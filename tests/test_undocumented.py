"""HCF and the MAME-compatibility behaviour of unassigned opcodes.

HCF is hardware-captured (Doc TB, 2019) as far as "it halts until reset"; the
``mame_compat`` behaviours are MAME 0.285's guesses (emulator-derived,
`[unverified]`), tested here only to prove the core reproduces MAME's code.
"""

from __future__ import annotations

import pytest
from conftest import make

from m6800_python import UndocumentedOpcode


@pytest.mark.parametrize("opcode", [0x9D, 0xDD])
def test_hcf_halts_until_reset(opcode: int) -> None:
    cpu, bus = make("6800", [opcode, 0x00])
    bus.set_word(0xFFFE, 0x2000)
    bus.set_word(0xFFFC, 0x3000)
    cpu.step()
    assert cpu.halted
    cpu.irq = True
    cpu.pulse_nmi()
    for _ in range(10):
        assert cpu.step() == 1
        assert cpu.halted
    assert bus.writes() == []
    cpu.reset()
    assert not cpu.halted and cpu.PC == 0x2000


def test_9d_and_dd_are_instructions_on_the_6803() -> None:
    cpu, _ = make("6803", [0x9D, 0x40])
    cpu.step()
    assert not cpu.halted and cpu.PC == 0x0040


def test_mame_compat_store_immediate_writes_into_the_instruction_stream() -> None:
    cpu, bus = make("6800", [0x87, 0x00], mame_compat=True)  # "STAA #"
    cpu.A = 0x80
    assert cpu.step() == 3
    assert bus.writes() == [(0x1001, 0x80)] and cpu.PC == 0x1002 and cpu.CC & 0x08
    cpu, bus = make("6803", [0xCF, 0x00, 0x00], mame_compat=True)  # "STX #"
    cpu.X = 0x1234
    assert cpu.step() == 3
    assert bus.writes() == [(0x1001, 0x12), (0x1002, 0x34)] and cpu.PC == 0x1003


def test_mame_compat_hcf_opcodes_on_the_6800() -> None:
    cpu, _ = make("6800", [0x9D, 0x40], mame_compat=True)  # MAME: JSR direct
    assert cpu.step() == 6 and cpu.PC == 0x0040 and not cpu.halted
    cpu, _ = make("6800", [0xDD, 0x40, 0x01], mame_compat=True)  # MAME: 2-byte no-op
    assert cpu.step() == 4 and cpu.PC == 0x1002


def test_mame_compat_brn_on_the_6800() -> None:
    cpu, _ = make("6800", [0x21, 0x40], mame_compat=True)
    assert cpu.step() == 4 and cpu.PC == 0x1002


@pytest.mark.parametrize(
    ("part", "opcode", "length"),
    [
        ("6800", 0x02, 1),
        ("6800", 0x61, 2),
        ("6800", 0x71, 3),
        ("6800", 0xCD, 3),
        ("6803", 0x02, 1),
        ("6803", 0x61, 1),
        ("6803", 0x71, 1),
    ],
)
def test_mame_compat_illegal_opcodes_skip_their_length(part: str, opcode: int, length: int) -> None:
    cpu, bus = make(part, [opcode, 0xAA, 0xBB], mame_compat=True)
    assert cpu.step() == 4
    assert cpu.PC == 0x1000 + length and bus.writes() == []


def test_strict_is_the_default() -> None:
    cpu, _ = make("6800", [0x02])
    with pytest.raises(UndocumentedOpcode, match=r"\$02 at \$1000"):
        cpu.step()
