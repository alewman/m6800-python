"""Public MC6800 and MC6801/6803 CPU classes.

The host owns memory and every device: it passes ``read_byte(address)`` and
``write_byte(address, value)`` in, calls :meth:`step`, and adds the returned
cycle count to its own clock.  See docs/start-here.md, "The embedding contract".
"""

from m6800_python._alu import ALUMixin
from m6800_python._branches import BranchMixin
from m6800_python._core import CC_FIXED, CoreMixin, I, ReadByte, WriteByte
from m6800_python._dispatch import Entry, build_table
from m6800_python._index import IndexMixin
from m6800_python._interrupts import VECTOR_IRQ, VECTOR_NMI, InterruptMixin
from m6800_python._loads import LoadMixin
from m6800_python._shifts import ShiftMixin
from m6800_python._stack import StackMixin
from m6800_python._undocumented import POLICIES, UndocumentedOpcode, policy_entry
from m6800_python.state import CPUState


class M6800(
    ALUMixin,
    ShiftMixin,
    LoadMixin,
    IndexMixin,
    StackMixin,
    BranchMixin,
    InterruptMixin,
    CoreMixin,
):
    """A Motorola MC6800 instruction core; also the MC6802 and MC6808.

    The MC6802 and MC6808 execute the MC6800's instruction set with its cycle
    counts; their on-chip clock and (6802) RAM belong to the host.

    Registers are plain attributes: ``A``, ``B`` (8-bit), ``X``, ``SP``, ``PC``
    (16-bit) and ``CC``, whose bits 7 and 6 read as 1.  Inputs: set ``irq``
    to True while the IRQ line is asserted (level-sensitive); set ``nmi`` to
    True to assert NMI -- it is edge-triggered, recognised on the False-to-True
    change, and :meth:`pulse_nmi` latches one directly.  Both are sampled at
    instruction boundaries.  ``waiting`` is True inside WAI, ``halted`` after
    HCF.

    ``undocumented`` chooses what the opcodes Motorola does not assign do:
    ``"strict"`` (the default) halts on the HCF family and raises
    :class:`UndocumentedOpcode` on the rest; ``"measured"`` adds the
    behaviours Wheeler (1977) and Doc TB (2019) observed on real MC6800s;
    ``"mame"`` reproduces MAME 0.285, for trace comparison.  See
    _undocumented.py for each behaviour and its source.
    """

    PART = 6800
    _tables: dict[str, list[Entry]]

    def __init__(
        self, read_byte: ReadByte, write_byte: WriteByte, *, undocumented: str = "strict"
    ) -> None:
        self._init_core(read_byte, write_byte)
        cls = type(self)
        if "_tables" not in cls.__dict__:
            cls._tables = {
                policy: build_table(cls, cls.PART, policy_entry(cls, cls.PART, policy))
                for policy in POLICIES
            }
        if undocumented not in cls._tables:
            raise ValueError(f"undocumented= must be one of {POLICIES}, not {undocumented!r}")
        self.undocumented = undocumented
        self._table = cls._tables[undocumented]

    def capture_state(self) -> CPUState:
        """Return an immutable snapshot of all CPU-owned state.

        No host reads, no side effects.  Memory and devices are the host's and
        are not included (docs/cpu-state.md).
        """
        return CPUState(
            a=self.A,
            b=self.B,
            x=self.X,
            sp=self.SP,
            pc=self.PC,
            cc=self.CC,
            irq=bool(self.irq),
            nmi=bool(self.nmi),
            irq2=getattr(self, "irq2", None),
            nmi_previous=bool(self._nmi_previous),
            nmi_pending=self._nmi_pending,
            irq_inhibit=self._irq_inhibit,
            waiting=self.waiting,
            halted=self.halted,
            opcode=self._opcode,
            previous_opcode=self._previous_opcode,
        )

    def restore_state(self, state: CPUState) -> None:
        """Restore a captured CPU state without touching the host.

        Restoring the processor alone does not restore memory or devices.
        """
        if type(state) is not CPUState:
            raise TypeError("state must be a CPUState")
        if state.irq2 is not None and not hasattr(self, "irq2"):
            raise ValueError("irq2 is an MC6801/6803 input; this CPU has none")
        self.A, self.B, self.X, self.SP, self.PC, self.CC = (
            state.a,
            state.b,
            state.x,
            state.sp,
            state.pc,
            state.cc,
        )
        self.irq = state.irq
        self.nmi = state.nmi
        if hasattr(self, "irq2"):
            self.irq2 = state.irq2
        self._nmi_previous = state.nmi_previous
        self._nmi_pending = state.nmi_pending
        self._irq_inhibit = state.irq_inhibit
        self.waiting = state.waiting
        self.halted = state.halted
        self._opcode = state.opcode
        self._previous_opcode = state.previous_opcode

    def pulse_nmi(self) -> None:
        """Latch an NMI edge, to be taken at the next instruction boundary."""
        self._nmi_pending = True

    def _maskable_vector(self) -> int | None:
        return VECTOR_IRQ if self.irq else None

    def step(self) -> int:
        """Execute one instruction or one interrupt entry; return its cycle count.

        Order at an instruction boundary: a halted (HCF) CPU stays halted; an
        NMI edge is taken; then, unless the previous instruction was TAP, or a
        CLI that holds interrupts off for one instruction, a maskable request
        is taken if I is clear; a CPU inside WAI idles for one cycle;
        otherwise one instruction runs.
        """
        if self.halted:
            return 1
        if self.nmi and not self._nmi_previous:
            self._nmi_pending = True
        self._nmi_previous = self.nmi
        if self._nmi_pending:
            self._nmi_pending = False
            return self._enter_interrupt(VECTOR_NMI)
        if self._irq_inhibit:
            self._irq_inhibit = False
        elif not self.CC & I:
            vector = self._maskable_vector()
            if vector is not None:
                return self._enter_interrupt(vector)
        if self.waiting:
            return 1

        opcode = self.read_byte(self.PC)
        self.PC = (self.PC + 1) & 0xFFFF
        previous, current = self._previous_opcode, self._opcode
        self._previous_opcode = current
        self._opcode = opcode
        handler, ea, cycles = self._table[opcode]
        try:
            if ea is None:
                handler(self)
            else:
                handler(self, ea(self))
        except UndocumentedOpcode:
            # The strict and measured policies promise that a trapped opcode
            # leaves the CPU exactly as it was, so put the history back. The
            # try costs nothing when nothing raises (zero-cost exceptions).
            self._previous_opcode, self._opcode = previous, current
            raise
        return cycles


