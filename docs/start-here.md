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

Those two totals are not quoted from anywhere — they fall out of MAME's tables
once its inventions are removed, which is itself a check that the inventions
have all been found. MAME treats **203** opcodes as legal on the 6800; remove
the six it should not (`$21`, `$87`, `$8F`, `$9D`, `$C7`, `$CF`) and exactly
**197** remain, Motorola's documented count. MAME treats **225** as legal on
the 6801/6803; remove the five it should not (`$87`, `$8F`, `$C7`, `$CD`,
`$CF`) and **220** remain.

**How to read the table.** Each cell is `` `opcode` bytes/cycles ``. Where the
6800 and the 6801/6803 differ, both appear as `6800 · 6801`. A cell marked
**†** exists only on the 6801/6803. A cell marked **‡** is an opcode Motorola
does **not** assign on the part in question — `$21` (`BRN`) and `$9D`
(`JSR` direct) are real 6801 instructions that MAME wrongly allows on the
6800; the store-immediate slots are assigned on neither. MAME executes them
all anyway; [undocumented-behavior.md](undocumented-behavior.md) says what it
does and what is known about the real part.

Flags use Motorola's Appendix A notation over **H N Z V C** (the I bit is not
in this column): `*` affected, `-` unaffected, `0` cleared, `1` set, `?`
undefined, `#` set directly from the operand (`TAP`), `@` a special rule given
in the text (`MUL`: C ← bit 7 of the low result byte).

Opcodes, byte counts and cycle counts below were extracted mechanically from
MAME's `cycles_6800[]` (`m6800.cpp:251-271`), `cycles_6803[]`
(`m6801.cpp:136-156`), `m6800_insn[]`, `m6803_insn[]` and the shared
disassembler table `6800dasm.cpp:43`; the flag column from the per-handler
comments in `6800ops.hxx`. **They agree with M68PRM Appendix A and M6801RM
Appendix A where the build session has checked them, and the manuals are the
judge if they ever disagree.** Re-derive the table with
`scripts/dump_mame_tables.py` after any MAME upgrade.

