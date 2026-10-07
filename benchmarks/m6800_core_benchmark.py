"""Reproducible microbenchmarks for the pure-Python MC6800 instruction core.

Modelled on z80-python's `benchmarks/z80_core_benchmark.py`: a flat-memory
host, deterministic workloads with all setup outside the timed region, median
of several samples, instructions/s and cycles/s. Every workload targets
`M6800` (identical instruction set and cycle counts to the MC6802/MC6808); the
family's superset timing differences on the MC6801/6803 are not this file's
subject.

    python benchmarks/m6800_core_benchmark.py
    python benchmarks/m6800_core_benchmark.py --workload interrupts --json out.json
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Final

from m6800_python import M6800, I

#: Where the reset, SWI, NMI and IRQ vectors live (M6801RM Appendix A); only
#: RESET and IRQ are used here.
VECTOR_IRQ: Final[int] = 0xFFF8
VECTOR_RESET: Final[int] = 0xFFFE
#: Where PSHA/PULA, JSR/RTS and WAI leave the stack, per the conformance
#: fixtures and `tests/conftest.make()`'s convention; chosen so pushes never
#: wrap through 0x0000 for any workload here.
INITIAL_SP: Final[int] = 0x01FF


class BenchmarkCPU(M6800):
    """Flat-memory benchmark host: a bytearray wired straight in as the bus."""

    def __init__(self, program: bytes, *, irq_vector: int | None = None) -> None:
        self.memory = bytearray(0x10000)
        self.memory[: len(program)] = program
        self.memory[VECTOR_RESET] = 0x00
        self.memory[VECTOR_RESET + 1] = 0x00
        if irq_vector is not None:
            self.memory[VECTOR_IRQ] = irq_vector >> 8
            self.memory[VECTOR_IRQ + 1] = irq_vector & 0xFF
        super().__init__(self.memory.__getitem__, self.memory.__setitem__)
        self.SP = INITIAL_SP
        # Construction leaves I set, as reset() does (README); the
        # interrupts workload needs it clear, and the others are indifferent,
        # so every workload starts the same way the shared test helper does
        # (`tests/conftest.make()`).
        self.CC &= ~I


#: A per-step callback that drives a workload's host inputs (only the
#: `interrupts` workload needs one); built fresh per sample so repeats and the
#: warmup run do not share mutable state.
Driver = Callable[[BenchmarkCPU], None]


def _no_driver(_cpu: BenchmarkCPU) -> None:
    return None


def _interrupt_driver() -> Driver:
    """Assert IRQ once a full idle wait has been observed, then withdraw it.

    WAI stacks the machine state and leaves `waiting` set until an interrupt
    arrives (M68PRM p. A-76); asserting IRQ the very step after WAI would skip
    the idle boundary entirely (IRQ is checked ahead of the wait in
    `next_boundary`), so this driver lets one `WAIT_IDLE` boundary pass before
    asserting, then withdraws IRQ as soon as the CPU is no longer waiting so
    the interrupt is not retaken before `RTI`'s caller reaches `BRA`.
    """
    armed = False

    def drive(cpu: BenchmarkCPU) -> None:
        nonlocal armed
        if cpu.waiting:
            cpu.irq = armed
            armed = True
        else:
            armed = False
            cpu.irq = False

    return drive


def _relative(opcode_address: int, target: int) -> int:
    """The signed byte a relative branch at `opcode_address` needs to reach `target`."""
    return (target - (opcode_address + 2)) & 0xFF


def _alu_loop_program() -> bytes:
    # LDAA #$31; LDAB #$17; ABA; CBA; INCB; DECA; TAB; BRA loop -- inherent and
    # immediate ALU dispatch and flag-setting, plus the relative branch, with
    # no memory access beyond opcode fetch.
    program = bytearray()
    program += bytes((0x86, 0x31))  # LDAA #$31
    program += bytes((0xC6, 0x17))  # LDAB #$17
    loop = len(program)
    program += bytes((0x1B,))  # ABA
    program += bytes((0x11,))  # CBA
    program += bytes((0x5C,))  # INCB
    program += bytes((0x4A,))  # DECA
    program += bytes((0x16,))  # TAB
    branch = len(program)
    program += bytes((0x20, _relative(branch, loop)))  # BRA loop
    return bytes(program)


def _indexed_memory_program() -> bytes:
    # LDX #$4000; loop: LDAA ,X; STAA ,X; INX; CPX #$4100; BRA loop. CPX's
    # result is unused (the branch is unconditional) so every sample's cycle
    # total is the same regardless of how far X has walked.
    program = bytearray()
    program += bytes((0xCE, 0x40, 0x00))  # LDX #$4000
    loop = len(program)
    program += bytes((0xA6, 0x00))  # LDAA $00,X
    program += bytes((0xA7, 0x00))  # STAA $00,X
    program += bytes((0x08,))  # INX
    program += bytes((0x8C, 0x41, 0x00))  # CPX #$4100
    branch = len(program)
    program += bytes((0x20, _relative(branch, loop)))  # BRA loop
    return bytes(program)


def _stack_calls_program() -> bytes:
    # loop: PSHA; PULA; JSR subroutine; BRA loop; subroutine: RTS.
    subroutine = 0x0010
    program = bytearray()
    loop = len(program)
    program += bytes((0x36,))  # PSHA
    program += bytes((0x32,))  # PULA
    program += bytes((0xBD, subroutine >> 8, subroutine & 0xFF))  # JSR subroutine
    branch = len(program)
    program += bytes((0x20, _relative(branch, loop)))  # BRA loop
    program = bytearray(program).ljust(subroutine, b"\x00")
    program += bytes((0x39,))  # RTS
    return bytes(program)


def _interrupts_program() -> tuple[bytes, int]:
    # loop: WAI; BRA loop; handler (elsewhere): RTI.
    handler = 0x0040
    program = bytearray()
    loop = len(program)
    program += bytes((0x3E,))  # WAI
    branch = len(program)
    program += bytes((0x20, _relative(branch, loop)))  # BRA loop
    program = bytearray(program).ljust(handler, b"\x00")
    program += bytes((0x3B,))  # RTI
    return bytes(program), handler


_INTERRUPTS_PROGRAM, _INTERRUPTS_HANDLER = _interrupts_program()


@dataclass(frozen=True)
class Workload:
    """Named deterministic program executed through :meth:`M6800.step`."""

    name: str
    description: str
    program: bytes
    irq_vector: int | None = None
    make_driver: Callable[[], Driver] = field(default=lambda: _no_driver)

    def host(self) -> BenchmarkCPU:
        return BenchmarkCPU(self.program, irq_vector=self.irq_vector)


WORKLOADS: Final[tuple[Workload, ...]] = (
    Workload(
        "alu_loop",
        "inherent and immediate ALU dispatch, flags, and a relative branch",
        _alu_loop_program(),
    ),
    Workload(
        "indexed_memory",
        "LDAA/STAA ,X with INX and CPX walking a 64 KiB host",
        _indexed_memory_program(),
    ),
    Workload(
        "stack_calls",
        "JSR/RTS and PSHA/PULA, SP returning to where it started each pass",
        _stack_calls_program(),
    ),
    Workload(
        "interrupts",
        "WAI, one idle boundary, IRQ entry from the wait, RTI, then BRA",
        _INTERRUPTS_PROGRAM,
        irq_vector=_INTERRUPTS_HANDLER,
        make_driver=_interrupt_driver,
    ),
)


@dataclass(frozen=True)
class Sample:
    """One timed benchmark sample."""

    elapsed_seconds: float
    cycles: int


@dataclass(frozen=True)
class BenchmarkResult:
    """All samples and derived rates for one workload."""

    name: str
    description: str
    instruction_count: int
    samples: tuple[Sample, ...]
    median_seconds: float
    instructions_per_second: float
    cycles_per_second: float


def _execute(cpu: BenchmarkCPU, instruction_count: int, driver: Driver) -> int:
    step = cpu.step
    cycles = 0
    if driver is _no_driver:
        for _ in range(instruction_count):
            cycles += step()
    else:
        for _ in range(instruction_count):
            driver(cpu)
            cycles += step()
    return cycles


def run_benchmark(
    workload: Workload,
    *,
    instruction_count: int,
    repeats: int,
    warmup_instructions: int,
) -> BenchmarkResult:
    """Run one workload with all host/program setup outside timed loops."""
    if instruction_count < 1 or repeats < 1 or warmup_instructions < 0:
        raise ValueError("instruction_count/repeats must be positive and warmup non-negative")

    if warmup_instructions:
        _execute(workload.host(), warmup_instructions, workload.make_driver())

    samples: list[Sample] = []
    for _ in range(repeats):
        cpu = workload.host()
        driver = workload.make_driver()
        started = time.perf_counter()
        cycles = _execute(cpu, instruction_count, driver)
        elapsed = time.perf_counter() - started
        samples.append(Sample(elapsed, cycles))

    median_seconds = statistics.median(sample.elapsed_seconds for sample in samples)
    median_cycles = statistics.median(sample.cycles for sample in samples)
    return BenchmarkResult(
        name=workload.name,
        description=workload.description,
        instruction_count=instruction_count,
        samples=tuple(samples),
        median_seconds=median_seconds,
        instructions_per_second=instruction_count / median_seconds,
        cycles_per_second=median_cycles / median_seconds,
    )


def _metadata() -> dict[str, str]:
    return {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
    }


def _print_results(results: list[BenchmarkResult]) -> None:
    metadata = _metadata()
    print(
        f"Python: {metadata['python_implementation']} {metadata['python_version']}\n"
        f"Platform: {metadata['platform']}"
    )
    for result in results:
        sample_text = ", ".join(f"{sample.elapsed_seconds:.6f}" for sample in result.samples)
        print(f"\n{result.name}: {result.description}")
        print(f"  instructions: {result.instruction_count:,} per sample")
        print(f"  samples (s): [{sample_text}]")
        print(f"  median (s): {result.median_seconds:.6f}")
        print(f"  instructions/s: {result.instructions_per_second:,.0f}")
        print(f"  cycles/s: {result.cycles_per_second:,.0f}")


def _write_json(path: Path, results: list[BenchmarkResult]) -> None:
    payload = {
        **_metadata(),
        "results": [asdict(result) for result in results],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instructions", type=int, default=500_000)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--warmup-instructions", type=int, default=25_000)
    parser.add_argument(
        "--workload",
        choices=("all", *(workload.name for workload in WORKLOADS)),
        default="all",
    )
    parser.add_argument("--json", type=Path, help="also write machine-readable results")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    selected = [
        workload
        for workload in WORKLOADS
        if args.workload == "all" or workload.name == args.workload
    ]
    try:
        results = [
            run_benchmark(
                workload,
                instruction_count=args.instructions,
                repeats=args.repeats,
                warmup_instructions=args.warmup_instructions,
            )
            for workload in selected
        ]
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    _print_results(results)
    if args.json is not None:
        _write_json(args.json, results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
