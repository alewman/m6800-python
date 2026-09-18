"""Shift and rotate instructions.

All of them share one flag rule (M68PRM pp. A-7, A-8, A-48, A-54, A-55): N and
Z from the result, C from the bit shifted out, and V = N XOR C *after* the
shift.  For LSR, N is always 0, so V simply equals C.  H is never touched.
"""

from m6800_python._core import C, N, V, Z


class ShiftMixin:
    """Private shift and rotate implementation."""

    def _shift_flags(self, result: int, carry_out: int) -> int:
        cc = self.CC & ~(N | Z | V | C)
        if result & 0x80:
            cc |= N
        if not result:
            cc |= Z
        if carry_out:
            cc |= C
        if bool(cc & N) != bool(carry_out):
            cc |= V
        self.CC = cc
        return result

    def _asl(self, value: int) -> int:
        return self._shift_flags((value << 1) & 0xFF, value & 0x80)

    def _asr(self, value: int) -> int:
        return self._shift_flags((value >> 1) | (value & 0x80), value & 0x01)

    def _lsr(self, value: int) -> int:
        return self._shift_flags(value >> 1, value & 0x01)

    def _rol(self, value: int) -> int:
        return self._shift_flags(((value << 1) & 0xFF) | (self.CC & C), value & 0x80)

    def _ror(self, value: int) -> int:
        return self._shift_flags((value >> 1) | ((self.CC & C) << 7), value & 0x01)

    # -- ASL (M68PRM p. A-7) -----------------------------------------------

    def _op_asl(self, ea: int) -> None:
        """ASL -- M <- M << 1, C <- bit 7 (M68PRM p. A-7)."""
        self.write_byte(ea, self._asl(self.read_byte(ea)))

    def _op_asla(self) -> None:
        """ASLA -- A <- A << 1, C <- bit 7 (M68PRM p. A-7)."""
        self.A = self._asl(self.A)

    def _op_aslb(self) -> None:
        """ASLB -- B <- B << 1, C <- bit 7 (M68PRM p. A-7)."""
        self.B = self._asl(self.B)

    # -- ASR (M68PRM p. A-8): bit 7 is held --------------------------------

    def _op_asr(self, ea: int) -> None:
        """ASR -- M <- M >> 1 keeping bit 7, C <- bit 0 (M68PRM p. A-8)."""
        self.write_byte(ea, self._asr(self.read_byte(ea)))

    def _op_asra(self) -> None:
        """ASRA -- A <- A >> 1 keeping bit 7, C <- bit 0 (M68PRM p. A-8)."""
        self.A = self._asr(self.A)

    def _op_asrb(self) -> None:
        """ASRB -- B <- B >> 1 keeping bit 7, C <- bit 0 (M68PRM p. A-8)."""
        self.B = self._asr(self.B)

    # -- LSR (M68PRM p. A-48): bit 7 is loaded with zero -------------------

    def _op_lsr(self, ea: int) -> None:
        """LSR -- M <- M >> 1, bit 7 <- 0, C <- bit 0 (M68PRM p. A-48)."""
        self.write_byte(ea, self._lsr(self.read_byte(ea)))

    def _op_lsra(self) -> None:
        """LSRA -- A <- A >> 1, bit 7 <- 0, C <- bit 0 (M68PRM p. A-48)."""
        self.A = self._lsr(self.A)

    def _op_lsrb(self) -> None:
        """LSRB -- B <- B >> 1, bit 7 <- 0, C <- bit 0 (M68PRM p. A-48)."""
        self.B = self._lsr(self.B)

    # -- ROL and ROR rotate through C (M68PRM pp. A-54, A-55) --------------

    def _op_rol(self, ea: int) -> None:
        """ROL -- M <- M << 1 through C (M68PRM p. A-54)."""
        self.write_byte(ea, self._rol(self.read_byte(ea)))

    def _op_rola(self) -> None:
        """ROLA -- A <- A << 1 through C (M68PRM p. A-54)."""
        self.A = self._rol(self.A)

    def _op_rolb(self) -> None:
        """ROLB -- B <- B << 1 through C (M68PRM p. A-54)."""
        self.B = self._rol(self.B)

    def _op_ror(self, ea: int) -> None:
        """ROR -- M <- M >> 1 through C (M68PRM p. A-55)."""
        self.write_byte(ea, self._ror(self.read_byte(ea)))

    def _op_rora(self) -> None:
        """RORA -- A <- A >> 1 through C (M68PRM p. A-55)."""
        self.A = self._ror(self.A)

    def _op_rorb(self) -> None:
        """RORB -- B <- B >> 1 through C (M68PRM p. A-55)."""
        self.B = self._ror(self.B)

    # -- MC6801/6803 double-accumulator shifts ------------------------------

    def _shift_flags16(self, result: int, carry_out: int) -> None:
        cc = self.CC & ~(N | Z | V | C)
        if result & 0x8000:
            cc |= N
        if not result:
            cc |= Z
        if carry_out:
            cc |= C
        if bool(cc & N) != bool(carry_out):
            cc |= V
        self.CC = cc
        self.A, self.B = result >> 8, result & 0xFF

    def _op_asld(self) -> None:
        """ASLD -- D <- D << 1, C <- bit 15 (M6801RM p. A-10; also LSLD, p. A-55)."""
        d = (self.A << 8) | self.B
        self._shift_flags16((d << 1) & 0xFFFF, d & 0x8000)

    def _op_lsrd(self) -> None:
        """LSRD -- D <- D >> 1, bit 15 <- 0, C <- bit 0 (M6801RM p. A-57)."""
        d = (self.A << 8) | self.B
        self._shift_flags16(d >> 1, d & 0x0001)
