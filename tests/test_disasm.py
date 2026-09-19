"""The disassembler: format, side-effect freedom, and agreement with the core."""

from __future__ import annotations

import random

import pytest
from conftest import make
from datasheet import DATASHEET

from m6800_python import UndocumentedOpcode, disassemble, disassemble_bytes, disassemble_range
from m6800_python.disasm import decode_table

PARTS_AND_POLICIES = [
    (part, policy) for part in ("6800", "6803") for policy in ("strict", "measured", "mame")
]
# Instructions that move PC somewhere other than the next instruction.
CONTROL = {"JMP", "JSR", "BSR", "RTS", "RTI", "SWI", "BRA", "WAI"}


@pytest.mark.parametrize(
    ("data", "address", "text", "mode", "target"),
    [
        ([0x86, 0x12], 0x1000, "LDAA #$12", "immediate", None),
        ([0xCE, 0x12, 0x34], 0, "LDX #$1234", "immediate", None),
        ([0x96, 0x40], 0, "LDAA $40", "direct", 0x40),
        ([0xB7, 0x20, 0x00], 0, "STAA $2000", "extended", 0x2000),
        ([0xB7, 0x00, 0x40], 0, "STAA $0040", "extended", 0x40),  # extended stays 4 digits
        ([0xA6, 0xFF], 0, "LDAA $FF,X", "indexed", None),
        ([0x26, 0xFE], 0x1234, "BNE $1234", "relative", 0x1234),
        ([0x20, 0x80], 0x1000, "BRA $0F82", "relative", 0x0F82),
        ([0x8D, 0x10], 0xFFF0, "BSR $0002", "relative", 0x0002),  # wraps
        ([0x1B], 0, "ABA", "inherent", None),
        ([0x3F], 0, "SWI", "inherent", None),
    ],
)
def test_motorola_syntax(data, address, text, mode, target) -> None:
    instruction = disassemble_bytes(data, address)
    assert (instruction.text, instruction.mode, instruction.target) == (text, mode, target)
    assert instruction.data == bytes(data) and instruction.documented


def test_parts_differ_where_the_manuals_do() -> None:
    assert disassemble_bytes([0x3D], part=6803).text == "MUL"
    assert disassemble_bytes([0x3D], part=6800).text == "FCB $3D"
    assert disassemble_bytes([0x9D, 0x40], part="MC6803").text == "JSR $40"
    assert disassemble_bytes([0x9D, 0x40], part=6800).text == "HCF"
    assert disassemble_bytes([0x21, 0x10], 0x1000, part=6801).text == "BRN $1012"


def test_undocumented_policies() -> None:
    strict = disassemble_bytes([0x87, 0xEE, 0x00])
    measured = disassemble_bytes([0x87, 0xEE, 0x00], undocumented="measured")
    mame = disassemble_bytes([0x87, 0xEE, 0x00], undocumented="mame")
    assert (strict.text, strict.size, strict.documented) == ("FCB $87", 1, False)
    assert (measured.text, measured.size, measured.target) == ("STAA #", 3, 2)  # Wheeler
    assert (mame.text, mame.size) == ("STAA #$EE", 2)
    assert disassemble_bytes([0x14], undocumented="measured").text == "NBA"
    assert disassemble_bytes([0x61, 0x00], undocumented="mame").text == "FCB $61,$00"


def test_reads_only_the_instruction_bytes() -> None:
    touched = []

    def peek(address: int) -> int:
        touched.append(address)
        return {0x2000: 0xB6, 0x2001: 0x12, 0x2002: 0x34}.get(address, 0)

    instruction = disassemble(peek, 0x2000)
    assert instruction.text == "LDAA $1234"
    assert sorted(set(touched)) == [0x2000, 0x2001, 0x2002]


def test_range_and_truncation() -> None:
    memory = bytes([0x86, 0x01, 0x8B, 0x02, 0x20, 0xFA])
    listing = disassemble_range(lambda a: memory[a] if a < len(memory) else 0, 0, 3)
    assert [i.text for i in listing] == ["LDAA #$01", "ADDA #$02", "BRA $0000"]
    with pytest.raises(ValueError, match="runs past"):
        disassemble_bytes([0xB6, 0x12])


def test_documented_lengths_are_the_datasheet() -> None:
    for part, column in (("6800", "cycles_6800"), ("6803", "cycles_6801")):
        table = decode_table(part)
        for opcode, entry in DATASHEET.items():
            if getattr(entry, column) is not None:
                assert table[opcode].length == entry.length, f"${opcode:02X}"
                assert table[opcode].mnemonic == entry.mnemonic


@pytest.mark.parametrize(("part", "policy"), PARTS_AND_POLICIES)
def test_the_core_consumes_exactly_the_decoded_bytes(part: str, policy: str) -> None:
    """For every opcode that neither raises, halts nor transfers control, running
    it moves PC exactly as far as the disassembler says it is long."""
    rng = random.Random(42)
    table = decode_table(part, policy)
    for opcode in range(256):
        form = table[opcode]
        if form.mnemonic in CONTROL or form.mnemonic == "HCF":
            continue
        if form.mode == "relative" and form.mnemonic != "BRN":
            continue
        for _ in range(8):
            cpu, bus = make(
                part, [opcode, rng.randrange(256), rng.randrange(256)], undocumented=policy
            )
            cpu.X, cpu.SP = rng.randrange(0x10000), 0x0400
            try:
                cpu.step()
            except UndocumentedOpcode:
                assert form.mnemonic == "FCB" and policy != "mame", f"${opcode:02X}"
                break
            if bus.memory[0x1000] != opcode:
                break  # the instruction stored over itself; PC is still right, but skip
            assert (
                cpu.PC
                == disassemble(
                    bus.memory.__getitem__, 0x1000, part=part, undocumented=policy
                ).next_address
            ), f"${opcode:02X}"
