"""The three policies for unassigned opcodes: strict, measured, mame.

HCF is measured on silicon (Wheeler 1977; Doc TB 2019) as far as "it halts
until reset".  The ``"measured"`` behaviours are Wheeler's Table 1 and Figure 1
(BYTE, December 1977, pp. 46-47) and Doc TB's MC6800P observations.  The
``undocumented="mame"`` behaviours are MAME 0.285's guesses (emulator-derived,
`[unverified]`), tested only to prove the core reproduces MAME's code.
"""

from __future__ import annotations

import pytest
from conftest import make

from m6800_python import UndocumentedOpcode


@pytest.mark.parametrize("policy", ["strict", "measured"])
@pytest.mark.parametrize("opcode", [0x9D, 0xDD, 0xFD, 0xCD, 0xED])
def test_hcf_family_halts_until_reset(opcode: int, policy: str) -> None:
    cpu, bus = make("6800", [opcode, 0x00], undocumented=policy)
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


def test_mame_policy_store_immediate_writes_into_the_instruction_stream() -> None:
    cpu, bus = make("6800", [0x87, 0x00], undocumented="mame")  # "STAA #"
    cpu.A = 0x80
    assert cpu.step() == 3
    assert bus.writes() == [(0x1001, 0x80)] and cpu.PC == 0x1002 and cpu.CC & 0x08
    cpu, bus = make("6803", [0xCF, 0x00, 0x00], undocumented="mame")  # "STX #"
    cpu.X = 0x1234
    assert cpu.step() == 3
    assert bus.writes() == [(0x1001, 0x12), (0x1002, 0x34)] and cpu.PC == 0x1003


def test_mame_policy_hcf_opcodes_on_the_6800() -> None:
    cpu, _ = make("6800", [0x9D, 0x40], undocumented="mame")  # MAME: JSR direct
    assert cpu.step() == 6 and cpu.PC == 0x0040 and not cpu.halted
    cpu, _ = make("6800", [0xDD, 0x40, 0x01], undocumented="mame")  # MAME: 2-byte no-op
    assert cpu.step() == 4 and cpu.PC == 0x1002


def test_mame_policy_brn_on_the_6800() -> None:
    cpu, _ = make("6800", [0x21, 0x40], undocumented="mame")
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
def test_mame_policy_illegal_opcodes_skip_their_length(part: str, opcode: int, length: int) -> None:
    cpu, bus = make(part, [opcode, 0xAA, 0xBB], undocumented="mame")
    assert cpu.step() == 4
    assert cpu.PC == 0x1000 + length and bus.writes() == []


def test_strict_is_the_default() -> None:
    cpu, _ = make("6800", [0x02])
    with pytest.raises(UndocumentedOpcode, match=r"\$02 at \$1000"):
        cpu.step()


# -- "measured": Wheeler (BYTE, Dec 1977, pp. 46-47) and Doc TB (x86.fr, 2019) --


def test_measured_nba_ands_the_accumulators() -> None:
    # Wheeler, Table 1: $14 NBA, A.B -> A, next instruction PC + 1.
    cpu, _ = make("6800", [0x14], undocumented="measured")
    cpu.A, cpu.B, cpu.CC = 0xF0, 0x9C, 0xC0 | 0x02 | 0x01
    assert cpu.step() == 2  # Doc TB: 2 cycles
    assert cpu.A == 0x90 and cpu.B == 0x9C and cpu.PC == 0x1001
    assert cpu.CC == 0xC0 | 0x08 | 0x01  # N set, Z clear, V cleared, C kept


def test_measured_15_is_a_two_cycle_nop() -> None:
    cpu, bus = make("6800", [0x15], undocumented="measured")
    cpu.A, cpu.B, cpu.CC = 0x12, 0x34, 0xC5
    assert cpu.step() == 2
    assert (cpu.A, cpu.B, cpu.CC, cpu.PC) == (0x12, 0x34, 0xC5, 0x1001)
    assert bus.writes() == []


@pytest.mark.parametrize(
    ("opcode", "register", "value", "stored", "length"),
    [
        (0x87, "A", 0x5A, [0x5A], 3),
        (0xC7, "B", 0xA5, [0xA5], 3),
        (0x8F, "SP", 0x1234, [0x12, 0x34], 4),
        (0xCF, "X", 0xBEEF, [0xBE, 0xEF], 4),
    ],
)
def test_measured_store_immediate_skips_a_hole(opcode, register, value, stored, length) -> None:
    # Wheeler, Table 1 and Figure 1: store at PC+2 (and PC+3); PC+1 is a
    # don't-care hole; STAA/STAB # are three bytes, STS/STX # four.
    cpu, bus = make("6800", [opcode, 0xEE, 0x00, 0x00], undocumented="measured")
    setattr(cpu, register, value)
    cpu.step()
    assert bus.writes() == [(0x1002 + n, byte) for n, byte in enumerate(stored)]
    assert bus.memory[0x1001] == 0xEE  # the hole is untouched
    assert cpu.PC == 0x1000 + length


def test_measured_leaves_the_rest_raising() -> None:
    for opcode in (0x00, 0x02, 0x41, 0x21):
        cpu, _ = make("6800", [opcode], undocumented="measured")
        with pytest.raises(UndocumentedOpcode):
            cpu.step()


def test_measured_is_strict_on_the_6803() -> None:
    for opcode in (0x14, 0x15, 0x87, 0xCF):
        cpu, _ = make("6803", [opcode, 0, 0, 0], undocumented="measured")
        with pytest.raises(UndocumentedOpcode):
            cpu.step()


def test_unknown_policy_is_refused() -> None:
    with pytest.raises(ValueError):
        make("6800", [], undocumented="guess")


def test_a_trapped_opcode_leaves_the_state_untouched(part: str) -> None:
    # _undocumented.py promises "the CPU state unchanged, PC still pointing at
    # the opcode": step() shifts the opcode history before dispatch, so it has
    # to put it back when the trap propagates.
    trapped = 0x00  # unassigned on every part in this family
    cpu, _bus = make(part, [0x01, trapped])  # NOP, then the trap
    cpu.step()
    before = cpu.capture_state()
    with pytest.raises(UndocumentedOpcode) as raised:
        cpu.step()
    assert raised.value.address == 0x1001
    assert cpu.capture_state() == before
