# Changelog

All notable changes to `m6800-python` are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
