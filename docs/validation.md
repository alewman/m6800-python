# Validation: the claim, the oracle inventory, and the record

The core exists and all seven rungs pass; the measured record is in
[The record so far](#the-record-so-far-2026-09-18), and this page keeps the
inventory that planned it, because which oracles exist for this family (and
which do not) is the reason the claim below is shaped as it is.

## The claim this project makes, and the one it cannot

The strongest honest claim available is:

> a pure-Python MC6800/6802/6808 and MC6801/6803 instruction core whose
> semantics, flags and cycle counts follow the Motorola manuals; which agrees
> with MAME 0.285's `m6800`/`m6801` core over multi-million-instruction traces
> of real arcade code and over a generated single-step corpus; whose remaining
> disagreements with MAME are enumerated, each attributed to a manual, to a
> published hardware measurement, or to a MAME simplification; and whose
> undocumented-opcode behaviour is marked as unverified wherever no
> measurement exists — which is nearly everywhere.

It **cannot** claim "verified against real silicon", for a blunter reason than
the 6809 project had: for the 6800 family there is **no hardware-captured
corpus, no hardware-corrected self-checking program, and no bus-decoder
project at all**. The evidence base is the manuals, one 1977 magazine article,
one 2019 measurement of two opcodes, and emulators.

## Oracle tiers

The user's rule: rank oracles by where their expected values came from.
**hardware-captured > hardware-corrected > emulator-derived.** A low-tier
oracle is a detector, never a judge. State the tier of every oracle.

| Tier | Meaning | What exists for the 6800 family |
| --- | --- | --- |
| **hardware-captured** | expected values read off a real part's bus or registers | Doc TB's 2019 Universal Chip Analyzer measurement of **HCF (`$9D`, `$DD`) only**. Nothing else |
| **hardware-corrected** | a self-checking program adjusted until a real part passed it | **nothing found** |
| **emulator-derived** | values produced by another emulator | MAME 0.285 (traces here; a corpus a build session can generate), sim68xx, EXORsim, shdl6800 |
| **datasheet** | the manufacturer's stated behaviour, "undefined" marked as undefined | M68PRM, MCSDD, M6801RM, APPS — **the judge, by default, for everything documented** |
| **secondary literature** | a published account without a stated method | Gerry Wheeler's 1977 *BYTE* article (better than this tier for the opcodes he measured; treated as hardware-captured for HCF because a later measurement corroborates it) |

Because the hardware tier is nearly empty, this project inverts the usual
shape: **the datasheet is the judge**, emulators are detectors, and every
undocumented corner is carried as `[unverified]` rather than settled.

## Inventory

### SingleStepTests: no 6800-family corpus (confirmed 2026-09-12)

Every repository in the `SingleStepTests` organisation, enumerated with
`gh api orgs/SingleStepTests/repos --paginate` on 2026-09-12 (21 repositories):

```
ProcessorTests  GameboyCPUTests  8088  65x02  680x0  65816  sm83  z80
spc700  v20  sh4  m68000  ARM7TDMI  r3000  8086  80186  huc6280  80286
80386  ares_r3000_ssts  ares_tcls900h_ssts  tlcs900h
```

`gh api repos/SingleStepTests/6800` returns **404**. `ProcessorTests` contains
`6502/`, `65816/`, `680x0/`, `8088/`, `nes6502/`, `rockwell65c02/`, `spc700/`,
`synertek65c02/`, `wdc65c02/`, `tools/` — **no 6800 directory**.

`680x0` and `m68000` are the **16/32-bit MC68000 family**, a completely
different architecture despite the name. Do not mistake one for the other.

**There is no 6800, 6801 or 6803 single-step corpus in that organisation under
any name.**

### No third-party corpus anywhere

The 6809 project could fetch `neetandev/m6809`, a MAME-generated corpus in
SingleStepTests format. There is **no 6800 equivalent**: `neetandev`'s
repositories are `m68000`, `m6809`, `neetan`, `neetan-manager` (checked
2026-09-12), and GitHub searches for a 6800 test-vector corpus returned
nothing. **Nothing is fetchable for this CPU**, which is why `scripts/`
contains trace tooling and source/document fetchers rather than a corpus
fetcher.

### No instruction exerciser, no diagnostic, no bus decoder

Each of these was looked for and **not found** (2026-09-12):

- **A Klaus-Dormann-style functional test.** `Klaus2m5/6502_65C02_functional_tests`
  (GPL-3.0) has no 6800 counterpart, by that author or anyone else.
- **A ZEXALL-style exerciser.** Nothing found for any 6800-family part.
- **A hardware bus decoder.** `hoglet67` — the author of the 6809 project's
  two hardware-captured sources — has `6502Decoder`, `6809Decoder` and
  `Z80Decoder` and **no `6800Decoder`**. His `hoglet67/MEK6800D2` repository
  (no licence, last pushed 2024-07-04) contains a port of the *Smithbug*
  monitor to the MEK6800D2 board and `serial` bit-bang code — **not** a
  decoder and not a test suite.
- **Motorola-era diagnostics.** The EXORciser's *EXbug* and the MEK6800D2's
  *JBUG* are monitor/debug firmware, described inside
  `MC6800_EXORciser_Users_Guide_Second_Edition_1975.pdf` and
  `MEK6800D2_Manual_2ed_1977.pdf` on bitsavers respectively. Neither is a
  portable self-checking instruction test, and bitsavers'
  `components/motorola/6800/exorciser/` directory (≈30 manuals) holds no
  separate diagnostics document.

**Stated plainly: no hardware-tier oracle exists for the 6800 family's
documented instruction set.** The plan below is built on that fact rather than
around it.

### Gerry Wheeler, *BYTE*, December 1977 — the one contemporary account (read)

"Undocumented M6800 Instructions", *BYTE* vol. 2 no. 12, pp. 46-47; scan at
<https://archive.org/details/byte-magazine-1977-12>, file
`1977_12_BYTE_02-12_The_Star_Trek_Computers.pdf`, 142,627,639 bytes, SHA-1
`53af342f2bc68753924f4036ba7f81898cabb09f` (Internet Archive's own record),
SHA-256 `f9b5e8d87bba424e71a5156d9090f66adc468e3b4212a7ab786ac1d9e1020d5d`;
the magazine's copyright, so the scan stays in the gitignored `reference/`.
**Read on 2026-09-18.** Wheeler executed the 59 unassigned opcodes on his
machine and describes six in Table 1 and Figure 1: `$14` (A AND B → A), the
four store-immediate slots (which skip a byte and are three or four bytes
long, unlike MAME's), and HCF (`$9D`/`$DD`). No cycle counts; the rest are
"just NOPS" or change the flags by an "undeciphered" pattern, unnamed. Tier:
a measurement on one unknown-revision part, published without method.
Details and what the core does with each: [undocumented-behavior.md](undocumented-behavior.md).

### Doc TB, x86.fr, 2019 — hardware-captured, seven opcodes (read)

<https://x86.fr/investigating-the-halt-and-catch-fire-instruction-on-motorola-6800/>,
2019-07-17: an MC6800P run at 1 MHz on a Universal Chip Analyzer. **Read on
2026-09-18.** Captured: `$9D`/`$DD` lock up until reset and, 64 ms after the
fetch, drive the address bus as a clean counter at 500 kHz; `$FD` does the same
at 250 kHz; `$CD`/`$ED` also lock up, with glitchy address lines; `$15` is a
2-cycle NOP; `$14` ANDs the accumulators into A on a later MC6800P but not on
an early XC6800 prototype. **Tier: hardware-captured**, for those seven. No
licence stated; cited, not copied.

### Motorola manuals — the judge (fetched, pinned, and read)

`scripts/fetch_reference_docs.py` downloads four bitsavers scans into the
gitignored `reference/` directory and verifies each against a pinned SHA-256.
Run on 2026-09-12, all four verify:

| Short name | Bytes | SHA-256 |
| --- | --- | --- |
| `M68PRM` — *M6800 Programming Reference Manual*, M68PRM(D), Nov 1976 | 6,944,968 | `c2ca7c06d3eca33467aa11dab35cb65e3fe8a12f97c98007239ea3a45e379835` |
| `MCSDD` — *MC6800 Microcomputer System Design Data*, 1976 (contains the MC6800 data sheet) | 23,834,957 | `b6b7b88fcdc9dfc536e9898b7ae396cdc9cc328067c017749c891ad3e7eded8a` |
| `M6801RM` — *MC6801 Reference Manual*, MC6801RM/AD2, May 1984 (covers MC6801/68701/MC6803) | 19,173,732 | `1b4a5b321664fb73e7a8b1e3ea042512ed673dc133dbc2b3a81fd5196622f075` |
| `APPS` — *M6800 Microprocessor Applications Manual*, 1975 | 31,322,558 | `d0131b26a2e353d86d5b719a9c57413fdeec3b521c9c24b136d64df8bd42234b` |

Licence: Motorola's copyright; bitsavers hosts the scans for reference. They
are not redistributed, and `reference/` is gitignored.

**Read on 2026-09-18 (milestone 0).** The scans carry bitsavers' OCR text
layer, so `pdftotext -layout` (poppler-utils) reads the prose and the
per-instruction tables; the flag tables and timing diagrams were checked on
pages rendered with `pdftoppm`. What was done with them:

- `scripts/extract_manual_tables.py` reads every Appendix A instruction page
  of M68PRM (pp. A-3 to A-76) and M6801RM (pp. A-3 to A-90). It takes each
  opcode from the octal and decimal columns, which must agree, and lists the
  ten rows the text layer scrambles, each read off the rendered page. It finds
  **197** documented opcodes in M68PRM and **220** in M6801RM.
- **Cycle and byte counts: MAME 0.285 agrees with the manuals on every
  documented opcode of both parts** (`--report`). The table in
  [start-here.md](start-here.md) is now generated from the manuals
  (`--markdown`), not from MAME.
- **Flag rules: the old table was wrong on 52 opcodes**, because its flag
  column came from MAME's handler *comments*; MAME's *code* agrees with the
  manuals on all of them. Corrected in start-here.md, each with its page.
- **`CPX` is settled**: M68PRM p. A-33 gives two byte compares, Z over both,
  N and V from the high byte, C not affected; M6801RM p. A-39 gives a true
  16-bit compare setting N Z V C. MAME 0.285 models both (`cmpx_*` on the
  6800, `cpx_*` on the 6801). The first write-up of milestone 0 said MAME
  was wrong for the 6800; it had looked only at the 6801's handler table.
- **Interrupt entry is 12 cycles** on both parts: MCSDD's MC6800 data sheet,
  Figure 13, and M6801RM §5.3 / Figure 5-12. The quoted 13 is a response
  time (one recognition cycle plus 12). Out of `WAI`, **4 on both parts**:
  APPS p. A-14, Q20 for the MC6800 ("four MPU cycles"), M6801RM §5.4.2 for
  the 6801. (Settled when APPS was read; MCSDD's Figure 14 had been read as 5.)
- `DAA`'s rule reproduces M68PRM's nine-row table on all 384 BCD cases, and
  its V is "not defined" in both manuals.
- The `CLI`/`SEI`/`TAP`/`RTI` interrupt-delay rules are stated in M6801RM
  §5.4.1 and match MAME 0.285 for the 6801. For the MC6800, APPS p. A-13,
  Q15 gives a different `CLI` rule — the delay happens only when the opcode
  before the `CLI` is odd — which the core implements on `M6800` and MAME does
  not; APPS Q12 agrees on `RTI`; the 6800's `TAP` delay stays inferred.

APPS (the applications manual) was searched for interrupt timing on
2026-09-18; its questions-and-answers appendix (pp. A-10 to A-14) settled the
MC6800's `WAI` exit and `CLI` rule and documents the in-instruction races in
[timing.md](timing.md). The rest of its 712 pages has not been read.

### MAME 0.285 — emulator-derived, the working detector

- Installed at `/usr/games/mame`, version string `0.285 (unknown)`.
- Source: **not** the 0.261 tree that happens to be at
  an older MAME source tree on the machine. `scripts/fetch_mame_source.py` fetches the six
  files of the 0.285 core from the `mame0285` tag and verifies them:

| File | Bytes | SHA-256 |
| --- | --- | --- |
| `m6800.cpp` | 33,737 | `974d0c205992d81bfa5c60bb4e2bccf03b7102c047b272c60285bf30180e4485` |
| `m6800.h` | 8,841 | `42cf7ecb77327d9d660519d666c2b06918898360c2a40d97f53573ba2a05c7c4` |
| `m6801.cpp` | 76,580 | `f744e99e7deb17c1d4c47747611c58f5ad13a47531a55c163067e18c42b75e95` |
| `m6801.h` | 17,038 | `4b6351d17f6d901a7a05204ad4fccb1a56bbc33a76832c2af67ecfce0853a2be` |
| `6800ops.hxx` | 29,853 | `f4c692a1c51435a9c0b76a36c66dc8060fc6e6963da7cba84d75ac65fcc5dec1` |
| `6800dasm.cpp` | 8,300 | `34b6497ef445231f27d2bc97adcd6e028381b849161e1cab86685b538a5b626f` |

Licence: MAME's CPU cores carry `// license:BSD-3-Clause` in their headers;
the project as a whole is GPL-2.0+ and GitHub reports the repository licence
as `NOASSERTION` because of the mix. Check the file header, which for all six
of these is BSD-3-Clause, copyright Aaron Giles.

**What the 0.261 tree would have got wrong.** The opcode tables, the cycle
tables and the disassembler table are byte-identical between 0.261 and 0.285
(verified by diffing the extracted arrays). Two things are not:

- the illegal-opcode cycle sentinel, `#define XX`, is **5** in 0.261 and
  **4** in 0.285;
- `CLI`/`SEI`/`TAP` interrupt-delay handling was rewritten: 0.261 ran an extra
  instruction inline for all three; 0.285 does it for `TAP` always, for `CLI`
  only when `I` was actually set, and not at all for `SEI`.

Coverage as an oracle: whole-program traces of real arcade code, per
instruction, with registers and a running cycle total —
[mame-oracle.md](mame-oracle.md) records three verified runs (Drag Race
MC6800, Robotron's MC6808 sound board, Knuckle Joe's MC6803 sound board).
Limits: no bus-level detail, interrupt latency tied to the scheduler
timeslice, and the documented-plus-invented mixture on the illegal opcodes.

### Independent emulators for cross-checking

| Emulator | URL | Licence | Independent core? |
| --- | --- | --- | --- |
| **sim68xx** (dg1yfe) | <https://github.com/dg1yfe/sim68xx> | **GPL-2.0** | yes; explicitly multi-variant across the 6800 family |
| **shdl6800** (GuzTech) | <https://github.com/GuzTech/shdl6800> | **ISC** | a partial SpinalHDL **port of n6800** (below), stopped at the design's part 8: no `CPX`, `LDS`/`LDX`, stack, subroutine or interrupt instructions, `DAA`, `TAB`/`TBA` or `ABA` |
| **n6800** (Robert Baruch) | <https://github.com/RobertBaruch/n6800>, commit `f117162` | **GPL-3.0** | the RTL design shdl6800 ports, carried further (to part 11): nMigen, cycle by cycle, with formal properties per instruction |
| **EXORsim** (Joe Allen) | <https://github.com/jhallen/exorsim> | **none stated** — treat as all-rights-reserved | yes; a 6800/6809 EXORciser and SWTPC emulator with assembler and debugger |
| **Sim-6800** (Shyann) | <https://github.com/Shyann/Sim-6800> | unconfirmed | unverified provenance |
| **jefftranter/6800** | <https://github.com/jefftranter/6800> | **no licence file found** (a search result claiming Apache-2.0 was **not** corroborated) | unverified |

Not found, though looked for: a transistor-level `visual6800` (only
`visual6502` exists), and Ray Bellis's "USim" is a **6809** simulator, not a
6800 one.

**Used for rung 5: sim68xx and n6800** — n6800 rather than shdl6800 because
it is the original of the two and the more complete. Two facts about them
found on the way (2026-09-18):

- **Neither RTL model was validated against silicon.** Both READMEs describe
  verification by the author's own formal properties, and n6800's bus cycles
  are written from Motorola's cycle-by-cycle tables — so on timing it is a
  second reading of MCSDD Table 8, not a measurement. (This settles the
  handoff brief's open question about shdl6800.)
- **sim68xx's MC6800 opcode table carries Hitachi HD6301 cycle counts** (NOP 1,
  BRA 3, INX 1 — `src/arch/m6800/optab.c` is a copy of the 6301 table), so it
  offers no opinion on MC6800 timing; its 6801-family targets are the Hitachi
  parts. It is compared on semantics, on the MC6800 only.

## The plan, in oracle-tier order

Each rung is cheaper than the next and earns one specific claim. Do not
reorder them; each one's failure is cheapest to diagnose before the next.

| Step | Gate | Judge or detector | Claim earned |
| --- | --- | --- | --- |
| 0 ✅ | **Read the four scans** (done 2026-09-18; results above). Correct [start-here.md](start-here.md) and [timing.md](timing.md) from M68PRM Appendix A, MCSDD's instruction-execution tables and M6801RM Appendix A. Settle `CPX`'s flags and the interrupt-entry cycle count | datasheet, **judge** | the table this project tests against is Motorola's, not MAME's |
| 1 ✅ | Per-opcode unit tests transcribed from the corrected table: bytes, cycles, flags, for both `M6800` and `M6803` classes; plus `PSHX`/`PULX` order, `RTI` with both stack contents, `WAI`, `SWI`, and the three interrupt entries | datasheet, **judge** | documented semantics and counts as Motorola states them |
| 2 ✅ | **Generate** a single-step corpus from MAME, the way `neetandev/m6809` was generated for the 6809, and run all 256 opcodes × N random states through it, comparing registers, memory and cycle count | MAME, detector | agreement with MAME on every documented opcode; every disagreement listed with the higher-tier source the core follows instead |
| 3 ✅ | Boot-segment replay of `dragrace` (`scripts/mame_trace.sh dragrace 2 :maincpu`, 368,676 lines, 483 IRQ entries) and of `kncljoe`'s 6803 sound CPU, comparing `curpc a b x s cc` and `totalcycles` deltas per line, special-casing `CLI`/`TAP` | MAME, detector | hundreds of thousands of instructions of real arcade code agree, on both parts |
| 4 ✅ | Williams sound-board host: memory map, one PIA with CB1 edge detection, an IRQ line, a DAC sink; drive it from the Robotron trace's command stream | MAME, detector | the 6808 runs a real sound ROM under a real host contract |
| 5 ✅ | Cross-check against **sim68xx** and **shdl6800** on the step-2 cases; three-way diff | independent emulators, detectors | every rule in the core is datasheet-backed or agreed by three independent implementations, and shdl6800's RTL gives a second opinion on cycle counts |
| 6 ✅ | The undocumented set: HCF as a halt state, and the Wheeler table once the *BYTE* article has been read (done 2026-09-18: both sources read; `undocumented="strict"`, `"measured"`, `"mame"`) | hardware-captured (HCF), secondary (the rest) | the two opcodes anyone has measured behave correctly; everything else stays explicitly `[unverified]` |

## The record so far (2026-09-18)

All seven rungs pass. Every number below was produced by the command beside it,
on CPython 3.14.4.

**Rung 1 — the manuals (tier: datasheet, the judge).** `pytest` runs 847
tests without the corpus (rungs 1 and 6), and 2 more for rung 2 when the corpus
exists; about 7 s in all. `tests/test_datasheet.py` checks all 197 MC6800 and 220
MC6803 opcodes from 40 random states each against `tests/datasheet.py` (cycles,
length, every flag the manual marks `-`, `0` or `1`); `tests/test_alu.py`
checks the `*` flags bit by bit against the manuals' printed Boolean formulae,
exhaustively for the 8-bit arithmetic, logic, single-operand and shift
instructions and for `MUL`; `tests/test_daa.py` covers all 1,024 `DAA` inputs
(the 384 the manual's table defines against the table) and every BCD addition;
`tests/test_cpx.py`, `tests/test_control.py` and `tests/test_interrupts.py`
cover the parts' `CPX` rules, the worked examples on M68PRM's `SWI`, `RTI`,
`JSR` and `RTS` pages, and the M6801RM section 5.4.1 interrupt-timing loops.

**Rung 2 — generated MAME corpus (tier: emulator-derived, a detector).**
`python scripts/mame_corpus.py generate` builds MAME 0.285's own 6800 handlers
from the pinned sources and writes 1,000 random-state cases for each of the
256 opcodes of each part; `python scripts/compare_mame_corpus.py` replays
them, comparing registers, memory, cycles and the exact bus access sequence.

| Part | Cases | Exact agreement | Explained differences | Unexplained |
| --- | --- | --- | --- | --- |
| MC6800 | 256,000 | 254,507 | 1,493 (`TAP` 750, `RTI` 743) | 0 |
| MC6803 | 256,000 | 254,467 | 1,533 (`TAP` 775, `RTI` 758) | 0 |

The explained differences are all one fact: after `TAP` or `RTI` the core
keeps CC bits 7-6 at 1, as the manuals do (M68PRM pp. A-67, A-70, A-72,
A-76), while MAME stores all eight bits. The undocumented opcodes agree
because the comparison runs with `undocumented="mame"`; that is agreement with
MAME's guess, not evidence about silicon.

**Rung 3 — real arcade code against MAME (tier: emulator-derived).**
`python scripts/replay_trace.py GAME` replays a watchpoint-logged MAME trace
(method and gotchas in [mame-oracle.md](mame-oracle.md)): registers before
every instruction, every non-ROM read and every write in order, the running
cycle total, and every interrupt entry.

| Game | CPU | Instructions | Interrupts replayed | Result |
| --- | --- | --- | --- | --- |
| `dragrace` | MC6800 | 368,675 | 483 IRQ, 479 of them out of `WAI` | all agree |
| `kncljoe` | MC6803 | 2,616,010 | 40,050 NMI, 240 IRQ, 8 back-to-back | all agree |
| `kidniki` | MC6803 | 10,544,332 | 160,015 NMI, 544 IRQ, 182 back-to-back | all agree |
| `bublbobl` (MCU) | MC6801U4 | 1,794,851 | 332 IRQ | all agree |
| `esclwrld` (Bally pinball) | MC6803 | 2,271,980 | 6,241 OCF, 390 ICF, 391 IRQ | all agree |

17,595,848 instructions in all. Drag Race executes one undocumented opcode,
`$02` at `$1230`; it replays only because `undocumented="mame"` gives it
MAME's behaviour. The MC6801 additions seen in real code: `MUL` (1,618 times,
Escape from the Lost World), `SUBD` (122,676, Bubble Bobble's MCU), `ADDD`,
`LDD`, `STD`, `PSHX`, `PULX`, `ABX`; only `LSRD` and `ASLD` occur in none of
the traces. Escape from the Lost World also exercises the 6803's on-chip
timer interrupts through the core's `irq2` input.

**Rung 6 — the undocumented set (tier: measured on silicon, 1977 and 2019).**
Both published measurements have been read and are implemented under
`undocumented="measured"`, each line citing its source: `$14` NBA, `$15` NOP,
Wheeler's store-immediate forms, and the HCF family (`$9D $DD $FD $CD $ED`),
which halts under every policy but `"mame"`. `tests/test_undocumented.py`
checks each against the article's table. Cycle counts nobody measured are
marked `[unverified]`.

**Rung 4 — a real board as the host (tier: emulator-derived).**
`python scripts/williams_sound.py` builds the Williams sound board of
Robotron on the core: the MC6808, RAM, ROM from the zip, an MC6821 PIA (port A
to the DAC, port B and CB1 from the main board, both IRQ outputs onto the
CPU's IRQ) at 894,886.25 Hz. Its input is 30 s of Robotron from MAME —
Advance, coin, start and some play — captured by `scripts/williams_capture.lua`
with Lua memory taps: the 176 sound commands the 6809 sent, each with its
machine time, and every write the 6808 made to its PIA. Run from reset with
the same commands at the same cycles, the board enters its IRQ handler at
`$FB11` 86 times (3 of them straight from the `$FB83: beq $FB83` idle loop)
and makes **all 199,423 PIA writes MAME made, in the same order with the same
values — the same 199,418 DAC bytes** — each within 3 cycles of MAME's time
(mean 1.0; MAME samples interrupts per timeslice, the core per instruction).
The command stream came from MAME's main CPU directly rather than from a
Robotron trace, which is simpler and times each command exactly.

**Rung 5 — independent emulators (tier: emulator-derived).** Both run the
MC6800 corpus's documented-opcode cases, 1,000 per opcode, from the same
states as the core:

- `python scripts/crosscheck/sim68xx.py` (sim68xx `d49c99a`, built in the
  gitignored `third_party/`; registers and memory, not cycles):
  **195,617 of 197,000 cases agree three ways** (core, MAME, sim68xx). In all
  2,622 differences the core and MAME agree and sim68xx is the odd one out, and
  the manuals side with the core each time: sim68xx's `CPX` takes N and V from
  the 16-bit difference (M68PRM p. A-33: the high byte; 11 cases); its `WAI`
  pushes nothing (p. A-76; 1,000 cases); its `DAA` breaks the manual's table on
  6 inputs, e.g. A = `$FC`, H = C = 0 gives `$02` where the table's row says
  add `$66` for `$62` and C = 1 (p. A-34), plus 365 inputs the table does not
  cover; and it does not wrap an operand fetch past `$FFFF` (1 case).
- `python scripts/crosscheck/n6800.py` (n6800 `f117162`, simulated in Python
  3.9 with amaranth 0.3; registers, memory, cycles and bus order):
  **173,527 of 197,000 cases agree**, and 173 of the 197
  documented opcodes agree on every case, cycle counts and bus order included —
  every stack, subroutine, interrupt, branch, indexed and read-modify-write
  instruction among them. n6800 also makes 72,000 valid-bus cycles the
  core does not, the MC6800's dummy reads ("Irrelevant Data", MCSDD Table 8),
  which the core and MAME leave out by design. Where n6800 differs, the manual
  again sides with the core: the twenty 8-bit immediate instructions take 3
  cycles in n6800 and 2 in M68PRM and MCSDD; `TSX`/`TXS` omit the ±1 (pp. A-74,
  A-75); `WAI` leaves SP one byte short of the seven it pushes (p. A-76); and
  `DAA` sets V in 473 cases, where both manuals say V is not defined.

**Open, carried forward:** the MC6800's `TAP` delay (inferred from the
6801's); HCF's bus
activity (not modelled); what a real part does with the ~50 unassigned opcodes
neither source describes; the dummy reads, if a host ever needs them;
`LSRD`/`ASLD` in real code.

### What would raise the ceiling

A logic-analyser capture of a real MC6800 executing a random-state single-step
generator — the 6800 equivalent of what SingleStepTests did for the 65x02 and
what `hoglet67/6809Decoder` did for the 6809 — would turn step 2 from a
detector into a judge and would settle the whole of
[undocumented-behavior.md](undocumented-behavior.md) at once. **Nobody has
done it.** It is outside this repository's scope and is written down here so
the ceiling on every claim is explicit.

A cheaper partial: **shdl6800** is an RTL reimplementation, so if its author
validated it against silicon, its bus behaviour would be a much better oracle
than MAME's. Whether he did is **unverified**; ask.

## Speed

Not an oracle rung -- this is not a correctness claim, just a reproducible
measurement of the pure-Python core's throughput. `benchmarks/m6800_core_benchmark.py`
(modelled on z80-python's `benchmarks/z80_core_benchmark.py`) runs four
deterministic workloads for a fixed instruction count, five repeats, and
reports the median: `alu_loop` (inherent/immediate ALU dispatch and a
relative branch), `indexed_memory` (`LDAA`/`STAA ,X` with `INX` and `CPX`),
`stack_calls` (`JSR`/`RTS`, `PSHA`/`PULA`), and `interrupts` (a `WAI` loop
with the host driving `irq`: one idle boundary observed, then the interrupt
taken from the wait, `RTI`, `BRA`). `tests/test_benchmark.py` checks each
workload is deterministic across repeats and actually exercises what its
name claims (`interrupts` really produces both a wait and an entry;
`stack_calls`' `SP` returns to where it started).

Measured 2026-10-07 on this machine (CPython 3.14.4 and PyPy 3.11.15, Linux
x86_64, 32 cores, load average ~5 at the time -- a shared machine, so read
these as representative, not as isolated-hardware benchmark figures;
`--instructions 500000 --repeats 5`, the defaults):

| Workload | CPython instr/s | CPython cycles/s | PyPy instr/s | PyPy cycles/s |
| --- | ---: | ---: | ---: | ---: |
| `alu_loop` | 4,486,015 | 10,467,362 | 79,919,726 | 186,479,255 |
| `indexed_memory` | 3,660,172 | 16,104,748 | 54,139,819 | 238,215,096 |
| `stack_calls` | 4,067,070 | 21,148,766 | 44,948,177 | 233,730,519 |
| `interrupts` | 2,969,218 | 16,627,622 | 81,790,405 | 458,026,270 |

For scale: z80-python's benchmark (a larger, more heavily dispatched
instruction set) runs 0.6-1.1 M instructions/s on CPython, per its own
record; the comparison is informative, not apples-to-apples, since the two
cores' workloads differ and neither benchmark was designed to be comparable
to the other. The Williams board's 30 s trace replay (rung 4, a fixed
program, not a looped workload) takes 4.0 s on CPython 3.14 and 1.9 s on
PyPy 3.11.

## A real 6803 host: the on-chip timer generating its own interrupts

Rungs 3 and 4 both read interrupt entries out of a MAME trace rather than
deciding them: a real "board" should not need the answer handed to it.
`scripts/m6803_board.py` builds the one piece that differs between the
MC6800 and the MC6801/6803 and that this project had not yet given a host --
TCSR, the free-running counter, and the output-compare register ($08-$0C) --
and lets the CPU's own `irq2` input be driven by that model instead of by the
trace, for Escape from the Lost World's Bally pinball MPU (MC6803).

**The target changed from the one first picked, and the trace already
available said why.** Knuckle Joe's sound ROM does contain one instruction
that reads the counter, but it never runs in the captured trace, and the ROM
never writes TCSR or the output-compare register anywhere in its 8 KiB --
checked by scanning the ROM and the trace directly, not assumed (see
[timing.md](timing.md) and the module's own docstring). esclwrld's captured
trace already shows the timer doing real work: TCSR read 7,710 times, the
output-compare register written 6,243 times, 6,241 output-compare interrupts
taken. That is the trace used here instead.

**What is modelled, and what is not.** TCSR, the counter and output compare
are entirely software-driven, so the board computes them, with the exact
register addresses and the pending-flag "read TCSR, then read the paired
register" clear sequence taken line-by-line from MAME 0.285's pinned
`reference/mame0285/m6801.cpp` (cited in the module). Input capture
($0D/$0E, 783 reads, 390 taken interrupts) depends on a signal external to
the chip -- most likely an AC zero-crossing detector, common on pinball
MPUs, but no driver source for this board is pinned to confirm it -- so its
reads and its interrupt entries are still read from the trace, exactly as
the external IRQ1 line already is for every game. Overflow (`TOF`) is
modelled for TCSR's read value, but this ROM never arms `ETOI`, so it is
never taken as an interrupt, matching the trace's zero `TOF` entries.

**Result**, checked 2026-10-07: all 2,271,980 instructions of the esclwrld
trace replay with every register, every bus access and the cycle total in
full agreement with MAME 0.285, and all 6,241 output-compare interrupts are
the board's own timer deciding, not read from the trace -- `ICF` (390) and
the external `IRQ` (391) remain trace-driven, by scope, as above. On CPython
3.14.4 and PyPy 3.11.15. `tests/test_m6803_board.py` (14 tests, fast) checks
the timer's documented rules directly -- the pending-flag protection, the
`$FFF8` counter-write quirk (not exercised by esclwrld's own trace, since it
only reads the counter), overflow across a multi-cycle jump that skips the
exact match point, OCF-outranks-TOF priority -- each citing the manual page
or the MAME source line it rests on. `tests/test_replays.py`'s
`test_m6803_board_matches_mame` (slow) is the full trace replay.
`scripts/m6803_debug.py` is the `williams_debug.py`-style debugger over it,
with `timer` (TCSR decoded, the counter, OC, what `irq2` is armed to) and
`irq2 VECTOR | off` added.

**Tier: emulator-derived**, the same as rungs 3 and 4 -- agreement here is
agreement with MAME on real code, not with silicon.

## Scope limits, stated now

- Instruction-level semantics, flags and cycle counts, and interrupt-entry
  sequences. Not intra-cycle bus timing, not DMA/`HALT`/three-state, not the
  6801's on-chip timer, SCI or ports — those are host devices
  ([timing.md](timing.md)).
- MC6800, MC6802, MC6808 (one instruction set) and MC6801/MC6803 (the
  superset). The Hitachi HD6301/HD63701/HD6303, the NSC8105's scrambled map,
  the MC6805 and the MC6809 are out of scope
  ([start-here.md](start-here.md)).
- No complete arcade board. The host contract is documented so that one can be
  built, and the MAME replay in step 3 stands in for it.
