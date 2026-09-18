"""Index-register and stack-pointer instructions.

X and SP are the two 16-bit registers besides PC.  Loads and stores of them set
N and Z from all sixteen bits and clear V (M68PRM pp. A-46, A-47, A-64, A-65).
INX and DEX change only Z; INS, DES, TSX, TXS and ABX change no flags at all.
"""

from m6800_python._core import N, V, Z


class IndexMixin:
    """Private index-register and stack-pointer implementation."""

    #: True on the MC6801/6803, whose CPX is a true 16-bit compare.
    _CPX_SETS_CARRY = False

    def _op_ldx(self, ea: int) -> None:
        """LDX -- X <- M:M+1 (M68PRM p. A-47)."""
        self.X = self._read_word(ea)
        self._nz16_v0(self.X)

    def _op_stx(self, ea: int) -> None:
        """STX -- M:M+1 <- X (M68PRM p. A-65)."""
        self._nz16_v0(self.X)
        self._write_word(ea, self.X)

    def _op_lds(self, ea: int) -> None:
        """LDS -- SP <- M:M+1 (M68PRM p. A-46)."""
        self.SP = self._read_word(ea)
        self._nz16_v0(self.SP)

    def _op_sts(self, ea: int) -> None:
        """STS -- M:M+1 <- SP (M68PRM p. A-64)."""
        self._nz16_v0(self.SP)
        self._write_word(ea, self.SP)

    def _op_cpx(self, ea: int) -> None:
        """CPX -- flags from X - M:M+1 (M68PRM p. A-33; M6801RM p. A-39)."""
        m = self._read_word(ea)
        if self._CPX_SETS_CARRY:
            # MC6801/6803: "a 16 bit subtract of (M:M+1) from the index
            # register", setting N, Z, V and C (M6801RM p. A-39).
            self._sub16(self.X, m)
            return
        # MC6800: two byte compares, IXH - M and IXL - (M+1).  Z is set only
        # if both results are zero; N and V come from the high-byte compare
        # alone, with no borrow from the low byte; C is not affected
        # (M68PRM p. A-33: N = RH7, V = IXH7./M7./RH7 + /IXH7.M7.RH7).
        xh, mh = self.X >> 8, m >> 8
        rh = (xh - mh) & 0xFF
        cc = self.CC & ~(N | Z | V)
        if rh & 0x80:
            cc |= N
        if m == self.X:
            cc |= Z
        if (xh ^ mh) & (xh ^ rh) & 0x80:
            cc |= V
        self.CC = cc

    def _op_inx(self) -> None:
        """INX -- X <- X + 1, only Z affected (M68PRM p. A-42)."""
        self.X = (self.X + 1) & 0xFFFF
        self.CC = (self.CC | Z) if self.X == 0 else (self.CC & ~Z)

    def _op_dex(self) -> None:
        """DEX -- X <- X - 1, only Z affected (M68PRM p. A-38)."""
        self.X = (self.X - 1) & 0xFFFF
        self.CC = (self.CC | Z) if self.X == 0 else (self.CC & ~Z)

    def _op_abx(self) -> None:
        """ABX -- X <- X + B, B unsigned, no flags (M6801RM p. A-4)."""
        self.X = (self.X + self.B) & 0xFFFF

    def _op_ins(self) -> None:
        """INS -- SP <- SP + 1 (M68PRM p. A-41)."""
        self.SP = (self.SP + 1) & 0xFFFF

    def _op_des(self) -> None:
        """DES -- SP <- SP - 1 (M68PRM p. A-37)."""
        self.SP = (self.SP - 1) & 0xFFFF

    def _op_tsx(self) -> None:
        """TSX -- X <- SP + 1 (M68PRM p. A-74)."""
        # SP points at the next free byte, so SP + 1 is the last byte pushed.
        self.X = (self.SP + 1) & 0xFFFF

    def _op_txs(self) -> None:
        """TXS -- SP <- X - 1 (M68PRM p. A-75)."""
        self.SP = (self.X - 1) & 0xFFFF
