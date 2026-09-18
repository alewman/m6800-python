# The Motorola 6800 family, for someone writing a core

This is the primer the build session reads before writing a line of
`m6800-python`. Everything here names its source. Where a claim comes from
MAME rather than from Motorola it says so, because MAME is an
**emulator-derived** source and under this project's oracle-tier rule it is a
detector, never a judge ([validation.md](validation.md)).

## Primary sources

All four are scans on bitsavers, fetched and hash-pinned by
`scripts/fetch_reference_docs.py`; the SHA-256 values are in
[validation.md](validation.md). Motorola's copyright stands; nothing is
redistributed here.

| Short name | Document | URL |
| --- | --- | --- |
| **M68PRM** | *M6800 Programming Reference Manual*, M68PRM(D), Nov 1976 | <https://www.bitsavers.org/components/motorola/6800/Motorola_M6800_Programming_Reference_Manual_M68PRM(D)_Nov76.pdf> |
| **MCSDD** | *MC6800 Microcomputer System Design Data*, 1976 — carries the MC6800 data sheet proper, including the cycle-by-cycle bus tables | <https://www.bitsavers.org/components/motorola/6800/MC6800_Microcomputer_System_Design_Data_1976.pdf> |
| **M6801RM** | *MC6801 Reference Manual*, MC6801RM/AD2, May 1984 — covers MC6801, MC68701 and **MC6803** | <https://www.bitsavers.org/components/motorola/6801/MC6801RM_AD2_MC6801_Reference_Manual_May84.pdf> |
| **APPS** | *M6800 Microprocessor Applications Manual*, 1975 | <https://www.bitsavers.org/components/motorola/6800/M6800_Microprocessor_Applications_Manual_1975.pdf> |

