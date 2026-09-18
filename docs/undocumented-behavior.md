# Undocumented and undefined behaviour on the 6800 family

Every claim below names its source and its tier
([validation.md](validation.md)). `[unverified]` marks a claim this project
has only inferred, and `[MAME only]` marks one where MAME's choice is the
**only** account anyone has written down — which is not evidence about
silicon, only evidence about MAME.

Motorola documented **197** of the 256 opcodes on the MC6800 and **220** on the
MC6801/6803. The remaining 59 (and 36) are the subject of this page, plus a
handful of documented instructions whose flag results the manual calls
undefined.

## HCF — "Halt and Catch Fire", `$9D` and `$DD`

**Tier: hardware-captured** (for the behaviour), **datasheet** (for the fact
that the opcodes are unassigned).

The coinage and the first published account are Gerry Wheeler's, in
"Undocumented M6800 Instructions", *BYTE* vol. 2 no. 12, December 1977,
pp. 46-47 (scan: <https://archive.org/details/byte-magazine-1977-12>). Wheeler
counted Motorola's 197 documented opcodes, worked through what the other 59
did on the parts he had, and named `$9D` and `$DD` **HCF**; he states the
mnemonics are his own and that the behaviour was already known inside
Motorola.

What the chip does: the opcode's incomplete decoding never terminates the
instruction. The program counter free-runs, so the **address bus becomes a
binary counter** sweeping the whole 64 KB space at high speed, the data bus is
read and discarded, and the part responds to nothing but `RESET` — not to
`IRQ`, not to `NMI`.

A modern hardware measurement exists: Doc TB, "Investigating the 'Halt and
Catch Fire' instruction on Motorola 6800", x86.fr, 2019-07-17
(<https://x86.fr/investigating-the-halt-and-catch-fire-instruction-on-motorola-6800/>),
run on an MC6800P at 1 MHz on a Universal Chip Analyzer. Reported: about 64 ms
after the opcode is fetched every address line begins toggling in sequence at
roughly 500 kHz, a clean square wave with no glitching, i.e. A0 toggles every
two clocks and each higher line at half the rate below it. **No behavioural
difference between `$9D` and `$DD` was found.** That is one measurement by one
author on one part; this project treats it as hardware-captured for the
address-bus behaviour and `[unverified]` for the 64 ms figure's generality.

Motorola kept HCF deliberately when designing the **MC6802** (1977) and
repurposed it as a production self-test that exercises the on-chip address
logic and the 128-byte RAM — reported in the same x86.fr piece and repeated by
Wikipedia's *Halt and Catch Fire (computing)* article, which cites Wheeler.
`[unverified]` here: this project has not found the Motorola document that
states it.

### What MAME does, and why it matters

**MAME does not model HCF at all.** There is no occurrence of the string `HCF`
anywhere in `src/devices/cpu/m6800/`. Worse for a naive comparison, MAME is
inconsistent between the two opcodes:

| Opcode | MAME's `m6800_insn[]` | MAME's disassembler | Real MC6800 |
| --- | --- | --- | --- |
| `$9D` | `jsr_di` — **executes a JSR direct**, 6 cycles (`m6800.cpp`, `m6800_insn[]` row `$98-$9F`) | `{jsr, dir, 0}`, i.e. "valid on every CPU type" (`6800dasm.cpp`) | **HCF** |
| `$DD` | `illegl2` — logs and skips two bytes, 4 cycles (`m6800.cpp`, `m6800_insn[]` row `$D8-$DF`) | `{_std, dir, 1}`, "invalid on 6800" | **HCF** |

`JSR` direct is a genuine **6801/6803** instruction; MAME shares one opcode
table layout across the family and lets it leak onto the 6800. MAME's own
source carries the matching TODO: `"verify invalid opcodes for the different
CPU types"` (`m6800.cpp:24`).

**Consequence for this project.** A trace-based comparison against MAME can
never exercise HCF, and if 6800 arcade code ever hits `$9D` MAME will do
something plausible where the board would have locked up. `m6800-python` must
implement HCF as a halt state that only `reset()` leaves, must **not** follow
MAME on `$9D`, and must record the divergence rather than "fix" the core.
This is the first entry in the divergence register the handoff asks for.

## `$21` (`BRN`) and `$9D` (`JSR` direct): 6801 instructions MAME allows on a 6800

**Tier: datasheet.**

MAME shares one opcode-table layout across the family and two 6801 additions
leak onto the plain 6800. `$21` `BRN` (branch never — a two-byte no-op, added
so that every branch has a complement) and `$9D` `JSR` direct are both
documented **MC6801** instructions and both **unassigned on the MC6800**;
`$9D` is one of the two HCF bytes.

The arithmetic is the proof: MAME treats 203 opcodes as legal on the 6800.
Subtract `$21`, `$9D` and the four store-immediate slots and exactly **197**
remain, which is Motorola's documented opcode count for the part. Subtract the
five store-immediate-family slots from MAME's 225 6801-legal opcodes and
**220** remain. No other MAME opcode is unaccounted for, which is how this
project knows the list of inventions is complete rather than merely plausible.

`BRN` is harmless in practice — a 6800 executing `$21` under MAME skips two
bytes, which is what a 2-byte illegal NOP would do anyway, and the cycle count
even matches `BRA`'s. `$9D` is not harmless: see HCF above.

## The store-immediate family: `$87`, `$8F`, `$C7`, `$CF` (and `$CD`)

**Tier: datasheet** for the fact they are unassigned; **`[MAME only]`** for the
behaviour.

Row 8 and row C of the opcode map have holes where a "store to an immediate
operand" would sit: storing into the instruction stream is meaningless, so
Motorola left `$87` (STAA #), `$8F` (STS #), `$C7` (STAB #) and `$CF` (STX #)
unassigned on the 6800 **and** on the 6801/6803; `$CD` (STD #) is the 6801's
equivalent hole.

MAME implements all five as real stores. `sta_im` and the rest compute the
effective address as the immediate operand's own address and write there, so
executing `$87 $00` **writes A over the byte after the opcode** — self-modifying
code, in ROM a write that goes nowhere. MAME charges 3 cycles on the 6800 and
2 on the 6803 (`cycles_6800[0x87] = 3`, `cycles_6803[0x87] = 2`), and its
disassembler marks all four as valid on every part.

`$CD` (`STD #`) gives the game away completely: MAME's `m6803_insn[]`
dispatches it to `std_im`, but `cycles_6803[0xCD]` is the **`XX` illegal
sentinel**, so MAME executes a store nobody ever measured and charges it the
made-up illegal-opcode cost. That is why the `$CD` cell in the instruction
table shows 4 cycles rather than the 5 an `STD` in any other mode would cost.

What real silicon does with these four is **not known to this project**. The
6809 has the same family of holes and there hardware captures exist (David
Banks's work); no equivalent 6800 capture has been found
([validation.md](validation.md)). Treat them as `[unverified]`, implement
MAME's behaviour behind a flag if trace comparison needs it, and do not present
it as hardware behaviour.

## The illegal opcodes MAME merely logs

**Tier: `[MAME only]`.**

MAME's three illegal handlers (`6800ops.hxx:20-37`) are:

```c
OP_HANDLER( illegl1 ) { logerror("m6800: illegal 1-byte opcode: ..."); }
OP_HANDLER( illegl2 ) { logerror("m6800: illegal 2-byte opcode: ..."); PC++; }
OP_HANDLER( illegl3 ) { logerror("m6800: illegal 3-byte opcode: ..."); PC += 2; }
```

(The HD63701's `trap` handler, three lines below, is the one illegal-opcode
path MAME models properly, because Hitachi documented it: it vectors through
`$FFEE`. Motorola's parts have no such trap.)

i.e. a 1-, 2- or 3-byte NOP, no flag effect, no memory access, and a cycle
count taken from the `XX` sentinel, whose only purpose is to stop the emulator
hanging: `#define XX 4 // illegal opcode unknown cycle count`
(`m6800.cpp:248-249`). It was **5** in MAME 0.261 and **4** in 0.285 — the
clearest possible demonstration that none of the three numbers (the length,
the flags, the cycles) is a measurement. Wheeler's article shows that at least
some of these opcodes do real work on silicon (he names several with
semantics), so MAME's model is certainly wrong for some of them and nobody
has published which.

The **53 opcodes MAME treats as illegal on the MC6800**:

```
00 02 03 04 05 12 13 14 15 18 1A 1C 1D 1E 1F 38 3A 3C 3D 41 42 45 4B 4E
51 52 55 5B 5E 61 62 65 6B 71 72 75 7B 83 93 A3 B3 C3 CC CD D3 DC DD E3
EC ED F3 FC FD
```

The **31 it treats as illegal on the MC6801/6803**:

```
00 02 03 12 13 14 15 18 1A 1C 1D 1E 1F 41 42 45 4B 4E 51 52 55 5B 5E 61
62 65 6B 71 72 75 7B
```

The difference is exactly the 22 opcodes the 6801 assigns (`$04` `$05` `$38`
`$3A` `$3C` `$3D` and the `SUBD`/`ADDD`/`LDD`/`STD` groups). Note what this
says about `$9D` and `$DD`: neither list contains `$9D`, and `$DD` is illegal
on the 6800 only because MAME needs the slot for `STD` on the 6801.

Two specific claims worth chasing, both `[unverified]` here:

- **`$14`** is reported by the x86.fr article to AND both accumulators into A
  on "the later MC6800P" only. That is a secondary claim about a variant part,
  it is not corroborated, and MAME makes `$14` `illegl1`. Do not implement it
  without a second source.
- Wheeler's article characterises several other opcodes in the `$0x`/`$1x`
  range. This project has **not** read the article's tables (only the
  bibliographic record and secondary summaries); the build session should
  read the *BYTE* scan and turn its table into the section this page is
  missing. That is the single highest-value document for this page.

## Undefined flag results on documented instructions

The "Motorola says" column was checked against the manuals' Appendix A pages on
2026-09-18 ([start-here.md](start-here.md), `scripts/extract_manual_tables.py`).

| Instruction | Motorola says | MAME does | Tier of MAME's choice |
| --- | --- | --- | --- |
| `DAA` `$19` | V **"Not defined"** (M68PRM p. A-34, M6801RM p. A-40) | clears V. Handler does `CLR_NZV` then sets N, Z and ORs in the new carry, so V is left 0 (`6800ops.hxx:208-220`) | `[MAME only]` |
| `DAA` | C by a nine-row table (M68PRM p. A-34): every row with C = 1 before has C = 1 after | **never cleared** — the handler deliberately keeps the incoming carry and ORs in its own (`/* keep carry from previous operation */`); its rule reproduces the manual's table on all 384 BCD cases | **agrees with the manual**; still worth a targeted test |
| `ASL`/`ASLA`/`ASLB`, `NEG`/`NEGA`/`NEGB`, `ASLD`, and every subtract and compare | H **"Not affected"** (M68PRM pp. A-7, A-31, A-49, A-59, A-66; M6801RM p. A-10) — *not* undefined, as this row used to say | the comment column says `?` but the handlers leave H alone | **agrees with the manual**; only MAME's comments are wrong |
| **`CPX` on the MC6800** | Z from both bytes; N and V from the high-byte compare alone; **C not affected** (M68PRM p. A-33). The MC6801 is a true 16-bit compare setting all four (M6801RM p. A-39) | separate handlers per part: `cmpx_*` on the 6800 (`6800ops.hxx:1093`: N and V from the high byte, Z over 16 bits, C untouched) and `cpx_*` on the 6801 (`6800ops.hxx:1107`, `SET_FLAGS16`) | **agrees with the manuals on both parts** (an earlier revision of this row said otherwise, from reading only the 6801 table) |
| `LSRD` `$04` (6801) | N ← 0, V ← N ⊻ C (M6801RM p. A-57) | the *comment* says V unaffected (`-0*-*`) but the *code* does `if (NXORC) SEV` (`6800ops.hxx:60-68`) | MAME's comment is stale; its code matches the manual. The same holds for `ASR`, `LSR`, `ROR` (V), `TST` (C cleared) and `MUL` (Z not affected) |
| Illegal opcodes generally | nothing | 4 cycles (the `XX` sentinel; 5 in MAME 0.261), no flags | `[MAME only]` |
| Reset | I set; A, B, IX, SP, and the other CC bits **undefined** | `CC = $D0`, A = B = IX = SP = 0 (`m6800.cpp:577-585`) | `[MAME only]`; confirmed in a real run — the first trace line of Drag Race is `1200 0 0 0 0 D0 0 0` |

CC bits 7 and 6 read as 1 on silicon and MAME pins them by initialising `CC`
to `$C0`; nothing in the instruction set can clear them, and `TPA` returns
them set. A core that lets them be zero will diverge from every trace on the
first `TPA`/`PSH CC`.

## `WAI`'s corner

`WAI` pushes the frame **before** waiting, so the interrupt that ends the wait
must not push again. MAME charges 4 cycles for that entry rather than 12
(`m6800.cpp:449-473`). If `I = 1` and only `IRQ` is pending, `WAI` never
returns; MAME's handler burns the rest of the timeslice (`eat_cycles()`) and
re-checks on the next one. For the MC6801 the 4 agrees with the manual
(M6801RM §5.4.2); for the MC6800, MCSDD's Figure 14 reads as 5, so it is
**`[unresolved: 4 or 5]`** there ([timing.md](timing.md)).

MAME exposes the wait latch as a debugger register, `WAI`
(`m6800.cpp:550`), and the trace scripts log it. **The column is zero on every
trace line even when the program waits**, because each line is logged before
its instruction runs and the latch is clear again by the next one. An earlier
revision of this page read the all-zero column as "none of these ROMs use
`WAI`"; that was wrong. Drag Race's main loop is `12C0: wai`, and in the
two-second trace **479 of its 483 IRQs arrive while it waits**, all of them
replayed through the core by `scripts/replay_trace.py` (the frame is pushed
once, by `WAI`, and not again at entry). The entry's own cost cannot be read
off a MAME trace, since MAME idles out the rest of its timeslice first, so the
6800's 4-or-5 question stays with the manuals.

## What would settle all of this

A bus capture of a real MC6800 executing each unassigned opcode from a known
state, the way David Banks's `6809Decoder` did for the 6809. **No such work
exists for the 6800** — `hoglet67` has `6502Decoder`, `6809Decoder` and
`Z80Decoder` but no `6800Decoder` (repository list checked 2026-09-12). Until
somebody does it, every line of this page above the HCF section is either the
manual, a 1977 magazine article, one 2019 measurement of two opcodes, or
MAME's guess.
