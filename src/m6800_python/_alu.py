"""Arithmetic, logic, test and condition-code instructions.

Each flag rule below is the one printed on the instruction's page of M68PRM
Appendix A (and, for the MC6801 additions, M6801RM Appendix A); the page is
named in the handler's docstring.  H is touched only by the 8-bit adds.
"""

from m6800_python._core import C, H, N, V, Z


class ALUMixin:
    """Private arithmetic and logic implementation."""

    # -- shared arithmetic -------------------------------------------------

    def _add8(self, a: int, m: int, carry: int) -> int:
        r = a + m + carry
        cc = self.CC & ~(H | N | Z | V | C)
        if (a ^ m ^ r) & 0x10:
            cc |= H  # carry out of bit 3 (M68PRM p. A-3: H = A3.B3 + B3./R3 + /R3.A3)
        if r & 0x80:
            cc |= N
        if not r & 0xFF:
            cc |= Z
        if (a ^ r) & (m ^ r) & 0x80:
            cc |= V  # both operands' sign differs from the result's
        if r & 0x100:
            cc |= C
        self.CC = cc
        return r & 0xFF

    def _sub8(self, a: int, m: int, borrow: int) -> int:
        r = a - m - borrow
        cc = self.CC & ~(N | Z | V | C)  # H is not affected by any subtract
        if r & 0x80:
            cc |= N
        if not r & 0xFF:
            cc |= Z
        if (a ^ m) & (a ^ r) & 0x80:
            cc |= V
        if r & 0x100:
            cc |= C  # C is the borrow: set when M (+ C) exceeds the minuend
        self.CC = cc
        return r & 0xFF

    def _add16(self, a: int, m: int) -> int:
        r = a + m
        cc = self.CC & ~(N | Z | V | C)  # ADDD leaves H alone (M6801RM p. A-7)
        if r & 0x8000:
            cc |= N
        if not r & 0xFFFF:
            cc |= Z
        if (a ^ r) & (m ^ r) & 0x8000:
            cc |= V
        if r & 0x10000:
            cc |= C
        self.CC = cc
        return r & 0xFFFF

    def _sub16(self, a: int, m: int) -> int:
        r = a - m
        cc = self.CC & ~(N | Z | V | C)
        if r & 0x8000:
            cc |= N
        if not r & 0xFFFF:
            cc |= Z
        if (a ^ m) & (a ^ r) & 0x8000:
            cc |= V
        if r & 0x10000:
            cc |= C
        self.CC = cc
        return r & 0xFFFF

    def _carry(self) -> int:
        return self.CC & C

    # -- add and subtract (M68PRM pp. A-3, A-4, A-5, A-58, A-59, A-66) ------

    def _op_aba(self) -> None:
        """ABA -- A <- A + B (M68PRM p. A-3)."""
        self.A = self._add8(self.A, self.B, 0)

    def _op_adca(self, ea: int) -> None:
        """ADCA -- A <- A + M + C (M68PRM p. A-4)."""
        self.A = self._add8(self.A, self.read_byte(ea), self._carry())

    def _op_adcb(self, ea: int) -> None:
        """ADCB -- B <- B + M + C (M68PRM p. A-4)."""
        self.B = self._add8(self.B, self.read_byte(ea), self._carry())

    def _op_adda(self, ea: int) -> None:
        """ADDA -- A <- A + M (M68PRM p. A-5)."""
        self.A = self._add8(self.A, self.read_byte(ea), 0)

    def _op_addb(self, ea: int) -> None:
        """ADDB -- B <- B + M (M68PRM p. A-5)."""
        self.B = self._add8(self.B, self.read_byte(ea), 0)

    def _op_sba(self) -> None:
        """SBA -- A <- A - B (M68PRM p. A-58)."""
        self.A = self._sub8(self.A, self.B, 0)

    def _op_sbca(self, ea: int) -> None:
        """SBCA -- A <- A - M - C (M68PRM p. A-59)."""
        self.A = self._sub8(self.A, self.read_byte(ea), self._carry())

    def _op_sbcb(self, ea: int) -> None:
        """SBCB -- B <- B - M - C (M68PRM p. A-59)."""
        self.B = self._sub8(self.B, self.read_byte(ea), self._carry())

    def _op_suba(self, ea: int) -> None:
        """SUBA -- A <- A - M (M68PRM p. A-66)."""
        self.A = self._sub8(self.A, self.read_byte(ea), 0)

    def _op_subb(self, ea: int) -> None:
        """SUBB -- B <- B - M (M68PRM p. A-66)."""
        self.B = self._sub8(self.B, self.read_byte(ea), 0)

    # -- compares: a subtract whose result is discarded (pp. A-26, A-31) ---

    def _op_cba(self) -> None:
        """CBA -- flags from A - B (M68PRM p. A-26)."""
        self._sub8(self.A, self.B, 0)

    def _op_cmpa(self, ea: int) -> None:
        """CMPA -- flags from A - M (M68PRM p. A-31)."""
        self._sub8(self.A, self.read_byte(ea), 0)

    def _op_cmpb(self, ea: int) -> None:
        """CMPB -- flags from B - M (M68PRM p. A-31)."""
        self._sub8(self.B, self.read_byte(ea), 0)

    # -- logic: N and Z from the result, V cleared, C untouched ------------

    def _op_anda(self, ea: int) -> None:
        """ANDA -- A <- A AND M (M68PRM p. A-6)."""
        self.A &= self.read_byte(ea)
        self._nz8_v0(self.A)

    def _op_andb(self, ea: int) -> None:
        """ANDB -- B <- B AND M (M68PRM p. A-6)."""
        self.B &= self.read_byte(ea)
        self._nz8_v0(self.B)

    def _op_bita(self, ea: int) -> None:
        """BITA -- flags from A AND M (M68PRM p. A-15)."""
        self._nz8_v0(self.A & self.read_byte(ea))

    def _op_bitb(self, ea: int) -> None:
        """BITB -- flags from B AND M (M68PRM p. A-15)."""
        self._nz8_v0(self.B & self.read_byte(ea))

    def _op_eora(self, ea: int) -> None:
        """EORA -- A <- A XOR M (M68PRM p. A-39)."""
        self.A ^= self.read_byte(ea)
        self._nz8_v0(self.A)

    def _op_eorb(self, ea: int) -> None:
        """EORB -- B <- B XOR M (M68PRM p. A-39)."""
        self.B ^= self.read_byte(ea)
        self._nz8_v0(self.B)

    def _op_oraa(self, ea: int) -> None:
        """ORAA -- A <- A OR M (M68PRM p. A-51)."""
        self.A |= self.read_byte(ea)
        self._nz8_v0(self.A)

    def _op_orab(self, ea: int) -> None:
        """ORAB -- B <- B OR M (M68PRM p. A-51)."""
        self.B |= self.read_byte(ea)
        self._nz8_v0(self.B)

    # -- single-operand operations on A, B or memory -----------------------

    def _clr(self) -> int:
        self.CC = (self.CC & ~(N | V | C)) | Z  # N=0 Z=1 V=0 C=0 (M68PRM p. A-29)
        return 0

    def _com(self, value: int) -> int:
        value ^= 0xFF
        self._nz8_v0(value)
        self.CC |= C  # COM always sets C (M68PRM p. A-32)
        return value

    def _neg(self, value: int) -> int:
        r = (-value) & 0xFF
        cc = self.CC & ~(N | Z | V | C)
        if r & 0x80:
            cc |= N
        if not r:
            cc |= Z
        if value == 0x80:
            cc |= V  # 0 - $80 overflows, and $80 is left unchanged (M68PRM p. A-49)
        if value:
            cc |= C  # a borrow unless the operand was zero
        self.CC = cc
        return r

    def _inc(self, value: int) -> int:
        r = (value + 1) & 0xFF
        cc = self.CC & ~(N | Z | V)  # C is not affected (M68PRM p. A-40)
        if r & 0x80:
            cc |= N
        if not r:
            cc |= Z
        if value == 0x7F:
            cc |= V
        self.CC = cc
        return r

    def _dec(self, value: int) -> int:
        r = (value - 1) & 0xFF
        cc = self.CC & ~(N | Z | V)  # C is not affected (M68PRM p. A-36)
        if r & 0x80:
            cc |= N
        if not r:
            cc |= Z
        if value == 0x80:
            cc |= V
        self.CC = cc
        return r

    def _tst(self, value: int) -> None:
        self._nz8_v0(value)
        self.CC &= ~C  # TST clears C as well as V (M68PRM p. A-73)

    def _op_clr(self, ea: int) -> None:
        """CLR -- M <- 0 (M68PRM p. A-29)."""
        # The MC6800 reads the location before writing it (MCSDD Table 8
        # gives CLR the same read-modify-write bus cycles as the others).
        self.read_byte(ea)
        self.write_byte(ea, self._clr())

    def _op_clra(self) -> None:
        """CLRA -- A <- 0 (M68PRM p. A-29)."""
        self.A = self._clr()

    def _op_clrb(self) -> None:
        """CLRB -- B <- 0 (M68PRM p. A-29)."""
        self.B = self._clr()

    def _op_com(self, ea: int) -> None:
        """COM -- M <- NOT M (M68PRM p. A-32)."""
        self.write_byte(ea, self._com(self.read_byte(ea)))

    def _op_coma(self) -> None:
        """COMA -- A <- NOT A (M68PRM p. A-32)."""
        self.A = self._com(self.A)

    def _op_comb(self) -> None:
        """COMB -- B <- NOT B (M68PRM p. A-32)."""
        self.B = self._com(self.B)

    def _op_neg(self, ea: int) -> None:
        """NEG -- M <- 0 - M (M68PRM p. A-49)."""
        self.write_byte(ea, self._neg(self.read_byte(ea)))

    def _op_nega(self) -> None:
        """NEGA -- A <- 0 - A (M68PRM p. A-49)."""
        self.A = self._neg(self.A)

    def _op_negb(self) -> None:
        """NEGB -- B <- 0 - B (M68PRM p. A-49)."""
        self.B = self._neg(self.B)

    def _op_inc(self, ea: int) -> None:
        """INC -- M <- M + 1 (M68PRM p. A-40)."""
        self.write_byte(ea, self._inc(self.read_byte(ea)))

    def _op_inca(self) -> None:
        """INCA -- A <- A + 1 (M68PRM p. A-40)."""
        self.A = self._inc(self.A)

    def _op_incb(self) -> None:
        """INCB -- B <- B + 1 (M68PRM p. A-40)."""
        self.B = self._inc(self.B)

    def _op_dec(self, ea: int) -> None:
        """DEC -- M <- M - 1 (M68PRM p. A-36)."""
        self.write_byte(ea, self._dec(self.read_byte(ea)))

    def _op_deca(self) -> None:
        """DECA -- A <- A - 1 (M68PRM p. A-36)."""
        self.A = self._dec(self.A)

    def _op_decb(self) -> None:
        """DECB -- B <- B - 1 (M68PRM p. A-36)."""
        self.B = self._dec(self.B)

    def _op_tst(self, ea: int) -> None:
        """TST -- flags from M - 0 (M68PRM p. A-73)."""
        self._tst(self.read_byte(ea))

    def _op_tsta(self) -> None:
        """TSTA -- flags from A - 0 (M68PRM p. A-73)."""
        self._tst(self.A)

    def _op_tstb(self) -> None:
        """TSTB -- flags from B - 0 (M68PRM p. A-73)."""
        self._tst(self.B)

    # -- decimal adjust (M68PRM pp. A-34, A-35) ----------------------------

    def _op_daa(self) -> None:
        """DAA -- decimal-adjust A after ABA, ADD or ADC (M68PRM p. A-34)."""
        a = self.A
        low = a & 0x0F
        high = a & 0xF0
        correction = 0
        if low > 0x09 or self.CC & H:
            correction |= 0x06
        if high > 0x80 and low > 0x09:
            correction |= 0x60
        if high > 0x90 or self.CC & C:
            correction |= 0x60
        r = a + correction
        # This rule reproduces the manual's nine-row table on all 384 BCD
        # cases.  C is never cleared: every row with C=1 before has C=1 after.
        # V is "not defined" (p. A-34); this core clears it, as MAME does.
        cc = self.CC & ~(N | Z | V)
        if r & 0x80:
            cc |= N
        if not r & 0xFF:
            cc |= Z
        if r & 0x100:
            cc |= C
        self.CC = cc
        self.A = r & 0xFF

    # -- condition-code register instructions ------------------------------

    def _op_clc(self) -> None:
        """CLC -- C <- 0 (M68PRM p. A-27)."""
        self.CC &= ~C

    def _op_sec(self) -> None:
        """SEC -- C <- 1 (M68PRM p. A-60)."""
        self.CC |= C

    def _op_clv(self) -> None:
        """CLV -- V <- 0 (M68PRM p. A-30)."""
        self.CC &= ~V

    def _op_sev(self) -> None:
        """SEV -- V <- 1 (M68PRM p. A-62)."""
        self.CC |= V

    # -- MC6801/6803 sixteen-bit arithmetic --------------------------------

    def _op_addd(self, ea: int) -> None:
        """ADDD -- D <- D + M:M+1 (M6801RM p. A-7)."""
        d = (self.A << 8) | self.B
        r = self._add16(d, self._read_word(ea))
        self.A, self.B = r >> 8, r & 0xFF

    def _op_subd(self, ea: int) -> None:
        """SUBD -- D <- D - M:M+1 (M6801RM p. A-80)."""
        d = (self.A << 8) | self.B
        r = self._sub16(d, self._read_word(ea))
        self.A, self.B = r >> 8, r & 0xFF

    def _op_mul(self) -> None:
        """MUL -- D <- A * B, unsigned (M6801RM p. A-58)."""
        r = self.A * self.B
        self.A, self.B = r >> 8, r & 0xFF
        # Only C changes: C <- bit 7 of the low byte, so ADCA #0 rounds.
        self.CC = (self.CC & ~C) | (1 if r & 0x80 else 0)
