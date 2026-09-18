"""What the core does with opcodes Motorola does not assign.

Nobody has measured what a real MC6800 does with most of its 59 unassigned
opcodes (docs/undocumented-behavior.md), so by default this core refuses to
guess: executing one raises :class:`UndocumentedOpcode` with the CPU state
unchanged, PC still pointing at the opcode.  The exception is HCF.

**HCF** (`$9D` and `$DD` on the MC6800) is the one undocumented behaviour that
has been captured from silicon: after it the address bus counts up forever and
the part ignores everything but reset (Doc TB's 2019 Universal Chip Analyzer
measurement, docs/validation.md; Wheeler, *BYTE*, December 1977).  The core
models it as a halt that only :meth:`reset` clears.  The bus activity during the
halt is not modelled yet: each step in HCF costs one cycle and reads nothing.
`[unverified]` beyond "it halts until reset".

**MAME compatibility.**  With ``mame_compat=True`` every unassigned opcode
behaves as MAME 0.285 makes it behave -- the store-immediate forms store into
the instruction stream, `$21` and `$9D` act as their MC6801 meanings on the
MC6800, and everything else is skipped as a 1-, 2- or 3-byte no-op costing 4
cycles (MAME's ``XX`` sentinel, "illegal opcode unknown cycle count").  This
exists so that MAME traces can be replayed; it is MAME's guess, not the
part's behaviour, and is `[unverified]` throughout.
"""

from collections.abc import Callable

from m6800_python._dispatch import MODES, Entry


class UndocumentedOpcode(Exception):
    """An opcode the part's manual does not assign was executed."""

    def __init__(self, opcode: int, address: int, part: str) -> None:
        super().__init__(
            f"undocumented {part} opcode ${opcode:02X} at ${address:04X}; its behaviour on "
            "silicon is unknown (pass mame_compat=True to execute MAME 0.285's guess)"
        )
        self.opcode = opcode
        self.address = address
        self.part = part


#: The HCF opcodes of the MC6800 (M6800 only: on the MC6801 both are assigned).
HCF_OPCODES = frozenset({0x9D, 0xDD})

# MAME 0.285's handling of the opcodes Motorola does not assign, read from
# m6800_insn[]/m6803_insn[] and cycles_6800[]/cycles_6803[] (m6800.cpp,
# m6801.cpp).  Handler, addressing mode and cycles for the ones MAME treats as
# instructions; every other unassigned opcode is an "illegl" no-op of the
# listed length costing XX = 4 cycles.
MAME_AS_INSTRUCTION: dict[int, dict[int, tuple[str, str | None, int]]] = {
    6800: {
        0x21: ("brn", None, 4),
        0x87: ("staa", "imm8", 3),
        0x8F: ("sts", "imm16", 4),
        0x9D: ("jsr", "dir", 6),
        0xC7: ("stab", "imm8", 3),
        0xCF: ("stx", "imm16", 4),
    },
    6801: {
        0x87: ("staa", "imm8", 2),
        0x8F: ("sts", "imm16", 3),
        0xC7: ("stab", "imm8", 2),
        0xCD: ("std", "imm16", 4),  # MAME's own comment: "is this a legal instruction?"
        0xCF: ("stx", "imm16", 3),
    },
}
MAME_ILLEGAL_LENGTH: dict[int, dict[int, int]] = {
    # illegl2 and illegl3 in m6800_insn[]; every other illegal opcode is illegl1.
    6800: {
        **dict.fromkeys(
            (0x61, 0x62, 0x65, 0x6B, 0x83, 0x93, 0xA3, 0xC3, 0xD3, 0xDC, 0xDD, 0xE3, 0xEC, 0xED), 2
        ),
        **dict.fromkeys((0x71, 0x72, 0x75, 0x7B, 0xB3, 0xCC, 0xCD, 0xF3, 0xFC, 0xFD), 3),
    },
    6801: {},  # m6803_insn[] uses illegl1 throughout
}
MAME_ILLEGAL_CYCLES = 4


def _trap(opcode: int, part: str) -> Callable:
    def undocumented(self) -> None:
        address = (self.PC - 1) & 0xFFFF
        self.PC = address
        raise UndocumentedOpcode(opcode, address, part)

    return undocumented


def _hcf(self) -> None:
    self.halted = True


def _skip(length: int) -> Callable:
    def mame_illegal(self) -> None:
        self.PC = (self.PC + length - 1) & 0xFFFF

    return mame_illegal


def strict_entry(cls: type, part: int) -> Callable[[int], Entry]:
    """The default policy: HCF halts, every other unassigned opcode raises."""

    def entry(opcode: int) -> Entry:
        if part == 6800 and opcode in HCF_OPCODES:
            return (_hcf, None, 1)
        return (_trap(opcode, f"MC{part}"), None, 0)

    return entry


def mame_entry(cls: type, part: int) -> Callable[[int], Entry]:
    """The ``mame_compat=True`` policy: MAME 0.285's behaviour, unverified."""

    def entry(opcode: int) -> Entry:
        known = MAME_AS_INSTRUCTION[part].get(opcode)
        if known is not None:
            handler, mode, cycles = known
            ea = getattr(cls, MODES[mode]) if mode else None
            return (getattr(cls, "_op_" + handler), ea, cycles)
        length = MAME_ILLEGAL_LENGTH[part].get(opcode, 1)
        return (_skip(length), None, MAME_ILLEGAL_CYCLES)

    return entry