There is **no standalone `MC6800.pdf` data sheet on bitsavers** (checked
2026-09-12: `components/motorola/_dataSheets/6800.pdf` and `.../MC6800.pdf`
both 404). The data sheet lives inside MCSDD and inside the *1983 Motorola
8-Bit Microprocessor and Peripheral Data* databook
(<https://www.bitsavers.org/components/motorola/_dataBooks/1983_Motorola_8-Bit_Microprocessor_and_Peripheral_Data.pdf>).

Sections to read first: M68PRM §2 (programming model), §3 (addressing modes),
Appendix A (the opcode map with byte and cycle counts and the boolean flag
formulae); MCSDD's "MC6800 Microprocessor" data sheet, the
"Instruction Execution Sequence" tables; M6801RM §1-2 (what the 6801 adds),
§4 (the timer), §5 (the SCI), and its Appendix A opcode map.

## Not the 6809

The MC6809 shares the "68" family name and a rough philosophy and is
otherwise a **different, binary-incompatible CPU** — different opcode map,
different register set, different flags word; 6800 object code does not run on
it. `/data/emu/m6809-python` is its own repository; nothing in this one
applies there and nothing there applies here.

## Scope

| Part | What it is | Here |
| --- | --- | --- |
| **MC6800** | The 1974 original. External two-phase clock, no on-chip RAM | in scope |
| **MC6802** | MC6800 plus an on-chip clock oscillator (÷4 from the crystal) and 128 bytes of RAM at `$0000-$007F`, 32 of them battery-backable | in scope; **identical instruction set and cycle counts** |
| **MC6808** | MC6802 without the on-chip RAM | in scope; identical |
| **MC6801 / MC6803** | Superset: adds the 16-bit D accumulator and ten instructions, and speeds up many existing ones. The 6801 has on-chip ROM, RAM, a 16-bit timer, an SCI and four I/O ports; the 6803 is the ROM-less version | in scope for the **instruction set and cycle counts**; the timer, SCI and ports belong to the host, not to the core |
| MC6801U4 / MC6803U4 | 6801 with more RAM/ROM and extra timer registers | out of scope, noted |
| HD6301 / HD63701 / HD6303 (Hitachi) | Pin-compatible CMOS supersets: `XGDX`, `SLP`, `AIM`/`OIM`/`EIM`/`TIM`, an illegal-opcode **trap** through `$FFEE`, and a faster cycle table | **out of scope**, noted |
| NSC8105 / MS2010-A | National Semiconductor's unlicensed clone with a **scrambled opcode map** — same instructions at different opcodes | **out of scope**, noted |
| MC68120 / MC68121 | 6801 core plus dual-port RAM for inter-processor communication | out of scope |
| MC6805 | A different, smaller core (different registers, different opcodes) despite the family name | **out of scope** |
| MC6809 | See above | **out of scope** |

MAME models the same split: `m6800_cpu_device` with `m6802`/`m6808`/`nsc8105`
below it (`m6800.h:403-406`) and
`m6801_cpu_device` with `m6803`, `m6803e`, the Hitachi parts and the 68120
below it (`m6801.h:530-545`).

## Registers

```
 7      0   7      0
+--------+ +--------+
|   A    | |   B    |     two 8-bit accumulators
+--------+ +--------+
|        D          |     on 6801/6803 only: D is A:B, A the high byte
+-------------------+
 15                0
+-------------------+
|        IX         |     16-bit index register
+-------------------+
|        SP         |     16-bit stack pointer
+-------------------+
|        PC         |     16-bit program counter
+-------------------+
        7 6 5 4 3 2 1 0
       +-+-+-+-+-+-+-+-+
   CC  |1|1|H|I|N|Z|V|C|   condition code register
       +-+-+-+-+-+-+-+-+
```

- **A**, **B**: 8-bit accumulators. On the 6800 they are unrelated; on the
  6801/6803 the pair is also addressable as **D** (A is the high byte), and the
  ten added instructions all operate on D.
- **IX**: the only index register. There is no second index register and no
  16-bit arithmetic on IX beyond `INX`/`DEX`/`ABX`.
- **SP**: points at the **next free byte**, not at the top item. `PSHA` writes
  at SP then decrements; `PULA` increments then reads. This is why `TSX` is
  `X ← SP + 1` and `TXS` is `SP ← X − 1` (M68PRM, TSX/TXS).
- **CC**: bits 7 and 6 read as 1 on real parts and cannot be cleared. MAME
  initialises `m_cc = 0xC0` at reset (`m6800.cpp:577-579`) and its `TPA`
  returns them set; a core should keep them pinned to 1.

Flag meanings (M68PRM Appendix A):

| Bit | Name | Meaning |
| --- | --- | --- |
| 5 | **H** | Half carry: carry out of bit 3 of an 8-bit **add** (`ADDA/ADDB/ADCA/ADCB/ABA` only). Consumed by `DAA`. Not set by subtracts, not set by 16-bit adds |
| 4 | **I** | Interrupt mask. 1 = `IRQ` ignored. Set by reset, `SEI`, `SWI`, `WAI`'s completion and every interrupt entry |
| 3 | **N** | Negative: bit 7 of the 8-bit result, or bit 15 of a 16-bit result |
| 2 | **Z** | Zero: the whole result is zero (all 16 bits for 16-bit operations) |
| 1 | **V** | Two's-complement overflow |
| 0 | **C** | Carry/borrow out of bit 7 (bit 15 for the 6801's 16-bit operations). On subtracts and compares C is the **borrow** (set when the subtrahend is larger), which is the 6502 convention inverted |

## Addressing modes

Six, and only six. There is no indirection, no auto-increment, no indexing
off anything but IX, and no 16-bit offset.

| Mode | Form | Bytes | Effective address |
| --- | --- | --- | --- |
| **Inherent** (implied/accumulator) | `ABA`, `INX`, `CLRA` | 1 | none |
| **Immediate** | `LDAA #$40`, `LDX #$1234` | 2 or 3 | operand follows the opcode; 3 bytes when the operand is 16-bit (`LDS`, `LDX`, `CPX`, and on the 6801 `LDD`, `ADDD`, `SUBD`) |
| **Direct** ("zero page") | `LDAA $40` | 2 | `$0000 + byte`; reaches `$0000-$00FF` only |
| **Extended** | `LDAA $1234` | 3 | the 16-bit address as written |
| **Indexed** | `LDAA $10,X` | 2 | `IX + byte`, the byte **unsigned**, so the reach is `IX+0 .. IX+255` and never backwards. The sum wraps modulo 65536 |
| **Relative** | `BNE $1234` | 2 | `PC_after_instruction + signed byte`, reach −126..+129 from the opcode |

The unsignedness of the indexed offset is the single most common source of
bugs when porting from a 6502 or 6809 habit. `LDAA $FF,X` reads `IX+255`.

## The instruction set

**107** mnemonic forms over **197** opcodes on the MC6800. The MC6801/6803 add
**11** more forms over **23** more opcodes, for 118 forms over 220 opcodes.

Both totals are counted off the manuals' Appendix A pages, one opcode per row
(`scripts/extract_manual_tables.py`), and they agree with MAME once its
inventions are removed, which is a check that the inventions have all been
found. MAME treats **203** opcodes as legal on the 6800; remove the six
M68PRM does not document (`$21`, `$87`, `$8F`, `$9D`, `$C7`, `$CF`) and the
remaining **197** are exactly M68PRM's. MAME treats **225** as legal on the
6801/6803; remove the five M6801RM does not document (`$87`, `$8F`, `$C7`,
`$CD`, `$CF`) and the remaining **220** are exactly M6801RM's.

**How to read the table.** Each cell is `` `opcode` bytes/cycles ``. Where the
6800 and the 6801/6803 differ, both appear as `6800 · 6801`. An opcode marked
**†** exists only on the 6801/6803. An opcode marked **‡** is one Motorola
does **not** assign on the part in question: `$21` (`BRN`) and `$9D` (`JSR`
direct) are real 6801 instructions that MAME also executes on the 6800 (hence
**†‡**), and the store-immediate slots are assigned on neither part. MAME
executes them all anyway; [undocumented-behavior.md](undocumented-behavior.md)
says what it does and what is known about the real part. **The cycle count in
a ‡ cell is MAME's, not Motorola's**, and `$CD`'s 4 is MAME's `XX` sentinel
for "unknown".

Flags use Motorola's notation over **H N Z V C** (the I bit is not in this
column): `*` set or cleared by a rule, `-` not affected, `0` cleared, `1` set,
`?` "not defined" in the manual, `#` loaded from the operand (`TAP`) or the
stack (`RTI`). Where the two parts differ the cell reads `6800 · 6801`, which
happens for `CPX` alone. The rule behind each `*` is the one printed on the
instruction's Appendix A page; the ones a core is likeliest to get wrong are
spelled out below the table.

**Source.** Every byte count, cycle count and flag rule for a documented opcode
below comes from the Motorola manuals: M68PRM Appendix A (pp. A-3 to A-76) for
the MC6800 and M6801RM Appendix A (pp. A-3 to A-90) for the MC6801/6803, read
by `scripts/extract_manual_tables.py`, which regenerates this table with
`--markdown` and cross-checks it against MAME with `--report`. On 2026-09-18
it found **197** documented opcodes in M68PRM and **220** in M6801RM, and
MAME 0.285's cycle tables agree with the manuals on **every one**. MAME's
handler *comments*, from which this table's flag column was first generated,
do not: they were wrong on 52 opcodes, all corrected here from the manuals
(MAME's code is right on those; see `scripts/dump_mame_tables.py`).

| Mnemonic | Operation | IMM | DIR | IDX | EXT | INH / REL | HNZVC |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **ABA** | A ← A + B |  |  |  |  | `1B` 1/2 | `*****` |
| **ABX** | X ← X + B (B unsigned) |  |  |  |  | `3A`† 1/3 | `-----` |
| **ADCA** | A ← A + M + C | `89` 2/2 | `99` 2/3 | `A9` 2/5 · 4 | `B9` 3/4 |  | `*****` |
| **ADCB** | B ← B + M + C | `C9` 2/2 | `D9` 2/3 | `E9` 2/5 · 4 | `F9` 3/4 |  | `*****` |
| **ADDA** | A ← A + M | `8B` 2/2 | `9B` 2/3 | `AB` 2/5 · 4 | `BB` 3/4 |  | `*****` |
| **ADDB** | B ← B + M | `CB` 2/2 | `DB` 2/3 | `EB` 2/5 · 4 | `FB` 3/4 |  | `*****` |
| **ADDD** | D ← D + M:M+1 | `C3`† 3/4 | `D3`† 2/5 | `E3`† 2/6 | `F3`† 3/6 |  | `-****` |
| **ANDA** | A ← A ∧ M | `84` 2/2 | `94` 2/3 | `A4` 2/5 · 4 | `B4` 3/4 |  | `-**0-` |
| **ANDB** | B ← B ∧ M | `C4` 2/2 | `D4` 2/3 | `E4` 2/5 · 4 | `F4` 3/4 |  | `-**0-` |
| **ASL** | M ← M << 1, C ← b7 |  |  | `68` 2/7 · 6 | `78` 3/6 |  | `-****` |
| **ASLA** | A ← A << 1, C ← b7 |  |  |  |  | `48` 1/2 | `-****` |
| **ASLB** | B ← B << 1, C ← b7 |  |  |  |  | `58` 1/2 | `-****` |
| **ASLD** | D ← D << 1, C ← b15 |  |  |  |  | `05`† 1/3 | `-****` |
| **ASR** | M ← M >> 1 arithmetic |  |  | `67` 2/7 · 6 | `77` 3/6 |  | `-****` |
| **ASRA** | A ← A >> 1 arithmetic |  |  |  |  | `47` 1/2 | `-****` |
| **ASRB** | B ← B >> 1 arithmetic |  |  |  |  | `57` 1/2 | `-****` |
| **BCC** | branch if C=0 |  |  |  |  | `24` 2/4 · 3 | `-----` |
| **BCS** | branch if C=1 |  |  |  |  | `25` 2/4 · 3 | `-----` |
| **BEQ** | branch if Z=1 |  |  |  |  | `27` 2/4 · 3 | `-----` |
| **BGE** | branch if N⊕V=0 |  |  |  |  | `2C` 2/4 · 3 | `-----` |
| **BGT** | branch if Z∨(N⊕V)=0 |  |  |  |  | `2E` 2/4 · 3 | `-----` |
| **BHI** | branch if C∨Z=0 |  |  |  |  | `22` 2/4 · 3 | `-----` |
| **BITA** | A ∧ M, flags only | `85` 2/2 | `95` 2/3 | `A5` 2/5 · 4 | `B5` 3/4 |  | `-**0-` |
| **BITB** | B ∧ M, flags only | `C5` 2/2 | `D5` 2/3 | `E5` 2/5 · 4 | `F5` 3/4 |  | `-**0-` |
| **BLE** | branch if Z∨(N⊕V)=1 |  |  |  |  | `2F` 2/4 · 3 | `-----` |
| **BLS** | branch if C∨Z=1 |  |  |  |  | `23` 2/4 · 3 | `-----` |
| **BLT** | branch if N⊕V=1 |  |  |  |  | `2D` 2/4 · 3 | `-----` |
| **BMI** | branch if N=1 |  |  |  |  | `2B` 2/4 · 3 | `-----` |
| **BNE** | branch if Z=0 |  |  |  |  | `26` 2/4 · 3 | `-----` |
| **BPL** | branch if N=0 |  |  |  |  | `2A` 2/4 · 3 | `-----` |
| **BRA** | branch always |  |  |  |  | `20` 2/4 · 3 | `-----` |
| **BRN** | branch never (2-byte NOP) |  |  |  |  | `21`†‡ 2/3 | `-----` |
| **BSR** | push PC, branch to subroutine |  |  |  |  | `8D` 2/8 · 6 | `-----` |
| **BVC** | branch if V=0 |  |  |  |  | `28` 2/4 · 3 | `-----` |
| **BVS** | branch if V=1 |  |  |  |  | `29` 2/4 · 3 | `-----` |
| **CBA** | A − B, flags only |  |  |  |  | `11` 1/2 | `-****` |
| **CLC** | C ← 0 |  |  |  |  | `0C` 1/2 | `----0` |
| **CLI** | I ← 0 |  |  |  |  | `0E` 1/2 | `-----` |
| **CLR** | M ← 0 |  |  | `6F` 2/7 · 6 | `7F` 3/6 |  | `-0100` |
| **CLRA** | A ← 0 |  |  |  |  | `4F` 1/2 | `-0100` |
| **CLRB** | B ← 0 |  |  |  |  | `5F` 1/2 | `-0100` |
| **CLV** | V ← 0 |  |  |  |  | `0A` 1/2 | `---0-` |
| **CMPA** | A − M, flags only | `81` 2/2 | `91` 2/3 | `A1` 2/5 · 4 | `B1` 3/4 |  | `-****` |
| **CMPB** | B − M, flags only | `C1` 2/2 | `D1` 2/3 | `E1` 2/5 · 4 | `F1` 3/4 |  | `-****` |
| **COM** | M ← ¬M |  |  | `63` 2/7 · 6 | `73` 3/6 |  | `-**01` |
| **COMA** | A ← ¬A |  |  |  |  | `43` 1/2 | `-**01` |
| **COMB** | B ← ¬B |  |  |  |  | `53` 1/2 | `-**01` |
| **CPX** | X − M:M+1, flags only | `8C` 3/3 · 4 | `9C` 2/4 · 5 | `AC` 2/6 | `BC` 3/5 · 6 |  | `-***-` · `-****` |
| **DAA** | decimal adjust A after ADD/ADC/ABA |  |  |  |  | `19` 1/2 | `-**?*` |
| **DEC** | M ← M − 1 |  |  | `6A` 2/7 · 6 | `7A` 3/6 |  | `-***-` |
| **DECA** | A ← A − 1 |  |  |  |  | `4A` 1/2 | `-***-` |
| **DECB** | B ← B − 1 |  |  |  |  | `5A` 1/2 | `-***-` |
| **DES** | SP ← SP − 1 |  |  |  |  | `34` 1/4 · 3 | `-----` |
| **DEX** | X ← X − 1 |  |  |  |  | `09` 1/4 · 3 | `--*--` |
| **EORA** | A ← A ⊻ M | `88` 2/2 | `98` 2/3 | `A8` 2/5 · 4 | `B8` 3/4 |  | `-**0-` |
| **EORB** | B ← B ⊻ M | `C8` 2/2 | `D8` 2/3 | `E8` 2/5 · 4 | `F8` 3/4 |  | `-**0-` |
| **INC** | M ← M + 1 |  |  | `6C` 2/7 · 6 | `7C` 3/6 |  | `-***-` |
| **INCA** | A ← A + 1 |  |  |  |  | `4C` 1/2 | `-***-` |
| **INCB** | B ← B + 1 |  |  |  |  | `5C` 1/2 | `-***-` |
| **INS** | SP ← SP + 1 |  |  |  |  | `31` 1/4 · 3 | `-----` |
| **INX** | X ← X + 1 |  |  |  |  | `08` 1/4 · 3 | `--*--` |
| **JMP** | PC ← EA |  |  | `6E` 2/4 · 3 | `7E` 3/3 |  | `-----` |
| **JSR** | push PC, PC ← EA |  | `9D`†‡ 2/5 | `AD` 2/8 · 6 | `BD` 3/9 · 6 |  | `-----` |
| **LDAA** | A ← M | `86` 2/2 | `96` 2/3 | `A6` 2/5 · 4 | `B6` 3/4 |  | `-**0-` |
| **LDAB** | B ← M | `C6` 2/2 | `D6` 2/3 | `E6` 2/5 · 4 | `F6` 3/4 |  | `-**0-` |
| **LDD** | D ← M:M+1 | `CC`† 3/3 | `DC`† 2/4 | `EC`† 2/5 | `FC`† 3/5 |  | `-**0-` |
| **LDS** | SP ← M:M+1 | `8E` 3/3 | `9E` 2/4 | `AE` 2/6 · 5 | `BE` 3/5 |  | `-**0-` |
| **LDX** | X ← M:M+1 | `CE` 3/3 | `DE` 2/4 | `EE` 2/6 · 5 | `FE` 3/5 |  | `-**0-` |
| **LSR** | M ← M >> 1 logical |  |  | `64` 2/7 · 6 | `74` 3/6 |  | `-0***` |
| **LSRA** | A ← A >> 1 logical |  |  |  |  | `44` 1/2 | `-0***` |
| **LSRB** | B ← B >> 1 logical |  |  |  |  | `54` 1/2 | `-0***` |
| **LSRD** | D ← D >> 1 logical |  |  |  |  | `04`† 1/3 | `-0***` |
| **MUL** | D ← A × B (unsigned) |  |  |  |  | `3D`† 1/10 | `----*` |
| **NEG** | M ← 0 − M |  |  | `60` 2/7 · 6 | `70` 3/6 |  | `-****` |
| **NEGA** | A ← 0 − A |  |  |  |  | `40` 1/2 | `-****` |
| **NEGB** | B ← 0 − B |  |  |  |  | `50` 1/2 | `-****` |
| **NOP** | no operation |  |  |  |  | `01` 1/2 | `-----` |
| **ORAA** | A ← A ∨ M | `8A` 2/2 | `9A` 2/3 | `AA` 2/5 · 4 | `BA` 3/4 |  | `-**0-` |
| **ORAB** | B ← B ∨ M | `CA` 2/2 | `DA` 2/3 | `EA` 2/5 · 4 | `FA` 3/4 |  | `-**0-` |
| **PSHA** | push A |  |  |  |  | `36` 1/4 · 3 | `-----` |
| **PSHB** | push B |  |  |  |  | `37` 1/4 · 3 | `-----` |
| **PSHX** | push X (low byte first) |  |  |  |  | `3C`† 1/4 | `-----` |
| **PULA** | pull A |  |  |  |  | `32` 1/4 | `-----` |
| **PULB** | pull B |  |  |  |  | `33` 1/4 | `-----` |
| **PULX** | pull X |  |  |  |  | `38`† 1/5 | `-----` |
| **ROL** | M ← rotate left through C |  |  | `69` 2/7 · 6 | `79` 3/6 |  | `-****` |
| **ROLA** | A ← rotate left through C |  |  |  |  | `49` 1/2 | `-****` |
| **ROLB** | B ← rotate left through C |  |  |  |  | `59` 1/2 | `-****` |
| **ROR** | M ← rotate right through C |  |  | `66` 2/7 · 6 | `76` 3/6 |  | `-****` |
| **RORA** | A ← rotate right through C |  |  |  |  | `46` 1/2 | `-****` |
| **RORB** | B ← rotate right through C |  |  |  |  | `56` 1/2 | `-****` |
| **RTI** | pull CC,B,A,X,PC |  |  |  |  | `3B` 1/10 | `#####` |
| **RTS** | pull PC |  |  |  |  | `39` 1/5 | `-----` |
| **SBA** | A ← A − B |  |  |  |  | `10` 1/2 | `-****` |
| **SBCA** | A ← A − M − C | `82` 2/2 | `92` 2/3 | `A2` 2/5 · 4 | `B2` 3/4 |  | `-****` |
| **SBCB** | B ← B − M − C | `C2` 2/2 | `D2` 2/3 | `E2` 2/5 · 4 | `F2` 3/4 |  | `-****` |
| **SEC** | C ← 1 |  |  |  |  | `0D` 1/2 | `----1` |
| **SEI** | I ← 1 |  |  |  |  | `0F` 1/2 | `-----` |
| **SEV** | V ← 1 |  |  |  |  | `0B` 1/2 | `---1-` |
| **STAA** | M ← A | `87`‡ 2/3 · 2 | `97` 2/4 · 3 | `A7` 2/6 · 4 | `B7` 3/5 · 4 |  | `-**0-` |
| **STAB** | M ← B | `C7`‡ 2/3 · 2 | `D7` 2/4 · 3 | `E7` 2/6 · 4 | `F7` 3/5 · 4 |  | `-**0-` |
| **STD** | M:M+1 ← D | `CD`‡ 3/4 | `DD`† 2/4 | `ED`† 2/5 | `FD`† 3/5 |  | `-**0-` |
| **STS** | M:M+1 ← SP | `8F`‡ 3/4 · 3 | `9F` 2/5 · 4 | `AF` 2/7 · 5 | `BF` 3/6 · 5 |  | `-**0-` |
| **STX** | M:M+1 ← X | `CF`‡ 3/4 · 3 | `DF` 2/5 · 4 | `EF` 2/7 · 5 | `FF` 3/6 · 5 |  | `-**0-` |
| **SUBA** | A ← A − M | `80` 2/2 | `90` 2/3 | `A0` 2/5 · 4 | `B0` 3/4 |  | `-****` |
| **SUBB** | B ← B − M | `C0` 2/2 | `D0` 2/3 | `E0` 2/5 · 4 | `F0` 3/4 |  | `-****` |
| **SUBD** | D ← D − M:M+1 | `83`† 3/4 | `93`† 2/5 | `A3`† 2/6 | `B3`† 3/6 |  | `-****` |
| **SWI** | software interrupt, vector $FFFA |  |  |  |  | `3F` 1/12 | `-----` |
| **TAB** | B ← A |  |  |  |  | `16` 1/2 | `-**0-` |
| **TAP** | CC ← A |  |  |  |  | `06` 1/2 | `#####` |
| **TBA** | A ← B |  |  |  |  | `17` 1/2 | `-**0-` |
| **TPA** | A ← CC |  |  |  |  | `07` 1/2 | `-----` |
| **TST** | M − 0, flags only |  |  | `6D` 2/7 · 6 | `7D` 3/6 |  | `-**00` |
| **TSTA** | A − 0, flags only |  |  |  |  | `4D` 1/2 | `-**00` |
| **TSTB** | B − 0, flags only |  |  |  |  | `5D` 1/2 | `-**00` |
| **TSX** | X ← SP + 1 |  |  |  |  | `30` 1/4 · 3 | `-----` |
| **TXS** | SP ← X − 1 |  |  |  |  | `35` 1/4 · 3 | `-----` |
| **WAI** | stack state, wait for interrupt |  |  |  |  | `3E` 1/9 | `-----` |

### What the 6801/6803 add

Ten mnemonics, all of them about the D accumulator or the index register
(M6801RM §1.1 and its Appendix A pages, cited per row), plus `BRN` and
`JSR` direct as new opcodes for old mnemonics:

| Mnemonic | Opcodes | Cycles | Operation | HNZVC |
| --- | --- | --- | --- | --- |
| `ABX` | `3A` | 3 | `X ← X + B`, B unsigned, carry into IXH, no flags (A-4) | `-----` |
| `ADDD` | `C3` `D3` `E3` `F3` | 4/5/6/6 | `D ← D + M:M+1`; H not affected (A-7) | `-****` |
| `ASLD` (= `LSLD`) | `05` | 3 | `D ← D << 1`, C ← bit 15, V ← N⊕C after the shift (A-10, A-55) | `-****` |
| `LDD` | `CC` `DC` `EC` `FC` | 3/4/5/5 | `D ← M:M+1` (A-51) | `-**0-` |
| `LSRD` | `04` | 3 | `D ← D >> 1`, C ← bit 0, N ← 0, V ← N⊕C = C (A-57) | `-0***` |
| `MUL` | `3D` | 10 | `D ← A × B`, unsigned 8×8→16; **only C changes: C ← bit 7 of B**, the low result byte, so that a following `ADCA #0` rounds (A-58) | `----*` |
| `PSHX` | `3C` | 4 | push X — **IXL first, then IXH** (A-63), so the stack holds high:low in ascending order | `-----` |
| `PULX` | `38` | 5 | pull X — IXH first, then IXL (A-65) | `-----` |
| `STD` | `DD` `ED` `FD` (`CD`‡) | 4/5/5 | `M:M+1 ← D` (A-76) | `-**0-` |
| `SUBD` | `83` `93` `A3` `B3` | 4/5/6/6 | `D ← D − M:M+1` (A-80) | `-****` |

Plus two behavioural changes on opcodes the 6800 already had:

- **`CPX`'s flags — the one documented semantic difference.** Settled from the
  manuals on 2026-09-18:
  - **MC6800** (M68PRM p. A-33): `CPX` is two byte compares, `IXH − M` and
    `IXL − (M+1)`. **Z** is set only if *both* byte results are zero, so it
    reflects all sixteen bits; **N** and **V** come from the high-byte
    subtraction alone (`N = RH7`, `V = IXH7·¬M7·¬RH7 + ¬IXH7·M7·RH7`), and the
    manual adds that they are "not intended for conditional branching";
    **C is not affected**. There is no borrow from the low byte into the high
    byte, so N and V can differ from a true 16-bit compare.
  - **MC6801/6803** (M6801RM p. A-39): "a 16 bit subtract of (M:M+1) from the
    index register", with **N, Z, V and C all set** from the 16-bit result,
    C being the borrow. M6801RM §4.3.3.3 says this is new: on the MC6801
    "internal processing has been modified such that it can be used for
    branching similar to the single byte comparisons", with a `CPX` followed
    by `BHI` as its example — which works only because C is now set.
  - **MAME 0.285 models both correctly**, with two handler sets: the 6800's
    `m6800_insn[]` uses `cmpx_im`/`_di`/`_ix`/`_ex` (`6800ops.hxx:1093`, `1436`
    and neighbours), which set N and V from the high-byte subtraction, Z from
    the 16-bit difference and leave C alone; the 6801's `m6803_insn[]` uses
    `cpx_*` (`6800ops.hxx:1107`), a 16-bit subtract with `SET_FLAGS16`. (An
    earlier version of this page said MAME shared one handler and was wrong
    for the 6800; that came from reading only the 6801 table and was itself
    wrong.)
  - The extra work costs the 6801 a cycle: `CPX` is the only instruction that
    is **slower** on the 6801 (4/5/6/6 against 3/4/5/6).
- **Speed.** The 6801 is not just "the 6800 plus instructions": among the
  opcodes both manuals document, **72 are faster** on the 6801 and the three
  non-indexed `CPX` forms are slower; `TAP`/`TPA` and every other inherent
  two-cycle instruction are unchanged. See [timing.md](timing.md).

### DAA and the half-carry

`DAA` ($19, inherent, 2 cycles) exists to fix up a BCD addition. M68PRM
pp. A-34/A-35 (and M6801RM p. A-40) give it as a nine-row table of C, the
upper nibble, H and the lower nibble; this rule, which is MAME's `daa`,
reproduces that table on all 384 BCD cases it covers (checked 2026-09-18):

```
low  = A & $0F
high = A & $F0
cf = 0
if low > 9 or H = 1:                cf |= $06
if high > $80 and low > 9:          cf |= $60
if high > $90 or C = 1:             cf |= $60
A ← A + cf;  C ← C or (carry out);  N, Z from the result
```

Three things a core must get right:

1. **C is sticky.** `DAA` never clears C: every table row with C = 1 before
   has C = 1 after, and `CLR_NZV` in MAME's handler keeps the carry from the
   preceding add, then ORs in its own. BCD `$99 + $99` leaves A = `$32`, C = 1,
   H = 1; `DAA` adds `$66`, giving `$98` with no carry out of its own, and C
   stays 1 — the correct decimal 198.
2. **H must be right or `DAA` is wrong.** H is set only by `ADDA`, `ADDB`,
   `ADCA`, `ADCB` and `ABA`: it is the carry out of bit 3, i.e.
   `((a ^ m ^ result) & $10) != 0`. Nothing else — not `SUBA`, not `INCA`,
   not the 6801's `ADDD` — touches it.
3. **V after `DAA` is "Not defined"** (M68PRM p. A-34, M6801RM p. A-40); MAME
   clears it. See [undocumented-behavior.md](undocumented-behavior.md).
4. **H is not affected** by `DAA` itself (both manuals), and neither is it by
   any subtract, compare, shift or `NEG`.

`DAA` only corrects **additions**. There is no decimal-subtract fixup on this
family; 6800 code subtracts BCD by nines-complement addition.

## Interrupts, reset and the vector table

Four vectors on the 6800, eight on the 6801/6803, all at the top of the map:

| Address | 6800 | 6801/6803 | Priority |
| --- | --- | --- | --- |
| `$FFF0` | (ordinary memory) | **SCI** — serial receive/transmit | lowest |
| `$FFF2` | (ordinary memory) | **TOF** — timer overflow | |
| `$FFF4` | (ordinary memory) | **OCF** — timer output compare | |
| `$FFF6` | (ordinary memory) | **ICF** — timer input capture | |
| `$FFF8` | **IRQ1** | IRQ1 (the external pin) | |
| `$FFFA` | **SWI** | SWI | |
| `$FFFC` | **NMI** | NMI | |
| `$FFFE` | **RESET** | RESET | highest |

The four 6801 peripheral vectors sit **below** `$FFF8` and are taken in the
order ICF > OCF > TOF > SCI, all of them gated by the I bit and each by its
own enable bit in the timer/SCI control registers (M6801RM §4.4). A core that
only implements the instruction set does not need them; the **host** owns the
timer and the SCI and raises the request. This project's contract puts them on
the host side: `m6800-python` will expose an interrupt-request input per
vector and let the host decide when to assert it.

### The stack frame

`IRQ`, `NMI`, `SWI` and `WAI` all push the same seven bytes, in this order,
each write decrementing SP:

```
   SP after entry → +0  CC
                    +1  B
                    +2  A
                    +3  IXH
                    +4  IXL
                    +5  PCH
                    +6  PCL      ← SP before entry pointed here + 1
```

so the pushes happen PCL, PCH, IXL, IXH, A, B, CC and `RTI` pulls them back in
the reverse order. **Verified in a real run**: in the Drag Race trace
(`docs/mame-oracle.md`) SP goes `$FD → $F6` across an IRQ entry, a drop of
seven, and CC goes `$C8 → $D0` — I set, the rest preserved.

### Entry rules

- `IRQ1` is taken between instructions when the pin is low **and I = 0**. Entry
  pushes the frame, sets I, and loads PC from `$FFF8`.
- `NMI` is edge-triggered and ignores I. Same frame, sets I, vector `$FFFC`.
  NMI has priority over IRQ1.
- `SWI` ($3F, 12 cycles) pushes the frame, sets I, vector `$FFFA`. It is an
  instruction, so it is never "pending".
- **Entry costs 12 cycles on both parts**, the same as `SWI`. MCSDD's MC6800
  data sheet, Figure 13 "Interrupt Timing" (printed p. 17), numbers them: the
  next opcode is fetched and discarded, one internal cycle, seven pushes, one
  internal cycle in which I is set, and the two vector reads; the routine's
  first opcode follows. M6801RM §5.3 says it in words — "the interrupt
  sequence requires 12 MPU E-cycles to complete once it has begun" — with the
  cycle-by-cycle Figure 5-12 (p. 5-14). The **13** often quoted is a
  *response time*: M6801RM gives 13 cycles from `NMI` going active to the
  routine's first fetch (one cycle to recognise it, then 12) and 14 for `IRQ1`,
  whose recognition adds a synchronising cycle. MAME charges 12, as measured
  in [mame-oracle.md](mame-oracle.md).
- **`CLI` and `TAP` delay recognition by one instruction.** A pending `IRQ`
  unmasked by `CLI` is not taken until the instruction *after* the `CLI` has
  run. For the MC6801 this is stated exactly (M6801RM §5.4.1.1-5.4.1.3,
  pp. 5-18/5-19): clearing I goes through a buffer, `ITMP`, and lands one
  cycle late, so "assuming the I-bit is not already clear … the instruction
  following CLI will always be executed prior to servicing any maskable
  interrupt"; `SEI` "is not delayed"; `TAP` always lets the next instruction
  run, even another `TAP`; and after `RTI` the delay "is absorbed by the
  remaining cycles of the instruction", so an `IRQ` still pending is taken
  straight after `RTI`. **The MC6800's `CLI` is different**, and Motorola says
  so in APPS (the *M6800 Microprocessor Applications Manual*, p. A-13, Q15):
  "If the opcode of the instruction immediately preceding the CLI instruction
  has a zero in its least significant bit position, a pending interrupt will
  be recognized as soon as execution of CLI is complete. If there was a one
  in the least significant bit position of the previous instruction's opcode,
  the instruction following the CLI will be executed before the pending
  interrupt is recognized" — which is why the manual tells programmers to
  write `NOP; CLI; WAI`. The core follows it on `M6800` and the M6801RM rule
  on `M6803`. APPS agrees about `RTI` (p. A-12, Q12: the `IRQ` "will be
  serviced prior to the instruction" after it) and says nothing about a
  `TAP` delay on the MC6800, so the core applies the 6801's `TAP` rule there,
  **inferred**. MAME 0.285 encodes the 6801 rules for both parts, so on an
  MC6800 after an even opcode it delays an `IRQ` the part would take at once: `cli` executes the next opcode
  inline via `execute_one()` **only if I was actually set** before the `CLI`,
  then checks the lines; `tap` always does, with the comment "TAP temporarily
  sets the I flag and blocks IRQ until the next opcode (if the next opcode is
  TAP, IRQ is blocked again)"; `sei` does neither
  (`6800ops.hxx:80-92`, `135-144`, `146-151`). MAME 0.261 instead ran the
  extra instruction for all three unconditionally — **this is the one part of
  the 6800 core that changed between those two releases**, so a document
  derived from the wrong tree gets it wrong. This project cites 0.285, the
  version installed here ([validation.md](validation.md)).
- Reset sets I ("during the restart routine, the interrupt mask bit is set",
  MCSDD's MC6800 data sheet, printed p. 26), clears nothing else that is
  specified, and loads PC from `$FFFE`. A, B, IX and SP are **undefined** after reset on real silicon. MAME
  leaves them at 0 and sets CC to `$D0` (`m6800.cpp:577-585`); the trace
  confirms `1200 0 0 0 0 D0 0 0` as the first line. A core should expose reset
  state as explicitly undefined and let the host choose, but matching MAME's
  zeros is what makes trace comparison possible.

### WAI

`WAI` ($3E, 9 cycles) is the reason this family has a low-latency interrupt
path. It **pushes the whole frame first**, then halts (on the 6800 with the
bus released),
and when an interrupt arrives the CPU only has to set I and fetch the vector —
the stacking has already happened. Consequences a core must model:

- The frame is on the stack *before* the wait, so an interrupt taken out of
  `WAI` must **not** push again. MAME's `enter_interrupt` charges 4 cycles in
  the `WAI` case and 12 otherwise (`m6800.cpp:449-473`).
- **The 4 is Motorola's on both parts.** MC6800: "Four MPU cycles are
  required to start the interrupt sequence after a WAI instruction" (APPS
  p. A-14, Q20). MC6801: M6801RM §5.4.2 (pp. 5-19 to 5-21, Figure 5-15)
  gives five cycles from `NMI` to the routine's first fetch out of `WAI` and
  six for `IRQ1`, which on the accounting that makes the ordinary case
  13 = 1 + 12 is 4 cycles of sequence. (Before APPS was read, this page
  guessed 5 for the MC6800 from MCSDD's Figure 14; the manual's own answer is
  4.)
- If I = 1 and only `IRQ` is pending, `WAI` waits forever (until `NMI` or
  reset). MAME's `wai` handler calls `check_irq_lines()` immediately and, if
  still waiting, `eat_cycles()` — it burns the rest of the timeslice
  (`6800ops.hxx:458-475`).
- After the interrupt, `RTI` restores CC with I as it was, so execution
  resumes at the instruction after the `WAI`.

The 6801/6803 add `SLP` only on the Hitachi parts; on Motorola's 6801 `WAI` is
still the only halt instruction.

## The embedding contract

Same as `z80-python` and `6502-python`. The host owns memory and I/O
(`src/m6800_python/cpu.py`; `scripts/williams_sound.py` is a complete host):

```python
from m6800_python import M6800, M6803   # also M6802/M6808 (= M6800), M6801 (= M6803)

cpu = M6800(bus.read, bus.write)          # read_byte(address) -> int, write_byte(address, value)
cpu.reset()                               # I set, other flags clear, PC from $FFFE
while True:
    cycles = cpu.step()                   # one instruction, or one interrupt entry
    bus.tick(cycles)                      # host advances timers, video, PIAs
    cpu.irq = bus.irq_level               # sampled at the next instruction boundary
```

- `step()` executes exactly one instruction **or** one interrupt-entry
  sequence and returns the cycles it took: the manual's count for the opcode,
  12 for an interrupt entry, 4 for one out of `WAI`, and 1 for each step spent
  waiting in `WAI` or halted by HCF.
- `A`, `B`, `X`, `SP`, `PC`, `CC` are plain attributes, which the host may
  read and set; keep CC bits 7-6 set. On `M6803`, `D` is a property over
  `A:B`.
- Inputs: `irq` is a level (`True` while the line is asserted); `nmi` is
  edge-triggered, recognised when it goes from `False` to `True` at a
  boundary, and `pulse_nmi()` latches an edge directly. On `M6803`, `irq2`
  holds the vector of the highest-priority pending on-chip request (`$FFF6`
  input capture, `$FFF4` output compare, `$FFF2` timer overflow, `$FFF0`
  SCI) or `None`; `irq` outranks it. The timer, SCI and ports themselves are
  the host's.
- Interrupt timing: `NMI` first, then `IRQ` if I is clear — except in the
  step after a `TAP`, or after a `CLI` that holds interrupts off (always on
  the 6801, only after an odd opcode on the MC6800; see "Entry rules").
- State flags: `waiting` is `True` inside `WAI`; `halted` after HCF, cleared
  only by `reset()`.
- `undocumented=` chooses what unassigned opcodes do: `"strict"` (default:
  HCF halts, the rest raise `UndocumentedOpcode`), `"measured"` (what Wheeler
  1977 and Doc TB 2019 observed), `"mame"` (MAME 0.285's guesses, for trace
  replay). See [undocumented-behavior.md](undocumented-behavior.md).
- Not modelled: the MC6800's dummy bus reads (the core makes only the reads
  and writes an instruction needs, as MAME does), interrupt races inside an
  instruction ([timing.md](timing.md)), and HCF's bus activity.
- The core never reaches for a clock, a timer, a PIA or a file.
