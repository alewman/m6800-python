# Handoff: build `m6800-python`, a pure-Python 6800-family core, from these documents

## Context you are inheriting

`/data/emu/m6800-python` holds **documents, oracle research, fetch and trace
scripts, and no core code**. It was prepared on 2026-09-12 in the shape of the
user's existing cores, which are the models for everything you write:

- `z80-python` (`/data/emu/z80-python`, public): readable pure-Python Z80,
  host-owned memory, `step()` returns cycles, certified against
  SingleStepTests, ZEX and raxoft/z80test. Read its `docs/start-here.md`,
  `docs/validation.md`, `docs/conformance.md` and `src/z80_python/` for the
  code shape: instruction families as ordinary Python modules, explicit
  dispatch, one mnemonic per handler docstring, the hardware reason written as
  a comment on the line that encodes it.
- `6502-python` (`/data/emu/6502-python`): the same contract in a smaller core.
- `m6809-python` (`/data/emu/m6809-python`): the sibling prepared the same day.
  **The 6809 is a different, binary-incompatible CPU** — read that repository
  for the *shape*, never for 6800 facts.

The user works by an oracle-tier rule: rank oracles by where their expected
values came from, **hardware-captured > hardware-corrected > emulator-derived**;
a low-tier oracle is a detector, never a judge; state the tier of every oracle.

**The situation you are walking into is worse than the 6809's, and the honesty
about it is the point of this repository.** For the 6800 family there is
**no** hardware-captured corpus, **no** hardware-corrected self-checking
program, **no** bus-decoder project and **no** third-party test vectors of any
kind. The only hardware measurement anyone has published covers two opcodes
(`$9D`, `$DD`). So the judge is the Motorola manuals, MAME is a detector, and
the undocumented set stays marked `[unverified]`. Do not soften this in any
README you write, and do not let agreement with MAME be reported as
verification against silicon.

### Read, in this order, before writing code

1. `docs/start-here.md` — registers, CC, the six addressing modes, the full
   instruction table with both parts' cycle counts, the 6801/6803 additions,
   DAA and the half-carry, interrupts, vectors, `WAI`, the embedding contract.
2. `docs/undocumented-behavior.md` — HCF, the store-immediate family, the 53/31
   illegal opcodes, the undefined flags, and which of MAME's answers are
   inventions.
3. `docs/timing.md` — the cycle model, the 78 shared opcodes the 6801 runs
   faster and the three it runs slower, interrupt costs measured from a real
   trace, and the Williams sound-board host contract.
4. `docs/validation.md` — the oracle inventory, the tiers, the pinned hashes,
   and the seven-rung plan.
5. `docs/mame-oracle.md` — the verified trace recipe, three real runs, and the
   gotchas confirmed and corrected here.

## Your task

Write the core, in this repository, to the `z80-python`/`6502-python`
embedding contract: a `M6800` class and an `M6803` subclass that take host
`read_byte`/`write_byte`, expose `A`, `B`, `X`, `SP`, `PC`, `CC` as plain
attributes (`D` as a property on the 6803), sample `NMI`/`IRQ` at instruction
boundaries with the `CLI`/`TAP` one-instruction delay, and whose `step()`
executes one instruction **or** one interrupt-entry sequence and returns its
cycle count. Dependency-free, Python 3.12+, CPython and PyPy. Then pass the
validation plan in order.

### Milestone 0 — read the manuals (do this first, it is not optional)

`python scripts/fetch_reference_docs.py` puts four hash-pinned bitsavers scans
in `reference/`. **This session could not read them**: they are image-only
scans and the machine has no PDF rasteriser (`pdftoppm`/poppler absent, no
`pypdf`). Install poppler-utils, or use another machine, or OCR them — but
read them.

- **Acceptance:** `docs/start-here.md`'s instruction table is re-checked
  against M68PRM Appendix A and M6801RM Appendix A, cell by cell, and every
  correction is a commit that says which page it came from; the two flagged
  open questions below are answered from the manual; and the sentence in
  `docs/validation.md` saying the scans have *not* been read is deleted
  because it is no longer true.

