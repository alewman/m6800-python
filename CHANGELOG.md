# Changelog

All notable changes to `m6800-python` are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **A self-checking MC6800 functional test**, `validation/functional_test.asm`
  (and `functional_test_6801.asm` for the eleven MC6801/6803 additions),
  Klaus-Dormann-style: one case per documented mnemonic (`WAI` excepted --
  no freestanding ROM can supply its own interrupt), each wrong answer
  landing on its own trap address, success at `DONE` with A = `$AA`. No
  system assembler was found, so `scripts/asm6800.py` (a small two-pass
  MC6800/6801/6803 assembler) and `scripts/gen_functional_test.py` (the
  generator, deriving every expected value from `tests/test_alu.py`'s and
  `test_cpx.py`'s independent Boolean formulas and `start-here.md`'s `DAA`
  table, never from this core's own arithmetic) were written for it. Passes
  on both parts of the core, on sim68xx, and -- batched, not chained, after
  chaining turned out to be unreliable in the existing n6800 harness (see
  `scripts/crosscheck/functional_test_n6800.py`'s docstring and
  docs/validation.md) -- agrees with n6800 on 949 of 959 instruction
  boundaries, every difference already explained by n6800's documented
  `TSX`/`TXS` ±1 quirk. `tests/test_asm6800.py` and `tests/test_functional_test.py`
  cover the assembler and the generated program. README gained a "Hardware
  owners" section inviting anyone with real MEK6800D2/SWTPC/Altair 680
  silicon to run it and report back -- this family's first hardware-corrected
  oracle, if anyone does.

- **A real MC6803 timer host**, `scripts/m6803_board.py`: TCSR, the
  free-running counter and output compare, computed from the CPU's own
  returned cycles rather than played back, raising `irq2` itself.
  Replayed against MAME's trace of Escape from the Lost World's pinball
  MPU: 2,271,980 instructions agree in full, and all 6,241
  output-compare interrupts are the board's own timer deciding. Input
  capture and the external IRQ1/NMI lines stay trace-driven (the module
  docstring says why). `scripts/m6803_debug.py` is the debugger over it.
  `tests/test_m6803_board.py` (14 fast tests) checks the timer's
  documented rules directly; `tests/test_replays.py` gained the full
  replay as a slow test.

- **A reproducible benchmark harness**, `benchmarks/m6800_core_benchmark.py`
  (modelled on z80-python's): four deterministic workloads -- `alu_loop`,
  `indexed_memory`, `stack_calls`, `interrupts` -- with `--instructions`,
  `--repeats`, `--warmup-instructions`, `--json`, median and per-sample
  timing, instructions/s and cycles/s. Numbers for CPython 3.14 and PyPy
  3.11 are recorded in a "Speed" section in README and in
  docs/validation.md, replacing the ad hoc Williams-board-timing sentence
  that stood in for them before.

- **The conformance kit**, `m6800_python.conformance` and
  `python -m m6800_python.conformance`: a manifest fixes a run (part,
  undocumented policy, memory, initial state, interrupt events, stop rule), so
  two cores given one see the same machine and any difference between their
  traces is a difference between the CPUs. `trace`, `diff` and `checkpoints`,
  with nineteen fixtures in `examples/conformance/` covering the MC6800 CLI
  delay, WAI, CPX on each part, DAA's table, the stack frames, the measured
  undocumented opcodes and HCF. docs/conformance.md is the contract.

- CI gained a `package` job: it builds the wheel and sdist, installs the wheel,
  runs `scripts/smoke_installed_package.py` from outside the source tree, and
  checks that `py.typed` is in the wheel.
- An `Oracles` workflow, weekly and on demand, runs rung 2 in CI: MAME 0.285's
  own 6800 handlers, built from the hash-pinned sources, compared over 256,000
  generated cases per part. Rungs 3 to 7 still cannot run in CI, and the README
  says which badge covers what.

## [0.1.0] — 2026-10-05

The first release: the core, its tooling, and the record of what it is checked
against. Built 2026-09-18; released after the polish described below.

### Added

- **The core.** `M6800` (with `M6802` and `M6808` as the same instruction set)
  and `M6803` (with `M6801`), one class per part with the MC6801 superset's
  extra opcodes, `MUL` and the 16-bit accumulator operations. The host passes
  the bus in: `M6800(read_byte, write_byte)`. `step()` executes one instruction
  or one interrupt entry and returns its cycle count; the lifecycle at an
  instruction boundary is RESET, NMI, IRQ, the 6801's peripheral vectors
  (`irq2`), SWI and WAI, with the MC6800's `CLI`/`TAP` one-instruction
  interrupt delay and its dependence on the preceding opcode.
- **Undocumented opcodes** behind `undocumented=`: `"strict"` traps them,
  `"measured"` adds what Wheeler (1977) and Doc TB (2019) measured on real
  parts, `"mame"` follows MAME. Cycle counts no source gives are marked
  `[unverified]`.
- **Tooling**: `CPUState` with `capture_state()`/`restore_state()`; a
  structured disassembler sharing the core's opcode table; `DebugSession` with
  breakpoints, bounded runs, bus-access tracking and watchpoints;
  `CommandDebugger` and `python -m m6800_python`; and the JSON Lines trace
  schema with `first_trace_divergence` for comparing a port against this core.
- **The validation record** (docs/validation.md): seven rungs, with the
  Motorola manuals as the judge and every emulator as a detector. All 197
  MC6800 and 220 MC6803 opcodes against a generated datasheet table; the
  manuals' printed flag formulae; all 1,024 `DAA` inputs; a generated MAME
  0.285 corpus of 256,000 cases per part (254,507 and 254,467 exact, the rest
  one explained `TAP`/`RTI` difference); 17.6 million instructions of arcade
  and pinball code replayed against MAME traces; a Williams sound board
  reproducing MAME's DAC output byte for byte; n6800 and sim68xx as
  independent emulators. **Nothing here is verified against silicon beyond
  HCF**, because for this family almost nothing can be.

### Fixed

- `reset()` now forgets the opcode history, so a `CLI` immediately after a
  reset keeps the MC6800's one-instruction interrupt delay whatever ran before
  the reset.
- A trapped undocumented opcode leaves the CPU state untouched again, as
  `undocumented="strict"` promises: `step()` restores the opcode history when
  `UndocumentedOpcode` propagates.

### Changed

- The ROM directory for the local oracle rungs comes from `$ROMPATH` (or
  `$MAME_ROMPATH`), not a path baked into the scripts; MAME itself from `$MAME`.
- `ruff` is pinned, so `ruff format --check` cannot fail on an unchanged tree
  when a new ruff is released.
