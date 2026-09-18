# Validation plan and oracle inventory

## The claim this project will be able to make, and the one it cannot

When the core exists, the strongest honest claim available is:

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

### Gerry Wheeler, *BYTE*, December 1977 — the one contemporary account

"Undocumented M6800 Instructions", *BYTE* vol. 2 no. 12, pp. 46-47; scan at
<https://archive.org/details/byte-magazine-1977-12> (Internet Archive, the
magazine's own copyright). Wheeler worked out what a number of the 59
unassigned opcodes do on real parts and named `$9D`/`$DD` **HCF**. **This
project has not read the article's tables** — only its bibliographic record
and secondary summaries — and doing so is the single highest-value document
task for the build session ([undocumented-behavior.md](undocumented-behavior.md)).

### Doc TB, x86.fr, 2019 — hardware-captured, two opcodes

<https://x86.fr/investigating-the-halt-and-catch-fire-instruction-on-motorola-6800/>,
2019-07-17: an MC6800P run at 1 MHz on a Universal Chip Analyzer, address-bus
behaviour after `$9D`/`$DD` captured directly. **Tier: hardware-captured**, for
those two opcodes and nothing else. No licence stated; cited, not copied.

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
- **`CPX` is settled, and MAME is wrong for the MC6800**: M68PRM p. A-33
  gives two byte compares, Z over both, N and V from the high byte, C not
  affected; M6801RM p. A-39 gives a true 16-bit compare setting N Z V C.
  MAME applies the 6801 rule to both.
- **Interrupt entry is 12 cycles** on both parts: MCSDD's MC6800 data sheet,
  Figure 13, and M6801RM §5.3 / Figure 5-12. The quoted 13 is a response
  time (one recognition cycle plus 12). Out of `WAI`, 4 on the 6801
  (M6801RM §5.4.2); on the 6800 MCSDD Figure 14 reads as 5, so that one stays
  **`[unresolved: 4 or 5]`**.
- `DAA`'s rule reproduces M68PRM's nine-row table on all 384 BCD cases, and
  its V is "not defined" in both manuals.
- The `CLI`/`SEI`/`TAP`/`RTI` interrupt-delay rules are stated in M6801RM
  §5.4.1 and match MAME 0.285; M68PRM states no such rule for the MC6800
  (only §3.3.8's look-ahead), so the 6800 behaviour is marked inferred.

APPS (the applications manual) was not needed for any of this and has **not**
been read; it is extracted and searchable when something calls for it.

### MAME 0.285 — emulator-derived, the working detector

- Installed at `/usr/games/mame`, version string `0.285 (unknown)`.
- Source: **not** the 0.261 tree that happens to be at
  `/home/aubrey/mame-master`. `scripts/fetch_mame_source.py` fetches the six
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
| **shdl6800** (GuzTech) | <https://github.com/GuzTech/shdl6800> | **ISC** | yes, and it is an **RTL** reimplementation in SpinalHDL, so it is the closest thing to a second opinion about *bus cycles* rather than just semantics |
| **EXORsim** (Joe Allen) | <https://github.com/jhallen/exorsim> | **none stated** — treat as all-rights-reserved | yes; a 6800/6809 EXORciser and SWTPC emulator with assembler and debugger |
| **Sim-6800** (Shyann) | <https://github.com/Shyann/Sim-6800> | unconfirmed | unverified provenance |
| **jefftranter/6800** | <https://github.com/jefftranter/6800> | **no licence file found** (a search result claiming Apache-2.0 was **not** corroborated) | unverified |

Not found, though looked for: a transistor-level `visual6800` (only
`visual6502` exists), and Ray Bellis's "USim" is a **6809** simulator, not a
6800 one.

**sim68xx and shdl6800 are the two to use**: both clearly licensed, both
independently written, and one of them is RTL.

## The plan, in oracle-tier order

Each rung is cheaper than the next and earns one specific claim. Do not
reorder them; each one's failure is cheapest to diagnose before the next.

| Step | Gate | Judge or detector | Claim earned |
| --- | --- | --- | --- |
| 0 ✅ | **Read the four scans** (done 2026-09-18; results above). Correct [start-here.md](start-here.md) and [timing.md](timing.md) from M68PRM Appendix A, MCSDD's instruction-execution tables and M6801RM Appendix A. Settle `CPX`'s flags and the interrupt-entry cycle count | datasheet, **judge** | the table this project tests against is Motorola's, not MAME's |
| 1 | Per-opcode unit tests transcribed from the corrected table: bytes, cycles, flags, for both `M6800` and `M6803` classes; plus `PSHX`/`PULX` order, `RTI` with both stack contents, `WAI`, `SWI`, and the three interrupt entries | datasheet, **judge** | documented semantics and counts as Motorola states them |
| 2 | **Generate** a single-step corpus from MAME, the way `neetandev/m6809` was generated for the 6809, and run all 256 opcodes × N random states through it, comparing registers, memory and cycle count | MAME, detector | agreement with MAME on every documented opcode; every disagreement listed with the higher-tier source the core follows instead |
| 3 | Boot-segment replay of `dragrace` (`scripts/mame_trace.sh dragrace 2 :maincpu`, 368,676 lines, 483 IRQ entries) and of `kncljoe`'s 6803 sound CPU, comparing `curpc a b x s cc` and `totalcycles` deltas per line, special-casing `CLI`/`TAP` | MAME, detector | hundreds of thousands of instructions of real arcade code agree, on both parts |
| 4 | Williams sound-board host: memory map, one PIA with CB1 edge detection, an IRQ line, a DAC sink; drive it from the Robotron trace's command stream | MAME, detector | the 6808 runs a real sound ROM under a real host contract |
| 5 | Cross-check against **sim68xx** and **shdl6800** on the step-2 cases; three-way diff | independent emulators, detectors | every rule in the core is datasheet-backed or agreed by three independent implementations, and shdl6800's RTL gives a second opinion on cycle counts |
| 6 | The undocumented set: HCF as a halt state, and the Wheeler table once the *BYTE* article has been read | hardware-captured (HCF), secondary (the rest) | the two opcodes anyone has measured behave correctly; everything else stays explicitly `[unverified]` |

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
