"""Dependency-free execution control and structured debugging records.

``DebugSession`` drives an existing CPU -- any object with ``step()`` and
``capture_state()`` -- one boundary at a time, with execute breakpoints,
bounded runs, a history ring and, optionally, memory-access tracking and
watchpoints.  It never changes what the core does.  See docs/debug-session.md.
"""

from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from m6800_python._undocumented import UndocumentedOpcode
from m6800_python.disasm import ByteReader, Instruction, disassemble
from m6800_python.state import CPUState

I_BIT = 0x10


@runtime_checkable
class DebugTarget(Protocol):
    """The minimum a :class:`DebugSession` needs from a CPU."""

    def step(self) -> int:
        """Advance one instruction or interrupt boundary; return its cycles."""

    def capture_state(self) -> CPUState:
        """Capture the current CPU-owned state."""


class BoundaryKind(Enum):
    """What one ``step()`` did."""

    INSTRUCTION = "instruction"
    IRQ = "irq"  # IRQ (IRQ1 on the 6801) accepted
    IRQ2 = "irq2"  # an MC6801/6803 on-chip request accepted
    NMI = "nmi"
    WAIT_IDLE = "wait_idle"  # a cycle spent in WAI with nothing to end it
    HCF_IDLE = "hcf_idle"  # a cycle spent halted by HCF


class StopReason(Enum):
    """Why a bounded run returned control."""

    BREAKPOINT = "breakpoint"  # before the instruction at a breakpoint
    WATCHPOINT = "watchpoint"  # after the step that touched a watched address
    WAITING = "waiting"  # in WAI with no interrupt able to end it
    HALTED = "halted"  # halted by HCF; only reset leaves it
    UNDOCUMENTED = "undocumented"  # an unassigned opcode under undocumented="strict"
    STEP_LIMIT = "step_limit"
    CYCLE_LIMIT = "cycle_limit"


Access = tuple[str, int, int]  # ("r" or "w", address, value)


@dataclass(frozen=True, slots=True)
class StepRecord:
    """Immutable before/after evidence for one boundary."""

    sequence: int
    kind: BoundaryKind
    before: CPUState
    after: CPUState
    cycles: int
    instruction: Instruction | None
    #: Every bus access the step made, in order, when the session tracks
    #: accesses; ``None`` otherwise.
    accesses: tuple[Access, ...] | None = None

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("sequence must be a non-negative integer")
        if type(self.kind) is not BoundaryKind:
            raise ValueError("kind must be a BoundaryKind")
        if type(self.before) is not CPUState or type(self.after) is not CPUState:
            raise ValueError("before and after must be CPUState values")
        if type(self.cycles) is not int or self.cycles <= 0:
            raise ValueError("cycles must be a positive integer")
        if self.kind is not BoundaryKind.INSTRUCTION and self.instruction is not None:
            raise ValueError("only instruction boundaries carry an instruction")


@dataclass(frozen=True, slots=True)
class RunResult:
    """Summary of one bounded run."""

    reason: StopReason
    steps: int
    instructions: int
    cycles: int
    state: CPUState
    last_record: StepRecord | None
    #: For WATCHPOINT: the watched accesses that stopped the run.
    hits: tuple[Access, ...] = ()
    #: For UNDOCUMENTED: the opcode the core refused to guess about.
    error: UndocumentedOpcode | None = None


def next_boundary(state: CPUState) -> BoundaryKind:
    """What the next ``step()`` will do, decided exactly as ``M6800.step()`` decides it."""
    if state.halted:
        return BoundaryKind.HCF_IDLE
    if state.nmi_pending or (state.nmi and not state.nmi_previous):
        return BoundaryKind.NMI
    if not state.irq_inhibit and not state.cc & I_BIT:
        if state.irq:
            return BoundaryKind.IRQ
        if state.irq2 is not None:
            return BoundaryKind.IRQ2
    if state.waiting:
        return BoundaryKind.WAIT_IDLE
    return BoundaryKind.INSTRUCTION