| Mnemonic | Operation | IMM | DIR | IDX | EXT | INH / REL | HNZVC |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **ABA** | A ← A + B |  |  |  |  | `1B` 1/2 | `*****` |
| **ABX** | X ← X + B (B unsigned) |  |  |  |  | `3A` 1/3† | `-----` |
| **ADCA** | A ← A + M + C | `89` 2/2 | `99` 2/3 | `A9` 2/5 · 4 | `B9` 3/4 |  | `*****` |
| **ADCB** | B ← B + M + C | `C9` 2/2 | `D9` 2/3 | `E9` 2/5 · 4 | `F9` 3/4 |  | `*****` |
| **ADDA** | A ← A + M | `8B` 2/2 | `9B` 2/3 | `AB` 2/5 · 4 | `BB` 3/4 |  | `*****` |
| **ADDB** | B ← B + M | `CB` 2/2 | `DB` 2/3 | `EB` 2/5 · 4 | `FB` 3/4 |  | `*****` |
| **ADDD** | D ← D + M:M+1 | `C3` 3/4† | `D3` 2/5† | `E3` 2/6† | `F3` 3/6† |  | `-****` |
| **ANDA** | A ← A ∧ M | `84` 2/2 | `94` 2/3 | `A4` 2/5 · 4 | `B4` 3/4 |  | `-**0-` |
| **ANDB** | B ← B ∧ M | `C4` 2/2 | `D4` 2/3 | `E4` 2/5 · 4 | `F4` 3/4 |  | `-**0-` |
| **ASL** | M ← M << 1, C ← b7 |  |  | `68` 2/7 · 6 | `78` 3/6 |  | `?****` |
| **ASLA** | A ← A << 1, C ← b7 |  |  |  |  | `48` 1/2 | `?****` |
| **ASLB** | B ← B << 1, C ← b7 |  |  |  |  | `58` 1/2 | `?****` |
| **ASLD** | D ← D << 1, C ← b15 |  |  |  |  | `05` 1/3† | `?****` |
| **ASR** | M ← M >> 1 arithmetic |  |  | `67` 2/7 · 6 | `77` 3/6 |  | `?**-*` |
| **ASRA** | A ← A >> 1 arithmetic |  |  |  |  | `47` 1/2 | `?**-*` |
| **ASRB** | B ← B >> 1 arithmetic |  |  |  |  | `57` 1/2 | `?**-*` |
| **BCC** | branch if C=0 |  |  |  |  | `24` 2/4 · 3 | `-----` |
| **BCS** | branch if C=1 |  |  |  |  | `25` 2/4 · 3 | `-----` |
| **BEQ** | branch if Z=1 |  |  |  |  | `27` 2/4 · 3 | `-----` |
| **BGE** | branch if N⊕V=0 |  |  |  |  | `2C` 2/4 · 3 | `-----` |
| **BGT** | branch if Z∨(N⊕V)=0 |  |  |  |  | `2E` 2/4 · 3 | `-----` |
| **BHI** | branch if C∨Z=0 |  |  |  |  | `22` 2/4 · 3 | `-----` |
| **BITA** | A ∧ M, flags only | `85` 2/2 | `95` 2/3 | `A5` 2/5 · 4 | `B5` 3/4 |  | `-**0-` |
| **BITB** | B ∧ M, flags only | `C5` 2/2 | `D5` 2/3 | `E5` 2/5 · 4 | `F5` 3/4 |  | `-**0-` |
| **BLE** | branch if Z∨(N⊕V)=1 |  |  |  |  | `2F` 2/4 · 3 | `-----` |
| **BLS** | branch if C∨Z=1 |  |  |  |  | `23` 2/4 · 3 | `-----` |
| **BLT** | branch if N⊕V=1 |  |  |  |  | `2D` 2/4 · 3 | `-----` |
| **BMI** | branch if N=1 |  |  |  |  | `2B` 2/4 · 3 | `-----` |
| **BNE** | branch if Z=0 |  |  |  |  | `26` 2/4 · 3 | `-----` |
| **BPL** | branch if N=0 |  |  |  |  | `2A` 2/4 · 3 | `-----` |
| **BRA** | branch always |  |  |  |  | `20` 2/4 · 3 | `-----` |
| **BRN** | branch never (2-byte NOP) |  |  |  |  | `21`‡ 2/4 · 3 | `-----` |
| **BSR** | push PC, branch to subroutine |  |  |  |  | `8D` 2/8 · 6 | `-----` |
| **BVC** | branch if V=0 |  |  |  |  | `28` 2/4 · 3 | `-----` |
| **BVS** | branch if V=1 |  |  |  |  | `29` 2/4 · 3 | `-----` |
| **CBA** | A − B, flags only |  |  |  |  | `11` 1/2 | `-****` |
| **CLC** | C ← 0 |  |  |  |  | `0C` 1/2 | `----0` |
| **CLI** | I ← 0 |  |  |  |  | `0E` 1/2 | `-----` |
| **CLR** | M ← 0 |  |  | `6F` 2/7 · 6 | `7F` 3/6 |  | `-0100` |
| **CLRA** | A ← 0 |  |  |  |  | `4F` 1/2 | `-0100` |
| **CLRB** | B ← 0 |  |  |  |  | `5F` 1/2 | `-0100` |
| **CLV** | V ← 0 |  |  |  |  | `0A` 1/2 | `---0-` |
| **CMPA** | A − M, flags only | `81` 2/2 | `91` 2/3 | `A1` 2/5 · 4 | `B1` 3/4 |  | `?****` |
| **CMPB** | B − M, flags only | `C1` 2/2 | `D1` 2/3 | `E1` 2/5 · 4 | `F1` 3/4 |  | `?****` |
| **COM** | M ← ¬M |  |  | `63` 2/7 · 6 | `73` 3/6 |  | `-**01` |
| **COMA** | A ← ¬A |  |  |  |  | `43` 1/2 | `-**01` |
| **COMB** | B ← ¬B |  |  |  |  | `53` 1/2 | `-**01` |
| **CPX** | X − M:M+1, flags only | `8C` 3/3 · 4 | `9C` 2/4 · 5 | `AC` 2/6 | `BC` 3/5 · 6 |  | `-***-` |
| **DAA** | decimal adjust A after ADD/ADC/ABA |  |  |  |  | `19` 1/2 | `-**0*` |
| **DEC** | M ← M − 1 |  |  | `6A` 2/7 · 6 | `7A` 3/6 |  | `-***-` |
| **DECA** | A ← A − 1 |  |  |  |  | `4A` 1/2 | `-***-` |
| **DECB** | B ← B − 1 |  |  |  |  | `5A` 1/2 | `-***-` |
| **DES** | SP ← SP − 1 |  |  |  |  | `34` 1/4 · 3 | `-----` |
| **DEX** | X ← X − 1 |  |  |  |  | `09` 1/4 · 3 | `--*--` |
| **EORA** | A ← A ⊻ M | `88` 2/2 | `98` 2/3 | `A8` 2/5 · 4 | `B8` 3/4 |  | `-**0-` |
| **EORB** | B ← B ⊻ M | `C8` 2/2 | `D8` 2/3 | `E8` 2/5 · 4 | `F8` 3/4 |  | `-**0-` |
| **INC** | M ← M + 1 |  |  | `6C` 2/7 · 6 | `7C` 3/6 |  | `-***-` |
| **INCA** | A ← A + 1 |  |  |  |  | `4C` 1/2 | `-***-` |
| **INCB** | B ← B + 1 |  |  |  |  | `5C` 1/2 | `-***-` |
| **INS** | SP ← SP + 1 |  |  |  |  | `31` 1/4 · 3 | `-----` |
| **INX** | X ← X + 1 |  |  |  |  | `08` 1/4 · 3 | `--*--` |
| **JMP** | PC ← EA |  |  | `6E` 2/4 · 3 | `7E` 3/3 |  | `-----` |
| **JSR** | push PC, PC ← EA |  | `9D`‡ 2/6 · 5 | `AD` 2/8 · 6 | `BD` 3/9 · 6 |  | `-----` |
| **LDAA** | A ← M | `86` 2/2 | `96` 2/3 | `A6` 2/5 · 4 | `B6` 3/4 |  | `-**0-` |
| **LDAB** | B ← M | `C6` 2/2 | `D6` 2/3 | `E6` 2/5 · 4 | `F6` 3/4 |  | `-**0-` |
| **LDD** | D ← M:M+1 | `CC` 3/3† | `DC` 2/4† | `EC` 2/5† | `FC` 3/5† |  | `-**0-` |
| **LDS** | SP ← M:M+1 | `8E` 3/3 | `9E` 2/4 | `AE` 2/6 · 5 | `BE` 3/5 |  | `-**0-` |
| **LDX** | X ← M:M+1 | `CE` 3/3 | `DE` 2/4 | `EE` 2/6 · 5 | `FE` 3/5 |  | `-**0-` |
| **LSR** | M ← M >> 1 logical |  |  | `64` 2/7 · 6 | `74` 3/6 |  | `-0*-*` |
| **LSRA** | A ← A >> 1 logical |  |  |  |  | `44` 1/2 | `-0*-*` |
| **LSRB** | B ← B >> 1 logical |  |  |  |  | `54` 1/2 | `-0*-*` |
| **LSRD** | D ← D >> 1 logical |  |  |  |  | `04` 1/3† | `-0*-*` |
| **MUL** | D ← A × B (unsigned) |  |  |  |  | `3D` 1/10† | `--*-@` |
| **NEG** | M ← 0 − M |  |  | `60` 2/7 · 6 | `70` 3/6 |  | `?****` |
| **NEGA** | A ← 0 − A |  |  |  |  | `40` 1/2 | `?****` |
| **NEGB** | B ← 0 − B |  |  |  |  | `50` 1/2 | `?****` |
| **NOP** | no operation |  |  |  |  | `01` 1/2 | `-----` |
| **ORAA** | A ← A ∨ M | `8A` 2/2 | `9A` 2/3 | `AA` 2/5 · 4 | `BA` 3/4 |  | `-**0-` |
| **ORAB** | B ← B ∨ M | `CA` 2/2 | `DA` 2/3 | `EA` 2/5 · 4 | `FA` 3/4 |  | `-**0-` |
| **PSHA** | push A |  |  |  |  | `36` 1/4 · 3 | `-----` |
| **PSHB** | push B |  |  |  |  | `37` 1/4 · 3 | `-----` |
| **PSHX** | push X (low byte first) |  |  |  |  | `3C` 1/4† | `-----` |
| **PULA** | pull A |  |  |  |  | `32` 1/4 | `-----` |
| **PULB** | pull B |  |  |  |  | `33` 1/4 | `-----` |
| **PULX** | pull X |  |  |  |  | `38` 1/5† | `-----` |
| **ROL** | M ← rotate left through C |  |  | `69` 2/7 · 6 | `79` 3/6 |  | `-****` |
| **ROLA** | A ← rotate left through C |  |  |  |  | `49` 1/2 | `-****` |
| **ROLB** | B ← rotate left through C |  |  |  |  | `59` 1/2 | `-****` |
| **ROR** | M ← rotate right through C |  |  | `66` 2/7 · 6 | `76` 3/6 |  | `-**-*` |
| **RORA** | A ← rotate right through C |  |  |  |  | `46` 1/2 | `-**-*` |
| **RORB** | B ← rotate right through C |  |  |  |  | `56` 1/2 | `-**-*` |
| **RTI** | pull CC,B,A,X,PC |  |  |  |  | `3B` 1/10 | `#####` |
| **RTS** | pull PC |  |  |  |  | `39` 1/5 | `-----` |
| **SBA** | A ← A − B |  |  |  |  | `10` 1/2 | `-****` |
| **SBCA** | A ← A − M − C | `82` 2/2 | `92` 2/3 | `A2` 2/5 · 4 | `B2` 3/4 |  | `?****` |
| **SBCB** | B ← B − M − C | `C2` 2/2 | `D2` 2/3 | `E2` 2/5 · 4 | `F2` 3/4 |  | `?****` |
| **SEC** | C ← 1 |  |  |  |  | `0D` 1/2 | `----1` |
| **SEI** | I ← 1 |  |  |  |  | `0F` 1/2 | `-----` |
| **SEV** | V ← 1 |  |  |  |  | `0B` 1/2 | `---1-` |
| **STAA** | M ← A | `87`‡ 2/3 · 2 | `97` 2/4 · 3 | `A7` 2/6 · 4 | `B7` 3/5 · 4 |  | `-**0-` |
| **STAB** | M ← B | `C7`‡ 2/3 · 2 | `D7` 2/4 · 3 | `E7` 2/6 · 4 | `F7` 3/5 · 4 |  | `-**0-` |
| **STD** | M:M+1 ← D | `CD`‡ 3/4† | `DD` 2/4† | `ED` 2/5† | `FD` 3/5† |  | `-**0-` |
| **STS** | M:M+1 ← SP | `8F`‡ 3/4 · 3 | `9F` 2/5 · 4 | `AF` 2/7 · 5 | `BF` 3/6 · 5 |  | `-**0-` |
| **STX** | M:M+1 ← X | `CF`‡ 3/4 · 3 | `DF` 2/5 · 4 | `EF` 2/7 · 5 | `FF` 3/6 · 5 |  | `-**0-` |
| **SUBA** | A ← A − M | `80` 2/2 | `90` 2/3 | `A0` 2/5 · 4 | `B0` 3/4 |  | `?****` |
| **SUBB** | B ← B − M | `C0` 2/2 | `D0` 2/3 | `E0` 2/5 · 4 | `F0` 3/4 |  | `?****` |
| **SUBD** | D ← D − M:M+1 | `83` 3/4† | `93` 2/5† | `A3` 2/6† | `B3` 3/6† |  | `-****` |
| **SWI** | software interrupt, vector $FFFA |  |  |  |  | `3F` 1/12 | `-----` |
| **TAB** | B ← A |  |  |  |  | `16` 1/2 | `-**0-` |
| **TAP** | CC ← A |  |  |  |  | `06` 1/2 | `#####` |
| **TBA** | A ← B |  |  |  |  | `17` 1/2 | `-**0-` |
| **TPA** | A ← CC |  |  |  |  | `07` 1/2 | `-----` |
| **TST** | M − 0, flags only |  |  | `6D` 2/7 · 6 | `7D` 3/6 |  | `-**0-` |
| **TSTA** | A − 0, flags only |  |  |  |  | `4D` 1/2 | `-**0-` |
| **TSTB** | B − 0, flags only |  |  |  |  | `5D` 1/2 | `-**0-` |
| **TSX** | X ← SP + 1 |  |  |  |  | `30` 1/4 · 3 | `-----` |
| **TXS** | SP ← X − 1 |  |  |  |  | `35` 1/4 · 3 | `-----` |
| **WAI** | stack state, wait for interrupt |  |  |  |  | `3E` 1/9 | `-----` |

