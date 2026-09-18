"""Interrupt instructions, interrupt entry and reset.

The seven-byte frame, the vectors and the costs are documented in
docs/start-here.md ("Interrupts, reset and the vector table") with their
sources; the short version is on each line below.
"""

from m6800_python._core import CC_FIXED, I

VECTOR_IRQ = 0xFFF8  # IRQ1 on the MC6801
VECTOR_SWI = 0xFFFA
VECTOR_NMI = 0xFFFC
VECTOR_RESET = 0xFFFE


class InterruptMixin:
    """Private interrupt, WAI, SWI, RTI and reset implementation."""

    #: Cycles from an accepted interrupt to the handler's first fetch: the
    #: discarded fetch, two internal cycles, seven pushes and two vector reads
    #: (MCSDD Figure 13, MC6800; M6801RM section 5.3 and Figure 5-12).
    INTERRUPT_ENTRY_CYCLES = 12

    #: The same, when WAI has already stacked the frame.  4 on the MC6801
    #: (M6801RM section 5.4.2).  On the MC6800 it is UNRESOLVED: MCSDD's
    #: Figure 14 reads as 5, MAME charges 4 (docs/timing.md).  M6800 keeps
    #: MAME's 4 until a better source settles it; change it here only.
    WAI_EXIT_CYCLES = 4

    def _enter_interrupt(self, vector: int) -> int:
        if self.waiting:
            # WAI pushed the frame before it waited (M68PRM p. A-76).
            self.waiting = False
            cycles = self.WAI_EXIT_CYCLES
        else:
            self._push_machine_state()
            cycles = self.INTERRUPT_ENTRY_CYCLES
        self.CC |= I
        self._irq_inhibit = False
        self.PC = self._read_word(vector)
        return cycles

    def reset(self) -> None:
        """Apply RESET: set I, clear the other flags, and load PC from $FFFE.

        The manuals specify only I and PC ("during the restart routine, the
        interrupt mask bit is set", MCSDD's MC6800 data sheet, p. 26).  A, B, X
        and SP are left as they were, and H N Z V C are cleared, as MAME does,
        so that traces can be compared.  Reset also leaves WAI and HCF.
        """
        self.CC = CC_FIXED | I
        self.waiting = False
        self.halted = False
        self._irq_inhibit = False
        self._nmi_pending = False
        self._nmi_previous = self.nmi
        self.PC = self._read_word(VECTOR_RESET)

    def _op_cli(self) -> None:
        """CLI -- I <- 0 (M68PRM p. A-28)."""
        # "Assuming the I-bit is not already clear ... the instruction following
        # CLI will always be executed prior to servicing any maskable
        # interrupt" (M6801RM section 5.4.1.1).  M68PRM states no such rule for
        # the MC6800; its section 3.3.8 look-ahead has the same effect.
        if self.CC & I:
            self._irq_inhibit = True
        self.CC &= ~I

    def _op_sei(self) -> None:
        """SEI -- I <- 1, with no delay (M68PRM p. A-61)."""
        self.CC |= I

    def _op_swi(self) -> None:
        """SWI -- stack the machine state, set I, jump through $FFFA (M68PRM p. A-67)."""
        self._push_machine_state()
        self.CC |= I
        self.PC = self._read_word(VECTOR_SWI)

    def _op_wai(self) -> None:
        """WAI -- stack the machine state and wait for an interrupt (M68PRM p. A-76)."""
        self._push_machine_state()
        self.waiting = True

    def _op_rti(self) -> None:
        """RTI -- pull CC, B, A, X and PC (M68PRM p. A-56)."""
        self.CC = self._pull() | CC_FIXED
        self.B = self._pull()
        self.A = self._pull()
        self.X = self._pull_word()
        self.PC = self._pull_word()
        # No CLI-style delay: "if the I-bit is cleared when the Condition Code
        # Register is restored, the one E-cycle delay is absorbed by the
        # remaining cycles of the instruction" (M6801RM section 5.4.1.3).