class M6803(M6800):
    """A Motorola MC6801/MC6803 instruction core.

    The MC6801's instruction set and cycle counts (M6801RM Appendix A): the
    MC6800's plus ABX, ADDD, ASLD, BRN, JSR direct, LDD, LSRD, MUL, PSHX, PULX,
    STD and SUBD, most shared opcodes faster, and CPX a true 16-bit compare.
    The on-chip timer, SCI and ports are the host's; so are their four
    interrupt sources, which the host raises through ``irq2``.

    ``D`` is A:B, A the high byte.  ``irq2`` holds the vector of the highest-
    priority pending on-chip request (``$FFF6`` input capture, ``$FFF4``
    output compare, ``$FFF2`` timer overflow, ``$FFF0`` SCI), or None; the
    external IRQ1 line (``irq``) outranks it (M6801RM section 5.3.1).
    """

    PART = 6801
    _CPX_SETS_CARRY = True
    _CLI_DELAY_NEEDS_ODD_OPCODE = False

    def __init__(
        self, read_byte: ReadByte, write_byte: WriteByte, *, undocumented: str = "strict"
    ) -> None:
        super().__init__(read_byte, write_byte, undocumented=undocumented)
        self.irq2: int | None = None

    @property
    def D(self) -> int:
        return (self.A << 8) | self.B

    @D.setter
    def D(self, value: int) -> None:
        self.A = (value >> 8) & 0xFF
        self.B = value & 0xFF

    def _maskable_vector(self) -> int | None:
        if self.irq:
            return VECTOR_IRQ
        return self.irq2


#: The MC6802 and MC6808 are MC6800s as far as the instruction core goes.
M6802 = M6800
M6808 = M6800
#: The MC6801 is an MC6803 with on-chip ROM, which is the host's business.
M6801 = M6803

__all__ = ["CC_FIXED", "M6800", "M6801", "M6802", "M6803", "M6808"]