### What the 6801/6803 add

Ten mnemonics, all of them about the D accumulator or the index register
(M6801RM §2, "New Instructions"):

| Mnemonic | Opcodes | Cycles | Operation | HNZVC |
| --- | --- | --- | --- | --- |
| `ABX` | `3A` | 3 | `X ← X + B`, B unsigned, no flags | `-----` |
| `ADDD` | `C3` `D3` `E3` `F3` | 4/5/6/6 | `D ← D + M:M+1` | `-****` |
| `ASLD` (= `LSLD`) | `05` | 3 | `D ← D << 1`, C ← bit 15 | `?****` |
| `LDD` | `CC` `DC` `EC` `FC` | 3/4/5/5 | `D ← M:M+1` | `-**0-` |
| `LSRD` | `04` | 3 | `D ← D >> 1`, C ← bit 0, N ← 0, V ← N⊕C | `-0**` |
| `MUL` | `3D` | 10 | `D ← A × B`, unsigned 8×8→16; **C ← bit 7 of B**, i.e. of the low result byte, so that a following `ADCA #0` rounds | `--*-@` |
| `PSHX` | `3C` | 4 | push X — **low byte first**, so the stack holds high:low in ascending order | `-----` |
| `PULX` | `38` | 5 | pull X | `-----` |
| `STD` | `DD` `ED` `FD` (`CD`‡) | 4/5/5 | `M:M+1 ← D` | `-**0-` |
| `SUBD` | `83` `93` `A3` `B3` | 4/5/6/6 | `D ← D − M:M+1` | `-****` |

