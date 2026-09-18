# m6800-python

**Status: documents and oracles only. There is no core code yet.**

`m6800-python` will be a readable, dependency-free Python 3.12+ instruction
core for the Motorola **6800 family** — MC6800, MC6802 and MC6808, which share
one instruction set, and the MC6801/MC6803 superset — built to the same
embedding contract as [z80-python](https://github.com/alewman/z80-python) and
6502-python: the host owns memory and I/O and supplies `read_byte` /
`write_byte`; the core owns registers, flags and the instruction-boundary
lifecycle (RESET, NMI, IRQ, SWI, WAI); `step()` executes one instruction or one
interrupt entry and returns its cycle count; the host schedules everything
else. This repository is the groundwork: the primer with the complete
instruction table, the timing and host notes, the undocumented-behaviour
record, the oracle inventory with its tiers and pins, the fetch and trace
scripts, and a handoff brief for the session that writes the core.

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

- **Milestone 0 is done (2026-09-18):** M68PRM, M6801RM and MCSDD were read
  (the scans carry an OCR text layer; poppler-utils reads it), the instruction
  table is now generated from the manuals by
  `scripts/extract_manual_tables.py`, and `CPX` and the 12-cycle interrupt
  entry are settled. See [docs/validation.md](docs/validation.md). APPS has not
  been read, and the MC6800's `WAI` exit cost (4 or 5) is still unresolved.
- Gerry Wheeler's 1977 tables of undocumented opcodes have not been read;
  only the bibliographic record and secondary summaries.
- No single-step corpus has been generated — there is none to fetch, so one
  must be made.

## License

MIT (see `LICENSE`). Cited documents, MAME's source and any external test
material keep their own licences and are not bundled.
