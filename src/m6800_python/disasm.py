"""Side-effect-free structured disassembly for the 6800 family.

The decode table is built from the same opcode map the core executes
(``_dispatch.OPCODES``) and from the same undocumented-opcode policies
(``_undocumented``), so the disassembler cannot disagree with the core about
which opcodes exist, how long they are, or how they address memory.

Syntax is Motorola's (M68PRM chapter 4): ``LDAA #$12`` immediate, ``LDAA $12``
direct, ``LDAA $1234`` extended, ``LDAA $12,X`` indexed, and branches with
their target resolved to an absolute address.  See docs/disassembly.md.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import cache

from m6800_python._dispatch import OPCODES
from m6800_python._undocumented import (
    HCF_OPCODES,
    MAME_AS_INSTRUCTION,
    MAME_ILLEGAL_LENGTH,
    MEASURED_6800,
    POLICIES,
)

ByteReader = Callable[[int], int]

#: Addressing modes, as ``Instruction.mode`` reports them.
MODES = ("inherent", "immediate", "direct", "indexed", "extended", "relative", "data")

_BRANCHES = frozenset(range(0x20, 0x30)) | {0x8D}
_MODE_NAMES = {
    None: "inherent",
    "imm8": "immediate",
    "imm16": "immediate",
    "dir": "direct",
    "idx": "indexed",
    "ext": "extended",
}
_LENGTHS = {"inherent": 1, "direct": 2, "indexed": 2, "extended": 3, "relative": 2}


@dataclass(frozen=True, slots=True)
class Instruction:
    """One decoded instruction and the exact bytes it occupies."""

    address: int
    data: bytes
    mnemonic: str
    operands: tuple[str, ...] = ()
    mode: str = "inherent"
    #: The absolute address the operand names: the direct, extended or branch
    #: target address, or None (immediate, indexed, inherent, data).
    target: int | None = None
    #: False when Motorola does not assign the opcode on this part.
    documented: bool = True

    def __post_init__(self) -> None:
        if type(self.address) is not int or not 0 <= self.address <= 0xFFFF:
            raise ValueError("address must be an integer in range 0x0000..0xFFFF")
        if type(self.data) is not bytes or not self.data:
            raise ValueError("data must contain at least one byte")
        if type(self.mnemonic) is not str or not self.mnemonic:
            raise ValueError("mnemonic must not be empty")
        if type(self.operands) is not tuple or not all(type(o) is str for o in self.operands):
            raise ValueError("operands must be a tuple of strings")
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")

    @property
    def size(self) -> int:
        """Number of encoded bytes."""
        return len(self.data)

    @property
    def next_address(self) -> int:
        """16-bit address immediately following the encoded instruction."""
        return (self.address + self.size) & 0xFFFF

    @property
    def text(self) -> str:
        """Canonical human-readable assembly text."""
        return self.mnemonic if not self.operands else f"{self.mnemonic} {','.join(self.operands)}"


@dataclass(frozen=True, slots=True)
class _Form:
    mnemonic: str
    mode: str
    length: int
    documented: bool
    # Wheeler's store-immediate forms skip a don't-care byte before the value.
    hole: bool = False


def _part(part: int | str) -> int:
    text = str(part).upper().removeprefix("MC").removeprefix("M")
    if text in ("6800", "6802", "6808"):
        return 6800
    if text in ("6801", "6803", "6801U4"):
        return 6801
    raise ValueError(f"part must be 6800, 6802, 6808, 6801 or 6803, not {part!r}")


@cache
def decode_table(part: int | str = 6800, undocumented: str = "strict") -> tuple[_Form, ...]:
    """The 256 forms ``part`` executes under ``undocumented``, as the core runs them."""
    if undocumented not in POLICIES:
        raise ValueError(f"undocumented must be one of {POLICIES}, not {undocumented!r}")
    number = _part(part)
    table = []
    for opcode in range(256):
        handler, mode, cycles_6800, cycles_6801 = OPCODES.get(opcode, (None, None, None, None))
        cycles = cycles_6800 if number == 6800 else cycles_6801
        if cycles is not None:
            table.append(_documented_form(opcode, handler, mode))
        else:
            table.append(_undocumented_form(number, undocumented, opcode))
    return tuple(table)


def _documented_form(opcode: int, handler: str, mode: str | None, documented: bool = True):
    name = "relative" if opcode in _BRANCHES else _MODE_NAMES[mode]
    length = {"imm8": 2, "imm16": 3}.get(mode, _LENGTHS.get(name, 1))
    return _Form(handler.upper(), name, length, documented)


def _undocumented_form(part: int, policy: str, opcode: int) -> _Form:
    if policy == "mame":
        known = MAME_AS_INSTRUCTION[part].get(opcode)
        if known is not None:
            handler, mode, _cycles = known
            return _documented_form(opcode, handler, mode, documented=False)
        return _Form("FCB", "data", MAME_ILLEGAL_LENGTH[part].get(opcode, 1), False)
    if part == 6800 and opcode in HCF_OPCODES:
        return _Form("HCF", "inherent", 1, False)
    if policy == "measured" and part == 6800 and opcode in MEASURED_6800:
        if opcode == 0x14:
            return _Form("NBA", "inherent", 1, False)  # Wheeler's name
        if opcode == 0x15:
            return _Form("NOP", "inherent", 1, False)
        wide = opcode in (0x8F, 0xCF)
        name = {0x87: "STAA", 0xC7: "STAB", 0x8F: "STS", 0xCF: "STX"}[opcode]
        return _Form(name, "immediate", 4 if wide else 3, False, hole=True)
    return _Form("FCB", "data", 1, False)


def disassemble(
    reader: ByteReader,
    address: int,
    *,
    part: int | str = 6800,
    undocumented: str = "strict",
) -> Instruction:
    """Decode the instruction at ``address`` using only ``reader``.

    ``reader`` must be side-effect-free (a peek, not the host's bus read);
    it is called with 16-bit addresses and must return byte values.
    """
    if type(address) is not int or not 0 <= address <= 0xFFFF:
        raise ValueError("address must be an integer in range 0x0000..0xFFFF")
    form = decode_table(part, undocumented)[_byte(reader, address)]
    data = bytes(_byte(reader, (address + n) & 0xFFFF) for n in range(form.length))
    operands: tuple[str, ...] = ()
    target = None
    if form.mode == "data":
        operands = (",".join(f"${b:02X}" for b in data),)
    elif form.hole:
        # Wheeler: the byte after the opcode is a don't-care hole, and the
        # register is stored over the next one (or two).
        target = (address + 2) & 0xFFFF
        operands = ("#",)
    elif form.mode == "immediate":
        value = data[1] if form.length == 2 else (data[1] << 8) | data[2]
        operands = (f"#${value:0{2 * (form.length - 1)}X}",)
    elif form.mode == "direct":
        target = data[1]
        operands = (f"${target:02X}",)
    elif form.mode == "extended":
        target = (data[1] << 8) | data[2]
        operands = (f"${target:04X}",)
    elif form.mode == "indexed":
        operands = (f"${data[1]:02X}", "X")
    elif form.mode == "relative":
        offset = data[1] - 0x100 if data[1] & 0x80 else data[1]
        target = (address + 2 + offset) & 0xFFFF
        operands = (f"${target:04X}",)
    return Instruction(address, data, form.mnemonic, operands, form.mode, target, form.documented)


def disassemble_bytes(
    data: Sequence[int] | bytes,
    address: int = 0,
    *,
    part: int | str = 6800,
    undocumented: str = "strict",
) -> Instruction:
    """Decode one instruction from ``data``, whose first byte sits at ``address``."""
    copy = bytes(data)
    if not copy:
        raise ValueError("data must not be empty")

    def reader(where: int) -> int:
        offset = (where - address) & 0xFFFF
        if offset >= len(copy):
            raise ValueError(f"instruction at 0x{address:04X} runs past the supplied bytes")
        return copy[offset]

    return disassemble(reader, address, part=part, undocumented=undocumented)


def disassemble_range(
    reader: ByteReader,
    address: int,
    count: int,
    *,
    part: int | str = 6800,
    undocumented: str = "strict",
) -> list[Instruction]:
    """Decode ``count`` consecutive instructions starting at ``address``."""
    listing = []
    for _ in range(count):
        instruction = disassemble(reader, address, part=part, undocumented=undocumented)
        listing.append(instruction)
        address = instruction.next_address
    return listing


def _byte(reader: ByteReader, address: int) -> int:
    value = reader(address)
    if type(value) is not int or not 0 <= value <= 0xFF:
        raise ValueError(f"byte reader returned a non-byte value at 0x{address:04X}")
    return value


__all__ = [
    "MODES",
    "ByteReader",
    "Instruction",
    "decode_table",
    "disassemble",
    "disassemble_bytes",
    "disassemble_range",
]
