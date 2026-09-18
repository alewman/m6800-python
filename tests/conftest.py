"""Shared test fixtures: a 64 KiB bus that records every access."""

from __future__ import annotations

import pytest

from m6800_python import M6800, M6803


class Bus:
    """Flat RAM with an access log, standing in for a host."""

    def __init__(self) -> None:
        self.memory = bytearray(0x10000)
        self.log: list[tuple[str, int, int]] = []

    def read(self, address: int) -> int:
        value = self.memory[address]
        self.log.append(("r", address, value))
        return value

    def write(self, address: int, value: int) -> None:
        assert 0 <= address <= 0xFFFF and 0 <= value <= 0xFF
        self.memory[address] = value
        self.log.append(("w", address, value))

    def load(self, address: int, data: bytes | list[int]) -> None:
        self.memory[address : address + len(data)] = bytes(data)

    def word(self, address: int) -> int:
        return (self.memory[address] << 8) | self.memory[(address + 1) & 0xFFFF]

    def set_word(self, address: int, value: int) -> None:
        self.memory[address] = value >> 8
        self.memory[(address + 1) & 0xFFFF] = value & 0xFF

    def writes(self) -> list[tuple[int, int]]:
        return [(a, v) for kind, a, v in self.log if kind == "w"]


PARTS = {"6800": M6800, "6803": M6803}


def make(part: str, program: bytes | list[int] = b"", *, at: int = 0x1000, **kwargs):
    """A CPU of ``part`` with ``program`` at ``at``, PC there, SP at $01FF, I clear."""
    bus = Bus()
    bus.load(at, program)
    cpu = PARTS[part](bus.read, bus.write, **kwargs)
    cpu.PC = at
    cpu.SP = 0x01FF
    cpu.CC = 0xC0
    return cpu, bus


@pytest.fixture(params=sorted(PARTS))
def part(request) -> str:
    return request.param