The two questions that must not survive this milestone:

- **`CPX`'s flags on the MC6800 versus the MC6801.** `docs/start-here.md`
  carries the community account (6800: only Z reflects all sixteen bits;
  6801: N and V correct; neither touches C) marked `[unverified here]`. MAME
  models **no** difference at all. One of the two is wrong. M68PRM's `CPX`
  page and M6801RM decide.
- **Interrupt entry: 12 cycles or 13?** MAME charges 12, measured three times
  in `docs/mame-oracle.md`. M68PRM's sequence is usually quoted as 13. MCSDD's
  cycle-by-cycle instruction-execution table decides. The same question
  applies to the 4 cycles MAME charges for an interrupt taken out of `WAI`.

### Milestone 1 — skeleton and the datasheet table

Registers, CC with bits 7 and 6 pinned to 1, all six addressing modes
(remember the **unsigned** indexed offset), the dispatch table, and every
documented instruction with its Motorola mnemonic first in its docstring.

- **Acceptance:** a per-opcode unit suite transcribed from the corrected
  table — bytes, cycles, flags — passing for **both** `M6800` and `M6803`;
  `PSHX`/`PULX` byte order; `RTI` restoring the seven-byte frame; `SWI`,
  `WAI` and the three interrupt entries; `DAA` over all 256 A values × H × C;
  and a readability test enforcing "one mnemonic per handler docstring" the
  way `z80-python`'s does.

### Milestone 2 — generate a single-step corpus from MAME