Plus two behavioural changes on opcodes the 6800 already had:

- **`CPX`'s flags.** `CPX` computes a 16-bit difference and, on **both**
  parts, leaves C alone — there is no borrow out of `CPX`, which is why the
  documented idiom after `CPX` is `BEQ`/`BNE` and not `BCC`/`BCS`. The
  long-standing account in the emulator community is that on the **MC6800**
  only Z reflects all sixteen bits while N and V come from the high-byte
  subtraction alone, and that the **MC6801** made N and V correct.
  **`[unverified here]`** — this session could not render the scanned manuals
  (no PDF rasteriser on this machine, see [validation.md](validation.md)), so
  the claim is carried forward unchecked. MAME uses one shared `cmpx` handler
  for both parts and therefore models no difference at all
  (`6800ops.hxx`, `cmpx_*`), which is either MAME being wrong or the account
  being wrong. **Milestone 1 of the handoff resolves this against M68PRM's
  CPX page and M6801RM Appendix A before any `CPX` test is written.**
- **`TAP`/`TPA` and the branches, index and stack operations get faster.** The
  6801 is not just "the 6800 plus instructions": 79 shared opcodes have
  different cycle counts. See [timing.md](timing.md).

### DAA and the half-carry

`DAA` ($19, inherent, 2 cycles) exists to fix up a BCD addition. Its rule
(M68PRM, DAA; MAME `6800ops.hxx`, `daa`) adds a correction factor to A:

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

