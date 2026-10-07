# m6800-python

[![CI](https://github.com/alewman/m6800-python/actions/workflows/ci.yml/badge.svg)](https://github.com/alewman/m6800-python/actions/workflows/ci.yml)
[![Oracles](https://github.com/alewman/m6800-python/actions/workflows/oracles.yml/badge.svg)](https://github.com/alewman/m6800-python/actions/workflows/oracles.yml)

**Status (2026-09-18): the core exists and passes all seven rungs of the
validation ladder** — the Motorola manuals; a generated MAME corpus; 17.6
million instructions of real arcade and pinball code replayed against MAME; a Williams
sound board, built on the core, producing MAME's DAC output byte for byte;
two independent emulators; and the two published measurements of
undocumented opcodes. It is checked against the manuals, against MAME and
against other emulators; **nothing here has been verified against silicon,
because for this family almost nothing can be** (see "Oracles" below).

`m6800-python` is a readable, dependency-free instruction core
for the Motorola **6800 family** — MC6800, MC6802 and MC6808, which share one
instruction set, and the MC6801/MC6803 superset — built to the same embedding
contract as [z80-python](https://github.com/alewman/z80-python) (0.4.0 and
later, whose `Z80CPU(read_byte, write_byte, ...)` takes its bus the same way):
the host owns memory and I/O and supplies `read_byte` / `write_byte`; the core owns registers, flags and the instruction-boundary
lifecycle (RESET, NMI, IRQ, SWI, WAI); `step()` executes one instruction or one
interrupt entry and returns its cycle count; the host schedules everything
else.

```python
from m6800_python import M6800, M6803  # also M6802, M6808 (= M6800), M6801 (= M6803)

memory = bytearray(0x10000)
cpu = M6800(memory.__getitem__, memory.__setitem__)
cpu.reset()  # I set, PC from $FFFE
cycles = cpu.step()  # one instruction or one interrupt entry
cpu.irq = True  # level-sensitive; cpu.nmi is edge-triggered
print(cpu.A, cpu.B, cpu.X, cpu.SP, cpu.PC, cpu.CC)
```

Every handler is one Motorola mnemonic with its manual page in its docstring;
the opcode map and both parts' cycle tables come from the manuals' Appendix A.
An opcode Motorola does not assign raises `UndocumentedOpcode` rather than
guessing, except the HCF family (`$9D $DD $FD $CD $ED` on the MC6800), which
halts until reset. `undocumented="measured"` adds what Wheeler (*BYTE*, 1977)
and Doc TB (2019) measured on real MC6800s; `undocumented="mame"` gives MAME
0.285's behaviour instead, for trace replay.

## Reading and stepping through code

The same tooling as z80-python — a structured disassembler, CPU state
capture/restore, a debug session with breakpoints, watchpoints and history, a
command debugger, and comparable JSON Lines traces — plus a command line that
loads ROMs straight out of MAME zips:

```text
$ python -m m6800_python --zip robotron.zip:video_sound_rom_3_std_767.ic12@F000 --reset
m6800> registers
A=00 B=00 X=0000 SP=0000 PC=F01D CC=D0 -I----
IRQ=0 NMI=0 WAI=0 HCF=0 INHIBIT=0
m6800> disassemble
> F01D  0F          SEI
  F01E  8E 00 7F    LDS #$007F
  F021  CE 04 00    LDX #$0400
  F024  6F 01       CLR $01,X
...
m6800> step 3
m6800> break F044
m6800> run 1000
```

Or step through a whole board. `scripts/williams_debug.py` puts Robotron's sound
board -- CPU, RAM, ROM and its PIA -- under the same debugger. MAME's captured
sound commands arrive on schedule, or you can send one yourself. Watch the PIA,
read the DAC bytes, and write what it played to a WAV file:

```text
$ python scripts/williams_debug.py --no-capture
williams> break F044
williams> run 1000
stopped: breakpoint, 20 steps, 20 instructions, 81 cycles, PC=F044
williams> sound DB
command $DB at cycle 81 (0.000091 s); PIA IRQ=1
williams> watch 0402 r
williams> continue
stopped: watchpoint, 4 steps, 3 instructions, 23 cycles, PC=FB17
  r $0402 = $DB
williams> unwatch 0402
williams> run 400000
williams> wav db.wav
wrote 1.49 s to db.wav
```

The disassembler shares its opcode table with the core and agrees with MAME's
own on all 4,172 distinct instructions of the five replayed games.
[docs/debug-session.md](docs/debug-session.md) has the commands and the API;
[docs/disassembly.md](docs/disassembly.md), [docs/cpu-state.md](docs/cpu-state.md)
and [docs/trace-schema.md](docs/trace-schema.md) the rest.

## Where it stands

| Rung | Judge or detector | Result |
| --- | --- | --- |
| 0. Read the manuals | datasheet (judge) | done: 197 + 220 opcodes extracted from Appendix A; `CPX`, the 12-cycle interrupt entry, the 4-cycle `WAI` exit and the MC6800's opcode-dependent `CLI` delay settled |
| 1. Per-opcode tests from the manuals | datasheet (judge) | 847 core tests pass (911 with the tooling): every opcode's cycles, length and stated flags; `*` flags against the manuals' Boolean formulae, exhaustive for 8-bit operations; all 1,024 `DAA` inputs |
| 2. Generated MAME single-step corpus | MAME (detector) | 512,000 cases: 508,974 exact; the other 3,026 differ only in CC bits 7-6 after `TAP`/`RTI`, where the core follows the manual; 0 unexplained |
| 3. Real code replayed against MAME | MAME (detector) | 17.6 million instructions of five games — Drag Race (MC6800), Knuckle Joe, Kid Niki, Escape from the Lost World (MC6803) and Bubble Bobble's MCU (MC6801U4): every register, bus access, cycle total and interrupt entry agrees; `MUL` and `SUBD` among them |
| 4. Williams sound board host | MAME (detector) | Robotron's sound board on the core, fed 176 commands captured from MAME: all 199,423 PIA writes and 199,418 DAC bytes identical to MAME's, within 3 cycles |
| 5. Independent emulators | sim68xx, n6800 RTL (detectors) | sim68xx: 195,617 of 197,000 agree three ways, every other case sim68xx alone off; n6800: 173 of 197 opcodes agree on every case including cycles and bus order; each remaining difference settled by the manual in the core's favour |
| 6. The undocumented set | measured on silicon (1977, 2019) | both sources read; HCF family halts; Wheeler's `$14` and store-immediate forms and Doc TB's `$15` under `undocumented="measured"`; MAME disagrees on the store-immediates |

`python -m pytest` runs rungs 1, 2 and 6 (2 only when the gitignored corpus
has been generated); `python -m pytest -m slow` replays the MAME traces and
the Williams board of rungs 3 and 4, where they have been recorded locally. Details, and every command: [docs/validation.md](docs/validation.md).

### Proving another core is this one

A manifest fixes everything about a run — the part, the undocumented-opcode
policy, memory, the initial state, when the interrupt inputs change, when to
stop — so two cores given the same one see the same machine, and any difference
between their traces is a difference between the CPUs:

```text
python -m m6800_python.conformance trace examples/conformance/daa.json --out mine.jsonl
python -m m6800_python.conformance diff examples/conformance/daa.json theirs.jsonl
```

`diff` names the first boundary and field that differ, and `checkpoints` splits
a long run into segments that can be diffed in parallel.
`examples/conformance/` ships a manifest and reference trace for each decision
a port is likeliest to get wrong — the MC6800's `CLI` delay, `WAI` and its
wake-up costs, `CPX` on each part, `DAA`'s table, the stack frames — and
[docs/conformance.md](docs/conformance.md) is the contract, including the point
that matching the registers while missing `irq_inhibit` is not equivalence.

### Speed

`python benchmarks/m6800_core_benchmark.py` runs four deterministic
workloads — `alu_loop` (inherent/immediate ALU and a branch, no memory
access beyond opcode fetch), `indexed_memory` (`LDAA`/`STAA ,X` with `INX`
and `CPX`), `stack_calls` (`JSR`/`RTS`, `PSHA`/`PULA`, the stack pointer
returning to where it started each pass) and `interrupts` (a `WAI` loop with
the host asserting `irq` once an idle boundary has been observed, then
withdrawing it) — each for 500,000 `step()` calls, 5 repeats, median timed.
Measured on this machine (load average ~5 of 32 cores; a shared machine, not
a benchmarking lab, so treat these as representative rather than exact):

| Workload | CPython 3.14.4 | PyPy 3.11.15 |
| --- | --- | --- |
| `alu_loop` | 4.5 M instr/s, 10.5 M cycles/s | 80 M instr/s, 186 M cycles/s |
| `indexed_memory` | 3.7 M instr/s, 16.1 M cycles/s | 54 M instr/s, 238 M cycles/s |
| `stack_calls` | 4.1 M instr/s, 21.1 M cycles/s | 45 M instr/s, 234 M cycles/s |
| `interrupts` | 3.0 M instr/s, 16.6 M cycles/s | 82 M instr/s, 458 M cycles/s |

`tests/test_benchmark.py` checks each workload actually exercises what it
claims (`interrupts` really waits and really takes the IRQ; `stack_calls`'
`SP` really comes home) and that every workload is reproducible run to run,
not just fast. `--json FILE` writes the interpreter, platform and every
sample for a later comparison.

## Scope

| Part | What differs | Here |
| --- | --- | --- |
| **MC6800** | The 1974 original; external clock, no on-chip RAM | in scope |
| **MC6802** | Adds an on-chip ÷4 oscillator and 128 bytes of RAM | in scope — **identical instruction set and cycle counts** |
| **MC6808** | MC6802 without the RAM | in scope — identical |
| **MC6801 / MC6803** | Superset: the 16-bit **D** accumulator and eleven new mnemonics — `ABX`, `ADDD`, `ASLD`, `BRN`, `LDD`, `LSRD`, `MUL`, `PSHX`, `PULX`, `STD`, `SUBD`, plus `JSR` direct — and **72 shared opcodes that run faster** (three `CPX` forms run slower). The 6801 also carries an on-chip timer, an SCI and four I/O ports | instruction set and cycle counts in scope; **the timer, SCI and ports belong to the host, not the core** |
| HD6301 / HD63701 / HD6303 | Hitachi supersets: `XGDX`, `SLP`, `AIM`/`OIM`/`EIM`/`TIM`, an illegal-opcode trap through `$FFEE` | **out of scope**, noted |
| NSC8105 / MS2010-A | An unlicensed clone with a **scrambled opcode map** | **out of scope**, noted |
| **MC6805**, **MC6809** | Different cores despite the family name; the 6809 is binary-incompatible and has a repository of its own | **out of scope** |

[docs/start-here.md](docs/start-here.md) has the full comparison and the
complete opcode table for both instruction sets.

## Where these chips ran

Verified against MAME's drivers at the `mame0285` tag rather than from memory,
which corrected three things the brief for this repository assumed:

- **Williams** — the arcade sound board of Defender, Stargate, Robotron: 2084,
  Joust, Bubbles, Splat!, Sinistar and Blaster is an **MC6808** (not a 6800)
  fed the whole 3.579545 MHz crystal, dividing on-chip to **894,886 Hz**
  (`src/mame/midway/williams.cpp:1539`). Sinistar's cockpit and Blaster carry
  two of them. The later `williams2` boards run theirs at 1.000 MHz. The
  6809 is the main CPU on all of them.
- **Atari** — the largest group of boards where a 6800 is the *whole* machine:
  Drag Race, Fire Truck, Orbit, Sky Diver, Destroyer, Sprint 8, Tank 8, Triple
  Hunt, Poolshark, Cannonball (`src/mame/atari/*.cpp`), 756 kHz to 1.008 MHz.
- **Taito** — Field Goal's main CPU is an MC6800 (`taito/fgoal.cpp:538`) and
  the Qix sound board an MC6802 at 921,600 Hz (`taito/qix_a.cpp:147`); Bubble
  Bobble and Kiki KaiKai use an **M6801U4** as their protection MCU.
- **Irem** — the M52/M62 sound boards (Moon Patrol, Kung-Fu Master and
  relatives) are **MC6803** at 894,886 Hz, "verified on pcb"
  (`irem/irem.cpp:403,469,503`).
- **Seibu / Technos / Konami / Zaccaria / Nichibutsu** — Knuckle Joe's sound
  CPU is an MC6803 (`seibu/kncljoe.cpp:535`); Double Dragon's sub-CPU is an
  HD63701Y0 with bootlegs substituting an M6803 (`technos/ddragon.cpp:948,1002`); the
  Hyper Olympic bootleg ADPCM board is an MC6802 (`konami/trackfld.cpp:1050`);
  Zaccaria's sound board carries **two** MC6802s (`zaccaria/zaccaria_a.cpp:232,430`);
  Nichibutsu's Seicross, Tube Panic and mahjong boards use the NSC8105 clone.
- **Pinball, in enormous quantity** — Williams System 3-11, Bally, Stern,
  Gottlieb's competitors, Atari, Zaccaria, Hankin and others, across
  `src/mame/pinball/*.cpp` and `src/mame/shared/{williamssound,ballysound}.cpp`.
- **Gottlieb and Exidy do *not* use this family.** Gottlieb's arcade hardware
  is an Intel 8088 (`gottlieb/gottlieb.cpp:2168`) plus 6502-family sound boards
  (`shared/gottlieb_a.cpp:135` `M6503`, and `M6502` throughout), and Gottlieb's
  System 80 pinballs are 6502 (`pinball/gts80.cpp:510`). Every Exidy driver is
  6502, Z80 or 6809 — `exidy.cpp:1511` and `circus.cpp:361` and
  `carpolo.cpp:228` are `M6502`, `victory.cpp:219` is `Z80`, `exidy440.cpp:999`
  is `MC6809E` — and a grep for `M6800`/`M6802`/`M6803`/`M6808` across every
  file in `src/mame/exidy/` returns **zero** matches.

[docs/timing.md](docs/timing.md) has the clocks with their source lines.

## Oracles, in one paragraph

**There is no hardware-captured corpus for the 6800 family, no
hardware-corrected test program, no instruction exerciser, and no bus-decoder
project — none at all, checked 2026-09-12.** SingleStepTests has no 6800
repository (its `680x0` and `m68000` are the unrelated 16/32-bit MC68000);
nobody has published a MAME-generated corpus the way `neetandev/m6809` did for
the 6809; there is no Klaus-Dormann-style functional test and no ZEXALL
equivalent; `hoglet67`, who built the 6502, 6809 and Z80 bus decoders, has no
6800 one. The only published measurements of real parts cover a handful of
**undocumented** opcodes: Gerry Wheeler's six in *BYTE*, December 1977, and Doc
TB's seven, captured on a Universal Chip Analyzer in 2019. So the **judge here
is the Motorola manuals** — four bitsavers scans, fetched and SHA-256-pinned by
`scripts/fetch_reference_docs.py` — and **MAME 0.285 is a detector**, pinned by
`scripts/fetch_mame_source.py`, turned into a single-step corpus and replayed
on real code; sim68xx and the n6800 RTL model are two more. Agreement with any
of them is reported as agreement with that emulator, never as verification
against silicon.
[docs/validation.md](docs/validation.md) has the full inventory, the hashes and
the seven-rung plan.

### CI coverage

The two badges cover different things, and neither covers everything. A green
**CI** badge would not mean the oracle rungs passed, so they are separate
rather than implied:

| Badge | Runs | When |
| --- | --- | --- |
| **CI** | the fast suite (the manual-derived tests of rung 1, the tooling tests), Ruff check and format, the debugger front end, and a wheel build with an installed-API smoke test, on CPython 3.11-3.14 and PyPy 3.11 | every push and pull request |
| **Oracles** | rung 2: MAME 0.285's own 6800 handlers built from the hash-pinned sources and compared over 256,000 generated cases per part | weekly, and on demand |

**Rungs 3 to 7 are certified locally, not in CI**, because no workflow can
fetch what they need: the trace replays and the Williams sound board need MAME
0.285 and its ROM sets (`$ROMPATH`), and the n6800 and sim68xx cross-checks
need a Python 3.9 environment with amaranth and a C build. Their commands,
numbers and dates are in
[the validation record](docs/validation.md#the-record-so-far-2026-09-18);
treat that, not a badge, as the citation for those rungs.

## Documents

- [docs/start-here.md](docs/start-here.md) — the primer and the complete
  instruction table.
- [docs/timing.md](docs/timing.md) — cycle rules, the 6800/6801 differences,
  and the Williams host contract.
- [docs/undocumented-behavior.md](docs/undocumented-behavior.md) — HCF, the
  opcodes MAME invents, the undefined flags; every claim tiered.
- [docs/validation.md](docs/validation.md) — oracles, tiers, licences, pins,
  and the plan.
- [docs/mame-oracle.md](docs/mame-oracle.md) — the verified MAME trace recipe.
- [docs/disassembly.md](docs/disassembly.md), [docs/debug-session.md](docs/debug-session.md),
  [docs/cpu-state.md](docs/cpu-state.md), [docs/trace-schema.md](docs/trace-schema.md) —
  the tooling.
- [docs/handoff-brief.md](docs/handoff-brief.md) — what the build session does,
  in order.
- [docs/README.md](docs/README.md) — index.

## Scripts

```text
python scripts/fetch_mame_source.py        # MAME 0.285's 6800 core, hash-verified
python scripts/fetch_reference_docs.py     # the four Motorola scans, hash-verified
python scripts/extract_manual_tables.py --markdown  # regenerate the instruction table from the manuals
python scripts/dump_mame_tables.py         # MAME's view of the same table, as a detector
python scripts/extract_manual_tables.py --python > tests/datasheet.py  # the per-opcode datasheet
python scripts/mame_corpus.py generate     # rung 2: MAME 0.285's own handlers -> tests/vectors/
python scripts/compare_mame_corpus.py      # rung 2: replay the corpus through the core
python scripts/replay_trace.py dragrace    # rung 3 (also kncljoe, kidniki, bublbobl, esclwrld);
                                           # with no trace, prints the MAME command that records it
python scripts/williams_sound.py           # rung 4: the Robotron sound board against MAME
python scripts/williams_debug.py           # the same board, in the debugger
python scripts/crosscheck/sim68xx.py       # rung 5: three-way diff with sim68xx
python scripts/crosscheck/n6800.py         # rung 5: against the n6800 RTL model
scripts/mame_trace.sh dragrace 2 :maincpu  # a raw MAME trace; see docs/mame-oracle.md
python scripts/smoke_installed_package.py  # the installed wheel's public API, run by CI
```

Nothing they fetch or produce is committed: `reference/`, `tests/vectors/`,
`third_party/`, `*.trace`, `error.log`, `mame-work/` and `mame-home/` are
gitignored. ROMs are
read in place from the directory `$ROMPATH` names (the scripts also accept
`$MAME_ROMPATH`, and `$MAME` locates the binary) and are never copied.

## What this repository has *not* done

Said plainly, because the next session needs to know:

- **Not verified against silicon.** No hardware-tier oracle exists for this
  family beyond HCF; every result above is agreement with the manuals or with
  MAME, and is labelled as such.
- **The RTL cross-check used n6800, not shdl6800**: shdl6800 is an
  incomplete SpinalHDL port of n6800 and would need a JDK, sbt and Verilator;
  n6800 is the original and runs in Python. Neither was validated against
  silicon.
- **Open questions carried forward:** whether the MC6800's `TAP` holds off an
  IRQ as the 6801's does (the core assumes so); what a real part does with
  the ~50 unassigned opcodes neither measurement describes; HCF's bus
  activity during the halt (not modelled); the cycle counts of Wheeler's
  instructions.
- `LSRD` and `ASLD` do not occur in any replayed trace; they are covered by
  the manual-formula tests and the MAME corpus only.
- APPS, the fourth manual, has been searched for interrupt timing (its
  Q&A appendix settled the `WAI` exit and the MC6800's `CLI` rule), not read
  through.
- The Williams board's 30 s run takes 4.0 s on CPython 3.14 and 1.9 s on
  PyPy 3.11, for scale against the benchmark numbers in "Speed" above (that
  run replays a fixed trace rather than looping a workload, so it is not one
  of the four).

## License

MIT (see `LICENSE`). Cited documents, MAME's source and any external test
material keep their own licences and are not bundled.
