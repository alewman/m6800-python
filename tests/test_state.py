"""capture_state() / restore_state(): complete, side-effect-free, deterministic."""

from __future__ import annotations

import dataclasses
import random

import pytest
from conftest import make

from m6800_python import CPUState


def test_capture_is_side_effect_free_and_complete(part: str) -> None:
    cpu, bus = make(part, [0x86, 0x42])
    bus.log.clear()
    state = cpu.capture_state()
    assert bus.log == []
    assert (state.a, state.pc, state.sp, state.cc) == (0, 0x1000, 0x01FF, 0xC0)
    assert set(dataclasses.asdict(state)) >= {"a", "b", "x", "sp", "pc", "cc", "waiting"}


def test_restore_then_step_repeats_exactly(part: str) -> None:
    """Capture, run, restore, run again: the same states and the same bus traffic."""
    rng = random.Random(6800)
    for _ in range(300):
        program = [rng.randrange(256) for _ in range(4)]
        cpu, bus = make(part, program, undocumented="mame")
        cpu.A, cpu.B, cpu.X = rng.randrange(256), rng.randrange(256), rng.randrange(0x10000)
        cpu.CC = 0xC0 | rng.randrange(64)
        cpu.irq = rng.random() < 0.3
        memory = bytes(bus.memory)
        before = cpu.capture_state()
        bus.log.clear()
        cpu.step()
        first, log1 = cpu.capture_state(), list(bus.log)
        bus.memory[:] = memory
        bus.log.clear()
        cpu.restore_state(before)
        assert cpu.capture_state() == before
        cpu.step()
        assert cpu.capture_state() == first
        assert bus.log == log1


def test_restore_carries_the_mc6800_cli_rule() -> None:
    # The CLI rule reads the previous opcode, so it must survive a restore.
    cpu, bus = make("6800", [0x0E, 0x86, 0x55])
    bus.set_word(0xFFF8, 0x4000)
    cpu.CC, cpu.irq = 0xD0, True
    even = dataclasses.replace(cpu.capture_state(), opcode=0x4C)  # "INCA ran last"
    cpu.restore_state(even)
    cpu.step()  # CLI after an even opcode: no delay
    assert cpu.step() == 12 and cpu.PC == 0x4000


def test_validation() -> None:
    with pytest.raises(ValueError):
        CPUState(a=256)
    with pytest.raises(ValueError):
        CPUState(cc=0x00)  # bits 7-6 must read 1
    with pytest.raises(ValueError):
        CPUState(irq2=0x1234)
    cpu, _ = make("6800", [])
    with pytest.raises(ValueError, match="irq2"):
        cpu.restore_state(CPUState(irq2=0xFFF4))
    with pytest.raises(TypeError):
        cpu.restore_state({"a": 1})


def test_d_on_the_state() -> None:
    assert CPUState(a=0x12, b=0x34).d == 0x1234
