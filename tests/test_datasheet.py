"""Every documented opcode against the manuals' Appendix A, for both parts.

tests/datasheet.py is the per-opcode table extracted from M68PRM (MC6800) and
M6801RM (MC6801/6803) by scripts/extract_manual_tables.py.  For each opcode a
part documents, this module runs the instruction from many random machine
states and checks what the table states outright:

* the cycle count ``step()`` returns;
* the instruction length, as the distance PC moves (for everything that does
  not transfer control);
* every condition-code bit the manual marks ``-`` (unchanged), ``0`` or ``1``.

Bits marked ``*`` are rules, and are checked by the per-family modules against
the manual's Boolean formulae.  The manuals are the judge here (tier:
datasheet); nothing in this module comes from MAME.
"""

from __future__ import annotations

import random

import pytest
from conftest import make
from datasheet import DATASHEET

from m6800_python import UndocumentedOpcode
from m6800_python._dispatch import OPCODES

FLAG_BITS = {"H": 0x20, "I": 0x10, "N": 0x08, "Z": 0x04, "V": 0x02, "C": 0x01}
# Instructions that move PC somewhere other than the next instruction.
CONTROL = {"JMP", "JSR", "BSR", "RTS", "RTI", "SWI"}
BRANCHES = {o.mnemonic for o in DATASHEET.values() if o.mode == "relative"} - {"BSR"}
STATES = 40


def documented(part: str) -> list[int]:
    if part == "6800":
        return [op for op, o in DATASHEET.items() if o.cycles_6800 is not None]
    return [op for op, o in DATASHEET.items() if o.cycles_6801 is not None]


def spec(part: str, opcode: int) -> tuple[int, str]:
    o = DATASHEET[opcode]
    return (o.cycles_6800, o.flags_6800) if part == "6800" else (o.cycles_6801, o.flags_6801)


def test_counts_match_the_manuals() -> None:
    assert len(documented("6800")) == 197  # M68PRM
    assert len(documented("6803")) == 220  # M6801RM


def test_dispatch_map_is_the_datasheet() -> None:
    """_dispatch.OPCODES was generated from the datasheet; it must not drift."""
    assert set(OPCODES) == set(DATASHEET)
    for opcode, (handler, _mode, cycles_6800, cycles_6801) in OPCODES.items():
        o = DATASHEET[opcode]
        assert handler.upper() == o.mnemonic, f"${opcode:02X}"
        assert (cycles_6800, cycles_6801) == (o.cycles_6800, o.cycles_6801), f"${opcode:02X}"


def _random_state(cpu, bus, rng: random.Random, opcode: int) -> int:
    """Randomise registers and the operand bytes; return the instruction's address."""
    bus.memory[:] = rng.randbytes(0x10000)
    cpu.waiting = cpu.halted = False
    pc = rng.randrange(0x0200, 0xF000)
    bus.memory[pc] = opcode
    cpu.PC = pc
    cpu.A, cpu.B = rng.randrange(256), rng.randrange(256)
    cpu.X = rng.randrange(0x10000)
    cpu.SP = rng.randrange(0x0100, 0x10000)
    cpu.CC = 0xC0 | rng.randrange(64)
    return pc


@pytest.mark.parametrize("opcode", documented("6800"), ids=lambda op: f"{op:02X}")
def test_mc6800_opcode(opcode: int) -> None:
    _check_opcode("6800", opcode)


@pytest.mark.parametrize("opcode", documented("6803"), ids=lambda op: f"{op:02X}")
def test_mc6803_opcode(opcode: int) -> None:
    _check_opcode("6803", opcode)


def _check_opcode(part: str, opcode: int) -> None:
    o = DATASHEET[opcode]
    cycles, flags = spec(part, opcode)
    page = o.page_6800 if part == "6800" else o.page_6801
    rng = random.Random(opcode * 7919 + (part == "6803"))
    cpu, bus = make(part)
    for _ in range(STATES):
        pc = _random_state(cpu, bus, rng, opcode)
        before = cpu.CC
        assert cpu.step() == cycles, f"{o.mnemonic} ${opcode:02X} cycles ({page})"
        if o.mnemonic == "WAI":
            assert cpu.waiting
        if o.mnemonic not in CONTROL and not (o.mnemonic in BRANCHES and cpu.PC != pc + 2):
            assert cpu.PC == (pc + o.length) & 0xFFFF, f"{o.mnemonic} ${opcode:02X} length"
        after = cpu.CC
        assert after & 0xC0 == 0xC0, "CC bits 7 and 6 must stay set"
        for name, rule in zip("HINZVC", flags, strict=True):
            bit = FLAG_BITS[name]
            if rule == "-":
                assert after & bit == before & bit, f"{o.mnemonic} changed {name} ({page})"
            elif rule == "0":
                assert not after & bit, f"{o.mnemonic} left {name} set ({page})"
            elif rule == "1":
                assert after & bit, f"{o.mnemonic} left {name} clear ({page})"


@pytest.mark.parametrize("part", ["6800", "6803"])
def test_undocumented_opcodes_raise_and_leave_state(part: str) -> None:
    documented_here = set(documented(part))
    hcf = {0x9D, 0xDD} if part == "6800" else set()
    for opcode in range(256):
        if opcode in documented_here or opcode in hcf:
            continue
        cpu, bus = make(part, [opcode, 0x12, 0x34])
        with pytest.raises(UndocumentedOpcode) as raised:
            cpu.step()
        assert raised.value.opcode == opcode
        assert cpu.PC == 0x1000
        assert bus.writes() == []
