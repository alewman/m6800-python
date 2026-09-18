"""Accumulator loads, stores and register transfers.

Loads *and stores* set N and Z from the value moved and clear V; C is never
touched (M68PRM pp. A-45, A-63; M6801RM pp. A-51, A-76).
"""

from m6800_python._core import CC_FIXED


class LoadMixin:
    """Private load, store and transfer implementation."""

    def _op_ldaa(self, ea: int) -> None:
        """LDAA -- A <- M (M68PRM p. A-45)."""
        self.A = self.read_byte(ea)
        self._nz8_v0(self.A)

    def _op_ldab(self, ea: int) -> None:
        """LDAB -- B <- M (M68PRM p. A-45)."""
        self.B = self.read_byte(ea)
        self._nz8_v0(self.B)

    def _op_staa(self, ea: int) -> None:
        """STAA -- M <- A (M68PRM p. A-63)."""
        self._nz8_v0(self.A)
        self.write_byte(ea, self.A)

    def _op_stab(self, ea: int) -> None:
        """STAB -- M <- B (M68PRM p. A-63)."""
        self._nz8_v0(self.B)
        self.write_byte(ea, self.B)

    def _op_ldd(self, ea: int) -> None:
        """LDD -- D <- M:M+1 (M6801RM p. A-51)."""
        d = self._read_word(ea)
        self.A, self.B = d >> 8, d & 0xFF
        self._nz16_v0(d)

    def _op_std(self, ea: int) -> None:
        """STD -- M:M+1 <- D (M6801RM p. A-76)."""
        d = (self.A << 8) | self.B
        self._nz16_v0(d)
        self._write_word(ea, d)

    def _op_tab(self) -> None:
        """TAB -- B <- A (M68PRM p. A-69)."""
        self.B = self.A
        self._nz8_v0(self.B)

    def _op_tba(self) -> None:
        """TBA -- A <- B (M68PRM p. A-71)."""
        self.A = self.B
        self._nz8_v0(self.A)

    def _op_tap(self) -> None:
        """TAP -- CC <- A, bits 0-5 (M68PRM p. A-70)."""
        # Only bits 0-5 are transferred; bits 7 and 6 stay 1.  (MAME copies all
        # eight, so its CC can read back with bits 7-6 clear; this core follows
        # the manual.)  On the MC6801 the new I lands through ITMP too late for
        # the next instruction: "the next instruction in line following single
        # or multiple TAP instructions will always be executed" (M6801RM
        # section 5.4.1.2).
        self.CC = (self.A & 0x3F) | CC_FIXED
        self._irq_inhibit = True

    def _op_tpa(self) -> None:
        """TPA -- A <- CC, with bits 7 and 6 set (M68PRM p. A-72)."""
        self.A = self.CC | CC_FIXED
