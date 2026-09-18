"""Push and pull instructions.

SP points at the next free byte: a push writes at SP and then decrements it, a
pull increments SP and then reads (M68PRM pp. A-52, A-53).  None of these
instructions touches the condition codes.
"""


class StackMixin:
    """Private push and pull implementation."""

    def _op_psha(self) -> None:
        """PSHA -- push A (M68PRM p. A-52)."""
        self._push(self.A)

    def _op_pshb(self) -> None:
        """PSHB -- push B (M68PRM p. A-52)."""
        self._push(self.B)

    def _op_pula(self) -> None:
        """PULA -- pull A (M68PRM p. A-53)."""
        self.A = self._pull()

    def _op_pulb(self) -> None:
        """PULB -- pull B (M68PRM p. A-53)."""
        self.B = self._pull()

    def _op_pshx(self) -> None:
        """PSHX -- push X, IXL first and then IXH (M6801RM p. A-63)."""
        self._push_word(self.X)

    def _op_pulx(self) -> None:
        """PULX -- pull X, IXH first and then IXL (M6801RM p. A-65)."""
        self.X = self._pull_word()
