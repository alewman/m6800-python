"""What the core does with opcodes Motorola does not assign.

Three policies, chosen per CPU with ``undocumented=``:

``"strict"`` (the default)
    Only what every source agrees on.  The HCF family halts until
    :meth:`reset`; every other unassigned opcode raises
    :class:`UndocumentedOpcode` with the CPU state unchanged, PC still
    pointing at the opcode.

``"measured"``
    ``"strict"`` plus the behaviours two people measured on real MC6800s
    (docs/undocumented-behavior.md), each cited on its line below: Gerry
    Wheeler, "Undocumented M6800 Instructions", *BYTE* 2(12), December 1977,
    pp. 46-47 (Table 1, Figure 1); and Doc TB, "Investigating the HCF (Halt &
    Catch Fire) instruction on Motorola 6800", x86.fr, 2019-07-17, an MC6800P
    at 1 MHz on a Universal Chip Analyzer.  Where neither source gives a cycle
    count, the count used is marked `[unverified]`.  Both warn that behaviour
    may differ between mask revisions and second sources.

``"mame"``
    MAME 0.285's behaviour, for replaying MAME traces: the store-immediate
    forms store into the byte after the opcode, `$21` and `$9D` act as their
    MC6801 meanings on the MC6800, and everything else is a 1-, 2- or 3-byte
    no-op costing MAME's ``XX`` = 4 cycles ("illegal opcode unknown cycle
    count").  MAME's guess, not the part's behaviour; `[unverified]`.

None of this applies to the MC6801/6803 except ``"mame"``: nobody has
published a measurement of that part's unassigned opcodes, so ``"measured"``
is ``"strict"`` there.

**HCF** is modelled as a halt only.  The bus activity during it -- the address
bus becomes a counter, reading every location in turn, starting about 64 ms
after the fetch and running at half the clock for `$9D`/`$DD` (Doc TB) -- is
not: each step in HCF costs one cycle and reads nothing.
"""

from collections.abc import Callable

from m6800_python._dispatch import MODES, Entry

POLICIES = ("strict", "measured", "mame")


class UndocumentedOpcode(Exception):
    """An opcode the part's manual does not assign was executed."""

    def __init__(self, opcode: int, address: int, part: str) -> None:
        super().__init__(
            f"undocumented {part} opcode ${opcode:02X} at ${address:04X}; its behaviour on "
            'silicon is unknown (undocumented="measured" or "mame" to run a published guess)'
        )
        self.opcode = opcode
        self.address = address
        self.part = part


#: MC6800 opcodes that lock the part up until RESET.  $9D and $DD are Wheeler's
#: HCF (p. 46) and Doc TB's clean counter; $FD is "exactly like" them at half
#: the rate; $CD and $ED also stop the CPU until a reset, with glitchy
#: address-line activity (Doc TB).
HCF_OPCODES = frozenset({0x9D, 0xDD, 0xFD, 0xCD, 0xED})

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
        # step() puts the opcode history back when this propagates, because
        # this policy promises the CPU state is left untouched.
        raise UndocumentedOpcode(opcode, address, part)

    return undocumented


def _hcf(self) -> None:
    self.halted = True


def _skip(length: int) -> Callable:
    def mame_illegal(self) -> None:
        self.PC = (self.PC + length - 1) & 0xFFFF

    return mame_illegal


# -- the measured MC6800 behaviours ("measured" policy) ----------------------


def _nba(self) -> None:
    # $14 "NBA": A <- A AND B, "setting the condition codes correctly", next
    # instruction at PC+1 (Wheeler, Table 1, p. 46) -- read here as ANDA's
    # rule, N and Z from the result, V cleared.  Doc TB saw the AND on a later
    # MC6800P but not on an early XC6800 prototype.
    self.A &= self.B
    self._nz8_v0(self.A)


def _nop(self) -> None:
    # $15: "treated as NOP, wasting 2 machine cycles.  Registers unchanged"
    # (Doc TB).
    pass


def _store_immediate(register: str, width: int) -> Callable:
    # Wheeler, Table 1 and Figure 1 (pp. 46-47): the store-immediate forms
    # skip the byte after the opcode -- a "hole", don't care -- store the
    # register at PC+2 (and PC+3), and continue after it: STAA/STAB # are three
    # bytes, STS/STX # four.  The flags are not described; this core sets them
    # as the documented stores do, N and Z from the value and V cleared
    # [unverified].
    def store(self) -> None:
        value = getattr(self, register)
        target = (self.PC + 1) & 0xFFFF  # PC is already past the opcode
        if width == 8:
            self._nz8_v0(value)
            self.write_byte(target, value)
        else:
            self._nz16_v0(value)
            self._write_word(target, value)
        self.PC = (self.PC + 1 + width // 8) & 0xFFFF

    return store


#: opcode: (handler, cycles).  Wheeler gives no execution times; the store
#: forms use the documented direct-mode store's count [unverified].
MEASURED_6800: dict[int, tuple[Callable, int]] = {
    0x14: (_nba, 2),  # 2 cycles: Doc TB
    0x15: (_nop, 2),  # Doc TB
    0x87: (_store_immediate("A", 8), 4),  # [unverified] cycles: STAA direct's
    0xC7: (_store_immediate("B", 8), 4),  # [unverified] cycles: STAB direct's
    0x8F: (_store_immediate("SP", 16), 5),  # [unverified] cycles: STS direct's
    0xCF: (_store_immediate("X", 16), 5),  # [unverified] cycles: STX direct's
}


def policy_entry(cls: type, part: int, policy: str) -> Callable[[int], Entry]:
    """The dispatch entry of every opcode ``part`` does not assign, under ``policy``."""
    if policy not in POLICIES:
        raise ValueError(f"undocumented= must be one of {POLICIES}, not {policy!r}")

    def entry(opcode: int) -> Entry:
        if policy == "mame":
            known = MAME_AS_INSTRUCTION[part].get(opcode)
            if known is not None:
                handler, mode, cycles = known
                ea = getattr(cls, MODES[mode]) if mode else None
                return (getattr(cls, "_op_" + handler), ea, cycles)
            length = MAME_ILLEGAL_LENGTH[part].get(opcode, 1)
            return (_skip(length), None, MAME_ILLEGAL_CYCLES)
        if part == 6800 and opcode in HCF_OPCODES:
            return (_hcf, None, 1)
        if policy == "measured" and part == 6800 and opcode in MEASURED_6800:
            handler, cycles = MEASURED_6800[opcode]
            return (handler, None, cycles)
        return (_trap(opcode, f"MC{part}"), None, 0)

    return entry
