"""The package's public surface: everything in __all__ imports and is documented."""

from __future__ import annotations

import inspect

import m6800_python


def test_every_public_name_exists_and_has_a_docstring() -> None:
    for name in m6800_python.__all__:
        value = getattr(m6800_python, name)
        if inspect.isclass(value) or inspect.isfunction(value):
            assert value.__doc__, f"{name} has no docstring"


def test_the_contract_in_one_breath() -> None:
    memory = bytearray(0x10000)
    memory[0xFFFE:0x10000] = b"\x10\x00"
    memory[0x1000:0x1003] = bytes([0x86, 0x2A, 0x4C])
    cpu = m6800_python.M6800(memory.__getitem__, memory.__setitem__)
    cpu.reset()
    assert cpu.step() == 2 and cpu.step() == 2 and cpu.A == 0x2B
    listing = m6800_python.disassemble_range(memory.__getitem__, 0x1000, 2)
    assert [i.text for i in listing] == ["LDAA #$2A", "INCA"]