Nothing is fetchable for this CPU. Build what the 6809 project could download:
a generator that drives MAME's `m6800`/`m6801` core over random initial states
and dumps expected registers, touched memory and cycle counts. The
`neetandev/m6809` generator (<https://github.com/neetandev/m6809>, `testgen/`)
is the worked example of the technique, including the SingleStepTests "MOO"
binary format; that project vendored MAME's core files and built them
standalone.

- **Acceptance:** ≥1,000 cases for each of the 197 documented 6800 opcodes and
  each of the 220 documented 6801/6803 opcodes, generated reproducibly from
  the pinned MAME 0.285 sources, kept **out of** the repository
  (`tests/vectors/` is gitignored), and the core agreeing on all of them **or**
  every disagreement listed with the higher-tier source it follows instead.
  Expected disagreements: the store-immediate opcodes, `$9D` on the 6800,
  `DAA`'s V, `CPX` if milestone 0 finds MAME wrong. **Do not change the core
  to match MAME where the manual disagrees.**

### Milestone 3 — MAME boot-segment replay

`scripts/mame_trace.sh dragrace 2 :maincpu` (3.2 s wall, 368,676 instruction
lines, 483 IRQ entries at `$15C7`) and `scripts/mame_trace.sh kncljoe 10
:soundcpu` (2,616,011 lines on an MC6803). Write a replay harness that loads
the ROMs in place from the zips at the addresses the drivers map, runs the
same instruction count, and compares `curpc a b x s cc` and the `totalcycles`
deltas per line, stopping at the first I/O read it cannot reproduce.

- **Acceptance:** Drag Race agrees from reset to its first unreproducible I/O
  read; the 483 interrupt entries land at the same instruction with the same
  seven-byte frame; the `CLI`/`TAP` cycle-accounting artefact documented in
  `docs/mame-oracle.md` is handled explicitly rather than papered over; and
  the same harness runs Knuckle Joe's 6803 far enough to exercise `MUL`,
  `LDD`/`STD`, `ADDD`/`SUBD` and `PSHX`/`PULX`.

### Milestone 4 — the Williams sound board as the first host

A memory map, one MC6821 PIA with CB1 edge detection and an IRQ output, a DAC
sink, and a cycle budget of 894,886 per emulated second
(`docs/timing.md`). The command stream can be lifted from a Robotron trace
rather than emulating the 6809 side.

- **Acceptance:** the 6808 leaves its `BEQ $FB83` self-loop on a command, runs
  the handler at `$FB11`, and produces the same DAC byte sequence MAME does
  for the same command. This is the rung that proves the embedding contract is
  usable, not just the core.

### Milestone 5 — independent-emulator cross-check

Build **sim68xx** (GPL-2.0) and **shdl6800** (ISC, an RTL implementation) and
run the milestone-2 cases through both.

- **Acceptance:** a three-way diff exists; every disagreement is resolved by
  the manual or recorded as unresolved in `docs/validation.md`; shdl6800's
  cycle behaviour is compared against the table specifically, since it is the
  only RTL opinion available.

### Milestone 6 — the undocumented set

Implement HCF (`$9D`, `$DD`) as a halt that only `reset()` clears — **not**
MAME's `JSR`. Then read Gerry Wheeler's "Undocumented M6800 Instructions",
*BYTE* December 1977, pp. 46-47
(<https://archive.org/details/byte-magazine-1977-12>) and turn its tables into
the section `docs/undocumented-behavior.md` is missing.

- **Acceptance:** HCF halts and is tested; every opcode Wheeler characterises
  is either implemented with a citation to his page or recorded as "described
  but not reproduced here"; every remaining illegal opcode keeps an explicit
  `[unverified]` marker and MAME's behaviour behind a compatibility flag, so
  that trace comparison still works without the core claiming MAME is right.

## Constraints

- **Do not modify the oracles.** If MAME or an emulator looks wrong, record the
  case and the higher-tier source; do not patch anything locally.
- **Never commit** a ROM, a MAME trace, a generated corpus, a bitsavers scan,
  or third-party source. `.gitignore` already excludes `tests/vectors/`,
  `tests/programs/`, `reference/`, `*.trace`, `error.log`, `mame-work/`,
  `mame-home/`. ROMs are read in place from
  `/data/emu/source/myrient.erista.me/files/MAME/ROMs (non-merged)/`.
- **Do not touch other directories under `/data/emu`.** Read them freely. The
  repository has no remote; do not push unless the user asks.
- **Do not quote `/home/aubrey/mame-master`.** It is MAME **0.261** and its
  6800 core differs from the installed 0.285 binary in exactly the places that
  matter. Use `scripts/fetch_mame_source.py`.
- Mirror `z80-python`'s module layout in spirit (`_alu`, `_loads`,
  `_branches`, `_stack`, `_index`, `_interrupts`, `_dispatch`), keep the
  explicit dispatch that PyPy compiles well, and put every hardware reason on
  the line that encodes it, with its source and tier.
- Same discipline as the user's other projects: every claim pinned to a hash
  or a revision and reproduced; state exactly what was and was not run;
  "the whole ladder" means every rung; report failures with their output.
- Commit in reviewable units with
  `git -c user.name=alewman -c user.email=alewman@gmail.com commit`, messages
  saying what the change rests on, ending with the trailer lines the user
  supplies for your session.

## Known open questions to carry, not to resolve silently

- `CPX` flags on the 6800 versus the 6801 (milestone 0).
- Interrupt entry: 12 or 13 cycles; `WAI` exit: 4 or something else.
- What a real MC6800 does with `$87`, `$8F`, `$C7`, `$CF` (and `$CD` on the
  6801) — MAME stores into the instruction stream; nobody has measured it.
- What a real MC6800 does with the other 47 unassigned opcodes. Drag Race's
  own ROM executes `$02` at `$1230`, so this is not academic.
- Whether the `$14` behaviour reported for "the later MC6800P" is real.
- Reset's cycle cost, and whether A/B/X/SP are really indeterminate.
- Whether `shdl6800` was validated against silicon.

## What done looks like

A `README.md` that states, with the pinned numbers `docs/validation.md`
requires (MAME version and the six core-file hashes, the four manual hashes,
the emulator versions), which rungs of the ladder pass, how many cases agree,
and the list of explained disagreements with their higher-tier sources; a
`docs/validation.md` turned from "plan" into "record"; and the oracle-tier
sentence kept intact — for this CPU more than any other the user works on,
**agreement with emulators is not verification against silicon, and there is
nothing else available.**

Before starting, tell the user in a few sentences how you read this brief and
what you will do first.