1. **C is sticky.** `DAA` never clears C — `CLR_NZV` in MAME's handler keeps
   the carry from the preceding add, then ORs in its own. A BCD add of
   `$99 + $01` leaves C set through the `DAA`.
2. **H must be right or `DAA` is wrong.** H is set only by `ADDA`, `ADDB`,
   `ADCA`, `ADCB` and `ABA`: it is the carry out of bit 3, i.e.
   `((a ^ m ^ result) & $10) != 0`. Nothing else — not `SUBA`, not `INCA`,
   not the 6801's `ADDD` — touches it.
3. **V after `DAA` is undefined in the manual**; MAME clears it. See
   [undocumented-behavior.md](undocumented-behavior.md).

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
- **`CLI` and `TAP` delay recognition by one instruction.** A pending `IRQ`
  unmasked by `CLI` is not taken until the instruction *after* the `CLI` has
  run. MAME 0.285 encodes this literally: `cli` executes the next opcode
  inline via `execute_one()` **only if I was actually set** before the `CLI`,
  then checks the lines; `tap` always does, with the comment "TAP temporarily
  sets the I flag and blocks IRQ until the next opcode (if the next opcode is
  TAP, IRQ is blocked again)"; `sei` does neither
  (`6800ops.hxx:80-92`, `135-144`, `146-151`). MAME 0.261 instead ran the
  extra instruction for all three unconditionally — **this is the one part of
  the 6800 core that changed between those two releases**, so a document
  derived from the wrong tree gets it wrong. This project cites 0.285, the
  version installed here ([validation.md](validation.md)).
