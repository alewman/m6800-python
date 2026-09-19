"""Immutable values for capturing and restoring 6800-family processor state."""

from dataclasses import dataclass


def _require_int(name: str, value: object, maximum: int) -> None:
    if type(value) is not int or not 0 <= value <= maximum:
        width = 2 if maximum == 0xFF else 4
        message = f"{name} must be an integer in range 0x{'0' * width}..0x{maximum:0{width}X}"
        raise ValueError(message)


def _require_bool(name: str, value: object) -> None:
    if type(value) is not bool:
        raise ValueError(f"{name} must be a bool")


@dataclass(frozen=True, slots=True)
class CPUState:
    """Complete CPU-owned state at an instruction boundary.

    Registers, the interrupt inputs as the core last saw them, and the internal
    execution state that decides what the next ``step()`` does.  Host memory,
    devices, scheduling and counters are deliberately excluded: restoring this
    value restores the processor, not a machine.
    """

    a: int = 0
    b: int = 0
    x: int = 0
    sp: int = 0
    pc: int = 0
    cc: int = 0xD0
    # Inputs, as the host has set them.
    irq: bool = False
    nmi: bool = False
    irq2: int | None = None  # MC6801/6803 on-chip request vector; always None on the 6800
    # Internal state.
    nmi_previous: bool = False  # the NMI level at the last boundary (edge detection)
    nmi_pending: bool = False  # an NMI edge latched and not yet taken
    irq_inhibit: bool = False  # the step after TAP, or after a CLI that holds IRQ off
    waiting: bool = False  # inside WAI, the frame already stacked
    halted: bool = False  # HCF: only reset leaves it
    opcode: int = 0x01  # the last opcode executed
    previous_opcode: int = 0x01  # the one before it (the MC6800's CLI rule reads it)

    def __post_init__(self) -> None:
        for name in ("a", "b", "cc", "opcode", "previous_opcode"):
            _require_int(name, getattr(self, name), 0xFF)
        for name in ("x", "sp", "pc"):
            _require_int(name, getattr(self, name), 0xFFFF)
        for name in (
            "irq",
            "nmi",
            "nmi_previous",
            "nmi_pending",
            "irq_inhibit",
            "waiting",
            "halted",
        ):
            _require_bool(name, getattr(self, name))
        if self.irq2 is not None and self.irq2 not in (0xFFF0, 0xFFF2, 0xFFF4, 0xFFF6):
            raise ValueError("irq2 must be None or one of 0xFFF0, 0xFFF2, 0xFFF4, 0xFFF6")
        if self.cc & 0xC0 != 0xC0:
            raise ValueError("cc bits 7 and 6 read as 1 on every 6800-family part")

    @property
    def d(self) -> int:
        """A:B as one 16-bit value (the MC6801/6803's D register)."""
        return (self.a << 8) | self.b


__all__ = ["CPUState"]
