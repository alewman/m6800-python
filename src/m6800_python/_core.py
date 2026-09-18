"""CPU state, fetch, effective-address and stack helpers.

Everything here is shared by the MC6800 and the MC6801/6803.  Sources are cited
as in docs/start-here.md: M68PRM is the MC6800 programming reference manual,
M6801RM the MC6801 reference manual, MCSDD the MC6800 system design data book.
"""

from collections.abc import Callable

# Condition code bits (M68PRM Appendix A, "Nomenclature", p. A-1).
H = 0x20  # half carry: carry out of bit 3 of an 8-bit add
I = 0x10  # interrupt mask
N = 0x08  # negative
Z = 0x04  # zero
V = 0x02  # two's complement overflow
C = 0x01  # carry / borrow

# Bits 7 and 6 of CC have no function and read as 1: TPA sets them in A and
# SWI/WAI push them set (M68PRM pp. A-67, A-72, A-76).
CC_FIXED = 0xC0

ReadByte = Callable[[int], int]
WriteByte = Callable[[int, int], None]


class CoreMixin:
    """Private implementation of CPU state and the helpers every handler uses."""

    def _init_core(self, read_byte: ReadByte, write_byte: WriteByte) -> None:
        self.read_byte = read_byte
        self.write_byte = write_byte
        # A, B, X and SP are undefined after reset on silicon (the manuals
        # specify only I and PC); zero matches MAME and makes traces comparable.
        self.A = 0
        self.B = 0
        self.X = 0
        self.SP = 0
        self.PC = 0
        self.CC = CC_FIXED | I
        # Interrupt inputs, sampled by step() at instruction boundaries.
        self.irq = False
        self.nmi = False
        self._nmi_previous = False
        self._nmi_pending = False
        # Set by CLI (when I was set) and TAP: the next instruction runs before
        # a maskable interrupt can be recognised (M6801RM section 5.4.1).
        self._irq_inhibit = False
        # WAI has stacked the machine state and is waiting (M68PRM p. A-76).
        self.waiting = False
        # HCF ($9D/$DD on the MC6800) has run; only reset() leaves this state.
        self.halted = False

    # -- fetch -------------------------------------------------------------

    def _fetch(self) -> int:
        value = self.read_byte(self.PC)
        self.PC = (self.PC + 1) & 0xFFFF
        return value

    def _fetch_word(self) -> int:
        high = self._fetch()  # the 6800 family is big-endian: high byte first
        return (high << 8) | self._fetch()

    def _read_word(self, address: int) -> int:
        high = self.read_byte(address)
        return (high << 8) | self.read_byte((address + 1) & 0xFFFF)

    def _write_word(self, address: int, value: int) -> None:
        self.write_byte(address, (value >> 8) & 0xFF)
        self.write_byte((address + 1) & 0xFFFF, value & 0xFF)

    # -- effective addresses (M68PRM chapter 4) ----------------------------
    # Every memory-mode handler receives an effective address, including the
    # immediate forms, whose "address" is the operand's own place in the
    # instruction stream.  The mode functions advance PC past the operand.

    def _ea_imm8(self) -> int:
        address = self.PC
        self.PC = (self.PC + 1) & 0xFFFF
        return address

    def _ea_imm16(self) -> int:
        address = self.PC
        self.PC = (self.PC + 2) & 0xFFFF
        return address

    def _ea_dir(self) -> int:
        return self._fetch()  # direct: page zero only, $0000-$00FF

    def _ea_ext(self) -> int:
        return self._fetch_word()

    def _ea_idx(self) -> int:
        # The offset is UNSIGNED: X+0 .. X+255, never backwards (M68PRM section 4.6).
        return (self.X + self._fetch()) & 0xFFFF

    # -- stack (SP points at the next free byte: M68PRM section 3.1) -------

    def _push(self, value: int) -> None:
        self.write_byte(self.SP, value & 0xFF)
        self.SP = (self.SP - 1) & 0xFFFF

    def _pull(self) -> int:
        self.SP = (self.SP + 1) & 0xFFFF
        return self.read_byte(self.SP)

    def _push_word(self, value: int) -> None:
        self._push(value)  # low byte first, so memory reads high:low upwards
        self._push(value >> 8)

    def _pull_word(self) -> int:
        high = self._pull()
        return (high << 8) | self._pull()

    def _push_machine_state(self) -> None:
        # The seven-byte frame of SWI, WAI and every interrupt: PCL, PCH, IXL,
        # IXH, ACCA, ACCB, CC (M68PRM p. A-67; MCSDD Figure 13).
        self._push_word(self.PC)
        self._push_word(self.X)
        self._push(self.A)
        self._push(self.B)
        self._push(self.CC | CC_FIXED)

    # -- condition-code helpers --------------------------------------------

    def _nz8_v0(self, value: int) -> None:
        """N and Z from an 8-bit value, V cleared: loads, stores, logic, transfers."""
        cc = self.CC & ~(N | Z | V)
        if value & 0x80:
            cc |= N
        if not value:
            cc |= Z
        self.CC = cc

    def _nz16_v0(self, value: int) -> None:
        cc = self.CC & ~(N | Z | V)
        if value & 0x8000:
            cc |= N
        if not value:
            cc |= Z
        self.CC = cc
