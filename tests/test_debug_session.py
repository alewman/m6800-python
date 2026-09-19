"""DebugSession: boundary prediction, stops, history, access tracking."""

from __future__ import annotations

import random

import pytest
from conftest import make

from m6800_python import BoundaryKind, DebugSession, StopReason, next_boundary


def session_for(part: str, program: list[int], **kwargs):
    cpu, bus = make(part, program, undocumented=kwargs.pop("undocumented", "strict"))
    return cpu, bus, DebugSession(cpu, peek_byte=bus.memory.__getitem__, **kwargs)


def test_step_record_carries_disassembly_and_states(part: str) -> None:
    _, _, session = session_for(part, [0x86, 0x42])
    record = session.step()
    assert record.kind is BoundaryKind.INSTRUCTION
    assert record.instruction.text == "LDAA #$42"
    assert (record.before.a, record.after.a, record.cycles) == (0x00, 0x42, 2)
    assert session.total_instructions == 1 and session.history == (record,)


def test_next_boundary_predicts_what_step_does() -> None:
    """For random interrupt situations, the predicted kind is what happened."""
    rng = random.Random(1)
    for _ in range(2000):
        part = rng.choice(["6800", "6803"])
        cpu, bus, session = session_for(part, [0x01], undocumented="mame")
        bus.set_word(0xFFF8, 0x4000)
        bus.set_word(0xFFFC, 0x5000)
        bus.set_word(0xFFF4, 0x6000)
        cpu.CC = 0xC0 | rng.randrange(64)
        cpu.irq = rng.random() < 0.4
        cpu.nmi = rng.random() < 0.2
        cpu._irq_inhibit = rng.random() < 0.2
        cpu.waiting = rng.random() < 0.2
        if part == "6803" and rng.random() < 0.3:
            cpu.irq2 = 0xFFF4
        predicted = next_boundary(cpu.capture_state())
        record = session.step()
        assert record.kind is predicted
        expected_pc = {
            BoundaryKind.NMI: 0x5000,
            BoundaryKind.IRQ: 0x4000,
            BoundaryKind.IRQ2: 0x6000,
            BoundaryKind.WAIT_IDLE: 0x1000,
            BoundaryKind.INSTRUCTION: 0x1001,
        }[predicted]
        assert cpu.PC == expected_pc


def test_breakpoint_stops_before_and_run_leaves_it(part: str) -> None:
    cpu, _, session = session_for(part, [0x01, 0x01, 0x01, 0x20, 0xFB])  # NOPs, BRA back
    session.add_breakpoint(0x1002)
    result = session.run(max_steps=100)
    assert result.reason is StopReason.BREAKPOINT and cpu.PC == 0x1002 and result.steps == 2
    again = session.run(max_steps=100)  # starts on the breakpoint: leaves it, hits it again
    assert again.reason is StopReason.BREAKPOINT and again.steps == 4


def test_wait_halt_undocumented_and_limits() -> None:
    _, _, session = session_for("6800", [0x0F, 0x3E])  # SEI; WAI: nothing can end it
    assert session.run(max_steps=10).reason is StopReason.WAITING
    _, _, session = session_for("6800", [0x9D])
    assert session.run(max_steps=10).reason is StopReason.HALTED
    cpu, _, session = session_for("6800", [0x01, 0x02])
    result = session.run(max_steps=10)
    assert result.reason is StopReason.UNDOCUMENTED and cpu.PC == 0x1001
    assert result.error.opcode == 0x02
    _, _, session = session_for("6800", [0x20, 0xFE])
    assert session.run(max_steps=5).reason is StopReason.STEP_LIMIT
    result = session.run(max_steps=100, max_cycles=10)
    assert result.reason is StopReason.CYCLE_LIMIT and result.cycles == 12


def test_access_tracking_and_watchpoints(part: str) -> None:
    program = [0x86, 0x07, 0xB7, 0x20, 0x00, 0xB6, 0x30, 0x00, 0x01]
    cpu, bus, session = session_for(part, program, track_accesses=True)
    record = session.step()
    assert record.accesses == (("r", 0x1000, 0x86), ("r", 0x1001, 0x07))
    session.add_watchpoint(0x2000, "w")
    session.add_watchpoint(0x3000, "r")
    result = session.run(max_steps=10)
    assert result.reason is StopReason.WATCHPOINT and result.hits == (("w", 0x2000, 7),)
    result = session.run(max_steps=10)
    assert result.reason is StopReason.WATCHPOINT and result.hits == (("r", 0x3000, 0),)
    session.close()
    assert cpu.read_byte == bus.read and cpu.write_byte == bus.write


def test_watchpoints_need_tracking() -> None:
    _, _, session = session_for("6800", [])
    with pytest.raises(ValueError, match="track_accesses"):
        session.add_watchpoint(0x2000)


def test_history_is_bounded() -> None:
    _, _, session = session_for("6800", [0x20, 0xFE], history_limit=3)
    for _ in range(10):
        session.step()
    assert [r.sequence for r in session.history] == [7, 8, 9]
    assert next(session.iter_history(newest_first=True)).sequence == 9


def test_interrupt_records_have_no_instruction(part: str) -> None:
    cpu, bus, session = session_for(part, [0x01])
    bus.set_word(0xFFF8, 0x4000)
    cpu.irq = True
    record = session.step()
    assert record.kind is BoundaryKind.IRQ and record.instruction is None
    assert record.cycles == 12
