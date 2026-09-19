# Disassembly

`disassemble(reader, address, *, part=6800, undocumented="strict")` decodes one
instruction without creating or touching a CPU. `reader` is called with 16-bit
addresses and must return bytes; `disassemble_bytes(data, address)` decodes from
a copied sequence whose first byte sits at `address`; `disassemble_range(reader,
address, count)` decodes consecutive instructions.

Each returns an immutable `Instruction`:

| Field | Meaning |
| --- | --- |
| `address`, `data` | where it is and the exact bytes it occupies |
| `mnemonic`, `operands` | Motorola mnemonic (`LDAA`, `CPX`, `BNE`) and operand texts |
| `mode` | `inherent`, `immediate`, `direct`, `indexed`, `extended`, `relative` or `data` |
| `target` | the absolute address a direct, extended or branch operand names, else `None` |
| `documented` | `False` when Motorola does not assign the opcode on this part |
| `size`, `next_address`, `text` | derived: byte count, the following address, printable text |

Debuggers and tools should consume the structured fields, not parse `text`.

## One table with the core

The decode table is built from the core's own opcode map (`_dispatch.OPCODES`)
and undocumented-opcode policies (`_undocumented`), so it cannot disagree with
what the core executes. Two tests hold it there: every documented opcode's length
and mnemonic equal the manuals' datasheet (`tests/datasheet.py`), and for every
opcode of both parts under all three policies that does not transfer control,
running it on the core moves PC exactly `size` bytes (`tests/test_disasm.py`).

It was also checked against MAME 0.285's own disassembler: every distinct ROM
instruction in the five replayed traces — 4,172 of them across Drag Race,
Knuckle Joe, Kid Niki, Bubble Bobble's MCU and Escape from the Lost World —
decodes to the same mnemonic and operands (`tests/test_disasm_mame.py`, run with
`pytest -m slow` where the traces exist). MAME spells a few mnemonics its own way
(`lda` for `LDAA`, `cmpx` for `CPX`); those are mapped.

## Syntax

Motorola's, as M68PRM chapter 4 writes it, in upper case with `$` hex:

| Mode | Example | Note |
| --- | --- | --- |
| inherent | `ABA`, `INCA`, `PSHX` | |
| immediate | `LDAA #$12`, `LDX #$1234` | two or four hex digits by operand size |
| direct | `LDAA $40` | always two digits |
| extended | `STAA $2000`, `STAA $0040` | always four digits, so `$0040` is extended, not direct |
| indexed | `LDAA $12,X` | the offset is unsigned: `$FF,X` is X+255 |
| relative | `BNE $1234` | the branch target, resolved, wrapping at 64K |

## Parts and undocumented opcodes

`part` is `6800`/`6802`/`6808` or `6801`/`6803` (also `"MC6803"` and the like):
`$3D` is `MUL` on a 6803 and unassigned on a 6800, `$9D` is `JSR` direct on one
and HCF on the other. `undocumented` follows the CPU policy of the same name
([undocumented-behavior.md](undocumented-behavior.md)):

| Bytes | `"strict"` | `"measured"` | `"mame"` |
| --- | --- | --- | --- |
| `02` | `FCB $02` | `FCB $02` | `FCB $02` |
| `9D 40` (6800) | `HCF` | `HCF` | `JSR $40` |
| `14` | `FCB $14` | `NBA` (Wheeler) | `FCB $14` |
| `87 EE 00` | `FCB $87` | `STAA #`, 3 bytes, target PC+2 (Wheeler's hole) | `STAA #$EE`, 2 bytes |
| `61 00` (6800) | `FCB $61` | `FCB $61` | `FCB $61,$00` (MAME skips 2) |

Undecodable bytes are shown as `FCB` data with `documented=False` rather than
raising, because real ROMs contain them (Drag Race runs `$02`) and a listing
has to get past them.

## Side-effect-free reads

Disassembly is observation. A real board's bus read can acknowledge an
interrupt or clear a PIA flag, so the library never reads through the CPU's
`read_byte`: pass a peek of the host's memory, as `DebugSession(peek_byte=...)`
does. If a region cannot be peeked, do not disassemble it through the bus.
