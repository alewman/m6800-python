"""Branches, jumps, subroutine calls and NOP.

A branch is always two bytes, the second a signed offset from the address of
the *next* instruction: PC <- PC + 2 + Rel (M68PRM p. A-22).  Every branch
costs the same number of cycles taken or not (4 on the MC6800, 3 on the
MC6801), which is why the cycle count lives in the dispatch table and not here.
No instruction in this module touches the condition codes.
"""

from m6800_python._core import C, N, V, Z


class BranchMixin:
    """Private branch, jump and call implementation."""

    def _branch(self, taken: bool) -> None:
        offset = self._fetch()
        if taken:
            self.PC = (self.PC + offset - (0x100 if offset & 0x80 else 0)) & 0xFFFF

    def _n_xor_v(self) -> bool:
        return bool(self.CC & N) != bool(self.CC & V)

    def _op_bra(self) -> None:
        """BRA -- branch always (M68PRM p. A-22)."""
        self._branch(True)

    def _op_brn(self) -> None:
        """BRN -- branch never: a two-byte, three-cycle no-op (M6801RM p. A-28)."""
        self._branch(False)

    def _op_bhi(self) -> None:
        """BHI -- branch if C + Z = 0, unsigned higher (M68PRM p. A-14)."""
        self._branch(not self.CC & (C | Z))

    def _op_bls(self) -> None:
        """BLS -- branch if C + Z = 1, unsigned lower or same (M68PRM p. A-17)."""
        self._branch(bool(self.CC & (C | Z)))

    def _op_bcc(self) -> None:
        """BCC -- branch if C = 0 (M68PRM p. A-9)."""
        self._branch(not self.CC & C)

    def _op_bcs(self) -> None:
        """BCS -- branch if C = 1 (M68PRM p. A-10)."""
        self._branch(bool(self.CC & C))

    def _op_bne(self) -> None:
        """BNE -- branch if Z = 0 (M68PRM p. A-20)."""
        self._branch(not self.CC & Z)

    def _op_beq(self) -> None:
        """BEQ -- branch if Z = 1 (M68PRM p. A-11)."""
        self._branch(bool(self.CC & Z))

    def _op_bvc(self) -> None:
        """BVC -- branch if V = 0 (M68PRM p. A-24)."""
        self._branch(not self.CC & V)

    def _op_bvs(self) -> None:
        """BVS -- branch if V = 1 (M68PRM p. A-25)."""
        self._branch(bool(self.CC & V))

    def _op_bpl(self) -> None:
        """BPL -- branch if N = 0 (M68PRM p. A-21)."""
        self._branch(not self.CC & N)

    def _op_bmi(self) -> None:
        """BMI -- branch if N = 1 (M68PRM p. A-19)."""
        self._branch(bool(self.CC & N))

    def _op_bge(self) -> None:
        """BGE -- branch if N XOR V = 0, signed greater or equal (M68PRM p. A-12)."""
        self._branch(not self._n_xor_v())

    def _op_blt(self) -> None:
        """BLT -- branch if N XOR V = 1, signed less than (M68PRM p. A-18)."""
        self._branch(self._n_xor_v())

    def _op_bgt(self) -> None:
        """BGT -- branch if Z + (N XOR V) = 0, signed greater (M68PRM p. A-13)."""
        self._branch(not (self.CC & Z or self._n_xor_v()))

    def _op_ble(self) -> None:
        """BLE -- branch if Z + (N XOR V) = 1, signed less or equal (M68PRM p. A-16)."""
        self._branch(bool(self.CC & Z or self._n_xor_v()))

    def _op_bsr(self) -> None:
        """BSR -- push the return address, then branch (M68PRM p. A-23)."""
        offset = self._fetch()
        self._push_word(self.PC)  # PCL first, then PCH
        self.PC = (self.PC + offset - (0x100 if offset & 0x80 else 0)) & 0xFFFF

    def _op_jmp(self, ea: int) -> None:
        """JMP -- PC <- effective address (M68PRM p. A-43)."""
        self.PC = ea

    def _op_jsr(self, ea: int) -> None:
        """JSR -- push the return address, PC <- effective address (M68PRM p. A-44)."""
        # The effective address has been formed, so PC already points past
        # the operand: PC + 3 for extended, PC + 2 for indexed and direct.
        self._push_word(self.PC)
        self.PC = ea

    def _op_rts(self) -> None:
        """RTS -- pull PC, PCH first (M68PRM p. A-57)."""
        self.PC = self._pull_word()

    def _op_nop(self) -> None:
        """NOP -- no operation (M68PRM p. A-50)."""
