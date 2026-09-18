# m6800-python

**Status (2026-09-18): the core exists and passes rungs 0 to 3 of the
validation ladder** — the Motorola manuals, a generated MAME corpus, and
13.5 million instructions of real arcade code replayed against MAME. It is
checked against the manuals and against MAME; **nothing here has been
verified against silicon, because for this family nothing can be** (see
"Oracles" below). Rungs 4 to 6 are still to do.

`m6800-python` is a readable, dependency-free Python 3.12+ instruction core
for the Motorola **6800 family** — MC6800, MC6802 and MC6808, which share one
instruction set, and the MC6801/MC6803 superset — built to the same embedding
contract as [z80-python](https://github.com/alewman/z80-python) and
6502-python: the host owns memory and I/O and supplies `read_byte` /
`write_byte`; the core owns registers, flags and the instruction-boundary
lifecycle (RESET, NMI, IRQ, SWI, WAI); `step()` executes one instruction or one
interrupt entry and returns its cycle count; the host schedules everything
else.

```python
from m6800_python import M6800, M6803   # also M6802, M6808 (= M6800), M6801 (= M6803)

memory = bytearray(0x10000)
cpu = M6800(memory.__getitem__, memory.__setitem__)
cpu.reset()                      # I set, PC from $FFFE
cycles = cpu.step()              # one instruction or one interrupt entry
cpu.irq = True                   # level-sensitive; cpu.nmi is edge-triggered
print(cpu.A, cpu.B, cpu.X, cpu.SP, cpu.PC, cpu.CC)
```

Every handler is one Motorola mnemonic with its manual page in its docstring;
the opcode map and both parts' cycle tables come from the manuals' Appendix A.
An opcode Motorola does not assign raises `UndocumentedOpcode` rather than
guessing, except the HCF family (`$9D $DD $FD $CD $ED` on the MC6800), which
halts until reset. `undocumented="measured"` adds what Wheeler (*BYTE*, 1977)
and Doc TB (2019) measured on real MC6800s; `undocumented="mame"` gives MAME
0.285's behaviour instead, for trace replay.

## Where it stands

| Rung | Judge or detector | Result |
| --- | --- | --- |
| 0. Read the manuals | datasheet (judge) | done: 197 + 220 opcodes extracted from Appendix A; `CPX` and the 12-cycle interrupt entry settled; the MC6800's `WAI` exit (4 or 5) still open |
| 1. Per-opcode tests from the manuals | datasheet (judge) | 847 tests pass: every opcode's cycles, length and stated flags; `*` flags against the manuals' Boolean formulae, exhaustive for 8-bit operations; all 1,024 `DAA` inputs |
| 2. Generated MAME single-step corpus | MAME (detector) | 512,000 cases: 508,974 exact; the other 3,026 differ only in CC bits 7-6 after `TAP`/`RTI`, where the core follows the manual; 0 unexplained |
| 3. Real code replayed against MAME | MAME (detector) | Drag Race (MC6800) 368,675 instructions, Knuckle Joe and Kid Niki (MC6803) 2,616,010 and 10,544,332: every register, bus access, cycle total and interrupt entry agrees |
| 4. Williams sound board host | MAME (detector) | not started |
| 5. sim68xx / shdl6800 three-way diff | independent emulators | not started |
| 6. The undocumented set | measured on silicon (1977, 2019) | both sources read; HCF family halts; Wheeler's `$14` and store-immediate forms and Doc TB's `$15` under `undocumented="measured"`; MAME disagrees on the store-immediates |

`python -m pytest` runs rungs 1 and 2 (2 only when the gitignored corpus has
been generated). Details, and every command: [docs/validation.md](docs/validation.md).

## Scope

| Part | What differs | Here |
| --- | --- | --- |
| **MC6800** | The 1974 original; external clock, no on-chip RAM | in scope |
| **MC6802** | Adds an on-chip ÷4 oscillator and 128 bytes of RAM | in scope — **identical instruction set and cycle counts** |
| **MC6808** | MC6802 without the RAM | in scope — identical |
| **MC6801 / MC6803** | Superset: the 16-bit **D** accumulator and eleven new mnemonics — `ABX`, `ADDD`, `ASLD`, `BRN`, `LDD`, `LSRD`, `MUL`, `PSHX`, `PULX`, `STD`, `SUBD`, plus `JSR` direct — and **72 shared opcodes that run faster** (three `CPX` forms run slower). The 6801 also carries an on-chip timer, an SCI and four I/O ports | instruction set and cycle counts in scope; **the timer, SCI and ports belong to the host, not the core** |
| HD6301 / HD63701 / HD6303 | Hitachi supersets: `XGDX`, `SLP`, `AIM`/`OIM`/`EIM`/`TIM`, an illegal-opcode trap through `$FFEE` | **out of scope**, noted |
| NSC8105 / MS2010-A | An unlicensed clone with a **scrambled opcode map** | **out of scope**, noted |
| **MC6805**, **MC6809** | Different cores despite the family name; the 6809 is binary-incompatible and has its own repository (`/data/emu/m6809-python`) | **out of scope** |

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
6800 one. The only hardware measurement anyone has published covers **two
opcodes**: Doc TB's 2019 Universal Chip Analyzer capture of HCF (`$9D`,
`$DD`), corroborating Gerry Wheeler's account in *BYTE*, December 1977. So the
**judge here is the Motorola manuals** — four bitsavers scans, fetched and
SHA-256-pinned by `scripts/fetch_reference_docs.py` — and **MAME 0.285 is a
detector**, pinned by `scripts/fetch_mame_source.py` and exercised by three
verified traces. Agreement with MAME will be reported as agreement with MAME,
never as verification against silicon.
[docs/validation.md](docs/validation.md) has the full inventory, the hashes and
the seven-rung plan.

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
- [docs/handoff-brief.md](docs/handoff-brief.md) — what the build session does,
  in order.