class DebugSession:
    """Control an existing CPU without modifying its execution core.

    ``peek_byte`` must be side-effect-free (the host's memory, not its bus);
    without it stepping and breakpoints work but records carry no
    disassembly.  ``track_accesses=True`` wraps the CPU's ``read_byte`` and
    ``write_byte`` callables to record every access and enable watchpoints;
    :meth:`close` puts the originals back.
    """

    def __init__(
        self,
        target: DebugTarget,
        *,
        peek_byte: ByteReader | None = None,
        history_limit: int = 256,
        track_accesses: bool = False,
    ) -> None:
        if not isinstance(target, DebugTarget):
            raise TypeError("target must provide step() and capture_state()")
        if peek_byte is not None and not callable(peek_byte):
            raise TypeError("peek_byte must be callable or None")
        if type(history_limit) is not int or history_limit < 0:
            raise ValueError("history_limit must be a non-negative integer")
        self.target = target
        self.peek_byte = peek_byte
        self.history_limit = history_limit
        self.part = getattr(target, "PART", 6800)
        self.undocumented = getattr(target, "undocumented", "strict")
        self.breakpoints: set[int] = set()
        self.watchpoints: dict[int, str] = {}  # address -> "r", "w" or "rw"
        self.total_steps = 0
        self.total_instructions = 0
        self.total_cycles = 0
        self._history: deque[StepRecord] = deque(maxlen=history_limit or 1)
        self._accesses: list[Access] | None = None
        self._originals = None
        if track_accesses:
            self._wrap_bus()

    # -- access tracking ---------------------------------------------------

    @property
    def tracking(self) -> bool:
        return self._originals is not None

    def _wrap_bus(self) -> None:
        read, write = self.target.read_byte, self.target.write_byte
        self._originals = (read, write)
        self._accesses = []
        log = self._accesses

        def tracked_read(address: int) -> int:
            value = read(address)
            log.append(("r", address, value))
            return value

        def tracked_write(address: int, value: int) -> None:
            log.append(("w", address, value))
            write(address, value)

        self.target.read_byte = tracked_read
        self.target.write_byte = tracked_write

    def close(self) -> None:
        """Stop tracking accesses and give the CPU its own bus callables back."""
        if self._originals is not None:
            self.target.read_byte, self.target.write_byte = self._originals
            self._originals = None
            self._accesses = None

    # -- breakpoints and watchpoints ---------------------------------------

    def add_breakpoint(self, address: int) -> None:
        """Stop before executing the instruction at ``address``."""
        self.breakpoints.add(_address(address))

    def remove_breakpoint(self, address: int) -> None:
        self.breakpoints.discard(_address(address))

    def add_watchpoint(self, address: int, kind: str = "rw") -> None:
        """Stop after any step that reads (``"r"``), writes (``"w"``) or either (``"rw"``)."""
        if not self.tracking:
            raise ValueError("watchpoints need a session created with track_accesses=True")
        if kind not in ("r", "w", "rw"):
            raise ValueError('kind must be "r", "w" or "rw"')
        self.watchpoints[_address(address)] = kind

    def remove_watchpoint(self, address: int) -> None:
        self.watchpoints.pop(_address(address), None)

    # -- history -----------------------------------------------------------

    @property
    def history(self) -> tuple[StepRecord, ...]:
        """Bounded immutable view of the retained records, oldest first."""
        return tuple(self._history)

    def iter_history(self, *, newest_first: bool = False) -> Iterator[StepRecord]:
        return reversed(self._history) if newest_first else iter(self._history)

    def clear_history(self) -> None:
        self._history.clear()

    # -- execution ---------------------------------------------------------

    def step(self) -> StepRecord:
        """Advance exactly one boundary, ignoring breakpoints.

        An unassigned opcode under ``undocumented="strict"`` raises
        :class:`UndocumentedOpcode` with the CPU unchanged, as the core does.
        """
        before = self.target.capture_state()
        kind = next_boundary(before)
        instruction = None
        if kind is BoundaryKind.INSTRUCTION and self.peek_byte is not None:
            instruction = disassemble(
                self.peek_byte, before.pc, part=self.part, undocumented=self.undocumented
            )
        if self._accesses is not None:
            self._accesses.clear()
        cycles = self.target.step()
        if type(cycles) is not int or cycles <= 0:
            raise ValueError("target step() must return a positive cycle count")
        record = StepRecord(
            sequence=self.total_steps,
            kind=kind,
            before=before,
            after=self.target.capture_state(),
            cycles=cycles,
            instruction=instruction,
            accesses=None if self._accesses is None else tuple(self._accesses),
        )
        self.total_steps += 1
        self.total_cycles += cycles
        if kind is BoundaryKind.INSTRUCTION:
            self.total_instructions += 1
        if self.history_limit:
            self._history.append(record)
        return record

    def run(
        self,
        *,
        max_steps: int,
        max_cycles: int | None = None,
        stop_on_wait: bool = True,
        stop_on_halt: bool = True,
    ) -> RunResult:
        """Run until a stop condition or the mandatory step budget.

        Breakpoints stop *before* the instruction; watchpoints stop *after*
        the step that touched the address.  A cycle limit is checked after each
        atomic step and may be exceeded by that step's cost.
        """
        if type(max_steps) is not int or max_steps <= 0:
            raise ValueError("max_steps must be a positive integer")
        if max_cycles is not None and (type(max_cycles) is not int or max_cycles <= 0):
            raise ValueError("max_cycles must be a positive integer or None")
        steps = instructions = cycles = 0
        last = None

        def result(reason: StopReason, state: CPUState, **extra) -> RunResult:
            return RunResult(reason, steps, instructions, cycles, state, last, **extra)

        while steps < max_steps:
            state = self.target.capture_state()
            kind = next_boundary(state)
            if kind is BoundaryKind.INSTRUCTION and state.pc in self.breakpoints and steps:
                return result(StopReason.BREAKPOINT, state)
            if stop_on_wait and kind is BoundaryKind.WAIT_IDLE:
                return result(StopReason.WAITING, state)
            if stop_on_halt and kind is BoundaryKind.HCF_IDLE:
                return result(StopReason.HALTED, state)
            try:
                last = self.step()
            except UndocumentedOpcode as error:
                return result(StopReason.UNDOCUMENTED, self.target.capture_state(), error=error)
            steps += 1
            cycles += last.cycles
            if last.kind is BoundaryKind.INSTRUCTION:
                instructions += 1
            hits = self._watch_hits(last)
            if hits:
                return result(StopReason.WATCHPOINT, last.after, hits=hits)
            if max_cycles is not None and cycles >= max_cycles:
                return result(StopReason.CYCLE_LIMIT, last.after)
        return result(StopReason.STEP_LIMIT, last.after if last else self.target.capture_state())

    def _watch_hits(self, record: StepRecord) -> tuple[Access, ...]:
        if not self.watchpoints or not record.accesses:
            return ()
        return tuple(
            access
            for access in record.accesses
            if access[1] in self.watchpoints and access[0] in self.watchpoints[access[1]]
        )


def _address(address: int) -> int:
    if type(address) is not int or not 0 <= address <= 0xFFFF:
        raise ValueError("address must be an integer in range 0x0000..0xFFFF")
    return address


__all__ = [
    "Access",
    "BoundaryKind",
    "DebugSession",
    "DebugTarget",
    "RunResult",
    "StepRecord",
    "StopReason",
    "next_boundary",
]