- Reset sets I, clears nothing else that is specified, and loads PC from
  `$FFFE`. A, B, IX and SP are **undefined** after reset on real silicon. MAME
  leaves them at 0 and sets CC to `$D0` (`m6800.cpp:577-585`); the trace
  confirms `1200 0 0 0 0 D0 0 0` as the first line. A core should expose reset
  state as explicitly undefined and let the host choose, but matching MAME's
  zeros is what makes trace comparison possible.

### WAI

`WAI` ($3E, 9 cycles) is the reason this family has a low-latency interrupt
path. It **pushes the whole frame first**, then halts with the bus released,
and when an interrupt arrives the CPU only has to set I and fetch the vector —
the stacking has already happened. Consequences a core must model:

- The frame is on the stack *before* the wait, so an interrupt taken out of
  `WAI` must **not** push again. MAME's `enter_interrupt` charges 4 cycles in
  the `WAI` case and 12 otherwise (`m6800.cpp:449-473`).
- If I = 1 and only `IRQ` is pending, `WAI` waits forever (until `NMI` or
  reset). MAME's `wai` handler calls `check_irq_lines()` immediately and, if
  still waiting, `eat_cycles()` — it burns the rest of the timeslice
  (`6800ops.hxx:458-475`).
- After the interrupt, `RTI` restores CC with I as it was, so execution
  resumes at the instruction after the `WAI`.

The 6801/6803 add `SLP` only on the Hitachi parts; on Motorola's 6801 `WAI` is
still the only halt instruction.

## The embedding contract

Same as `z80-python` and `6502-python`. The host owns memory and I/O:

```python
cpu = M6800(read_byte=bus.read, write_byte=bus.write)   # or M6803(...)
cpu.reset()
while True:
    cycles = cpu.step()       # one instruction, or one interrupt entry
    bus.tick(cycles)          # host advances timers, video, PIAs
    cpu.irq = bus.irq_level   # sampled at the next instruction boundary
```

- `step()` executes exactly one instruction **or** one interrupt-entry
  sequence and returns the cycle count it consumed.
- `A`, `B`, `X`, `SP`, `PC`, `CC` are plain attributes; on the 6803 class `D`
  is a property over `A:B`.
- `nmi` is edge-sensitive, `irq` level-sensitive; both are sampled at
  instruction boundaries, with the `CLI`/`SEI`/`TAP` one-instruction delay
  applied.
- The core never reaches for a clock, a timer, a PIA or a file.