- [docs/README.md](docs/README.md) — index.

## Scripts

```text
python scripts/fetch_mame_source.py        # MAME 0.285's 6800 core, hash-verified
python scripts/fetch_reference_docs.py     # the four Motorola scans, hash-verified
python scripts/extract_manual_tables.py --markdown  # regenerate the instruction table from the manuals
python scripts/dump_mame_tables.py         # MAME's view of the same table, as a detector
scripts/mame_trace.sh dragrace 2 :maincpu  # MC6800 trace; see docs/mame-oracle.md
scripts/mame_trace.sh kncljoe 10 :soundcpu # MC6803 trace
M6800_PRESS="IN2:Advance:680:20" \
  scripts/mame_trace.sh robotron 20 :soundcpu   # MC6808 Williams sound board
```

Nothing they fetch or produce is committed: `reference/`, `tests/vectors/`,
`*.trace`, `error.log`, `mame-work/` and `mame-home/` are gitignored. ROMs are
read in place from `/data/emu/source/myrient.erista.me/files/MAME/ROMs (non-merged)/`
and are never copied.

## What this repository has *not* done

Said plainly, because the next session needs to know:

- **Not verified against silicon.** No hardware-tier oracle exists for this
  family beyond HCF; every result above is agreement with the manuals or with
  MAME, and is labelled as such.
- **Rungs 4 and 5 are not done**: no Williams sound-board host yet, no
  sim68xx/shdl6800 cross-check.
- **Open questions carried forward:** the MC6800's `WAI`-exit cost (4 or 5
  cycles; the core uses 4 from one constant); what a real part does with the
  ~50 unassigned opcodes neither measurement describes; HCF's bus activity
  during the halt (not modelled); the cycle counts of Wheeler's instructions.
- `MUL` and `SUBD` do not occur in any replayed trace; they are covered by the
  manual-formula tests and the MAME corpus only.
- APPS, the fourth manual, has not been read.
- No PyPy run yet; the core has only been timed on CPython 3.14.

## License

MIT (see `LICENSE`). Cited documents, MAME's source and any external test
material keep their own licences and are not bundled.
