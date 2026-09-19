"""CommandDebugger: each command's output, errors, and the interactive loop."""

from __future__ import annotations

import io

import pytest
from conftest import make

from m6800_python import CommandDebugger, CommandError, DebugSession
from m6800_python.console import parse_number

PROGRAM = [0x86, 0x05, 0xBD, 0x10, 0x10, 0x01, 0x20, 0xFE]  # LDAA #5; JSR $1010; NOP; BRA *
SUBROUTINE = [0x4C, 0x39]  # $1010: INCA; RTS


def debugger(part: str = "6800", track: bool = True):
    cpu, bus = make(part, PROGRAM)
    bus.load(0x1010, SUBROUTINE)
    session = DebugSession(cpu, peek_byte=bus.memory.__getitem__, track_accesses=track)
    return cpu, CommandDebugger(session)


def run(d: CommandDebugger, command: str) -> tuple[str, ...]:
    return d.execute(command).lines


def test_registers_and_flags() -> None:
    cpu, d = debugger()
    cpu.CC = 0xC0 | 0x28
    assert run(d, "regs")[0] == "A=00 B=00 X=0000 SP=01FF PC=1000 CC=E8 H-N---"
    _, d6803 = debugger("6803")
    assert "D=0000" in run(d6803, "r")[0]


def test_disassemble_marks_pc_and_breakpoints() -> None:
    _, d = debugger()
    run(d, "break 1002")
    lines = run(d, "d 1000 3")
    assert lines[0] == "> 1000  86 05       LDAA #$05"
    assert lines[1] == "* 1002  BD 10 10    JSR $1010"


def test_step_over_and_run() -> None:
    cpu, d = debugger()
    assert run(d, "step")[0].startswith("#0 1000  86 05       LDAA #$05")
    lines = run(d, "over")  # the JSR runs through INCA and RTS
    assert cpu.PC == 0x1005 and cpu.A == 6 and lines[-2].startswith("A=06")
    assert run(d, "run 10")[0].startswith("stopped: step_limit, 10 steps")


def test_counts_are_decimal_and_addresses_hex() -> None:
    assert parse_number("10", decimal=True) == 10
    assert parse_number("10") == 0x10
    assert parse_number("$10", decimal=True) == 0x10
    assert parse_number("#10") == 10
    _, d = debugger()
    run(d, "step 3")
    assert len(d.session.history) == 3


def test_set_irq_nmi_reset() -> None:
    cpu, d = debugger()
    run(d, "set a 7f")
    run(d, "set cc 0")
    assert cpu.A == 0x7F and cpu.CC == 0xC0  # bits 7-6 stay set
    run(d, "irq on")
    assert cpu.irq
    run(d, "nmi")
    assert cpu.capture_state().nmi_pending
    with pytest.raises(CommandError, match="no register D"):
        run(d, "set d 1234")


def test_watch_memory_history_and_errors() -> None:
    _, d = debugger()
    assert run(d, "watch 01FF w") == ("watch 01FF w",)
    lines = run(d, "run 100")
    assert lines[0].startswith("stopped: watchpoint") and lines[1] == "  w $01FF = $05"
    assert run(d, "m 1000 8")[0].startswith("1000  86 05 BD 10 10 01 20 FE")
    assert run(d, "history 1")[0].startswith("#1 1002")
    assert run(d, "breakpoints") == ("watch 01FF w",)
    with pytest.raises(CommandError, match="unknown command"):
        run(d, "frobnicate")
    with pytest.raises(CommandError, match="takes"):
        run(d, "break")


def test_interact_loop() -> None:
    _, d = debugger()
    out = io.StringIO()
    d.interact(io.StringIO("r\nbogus\nstep\nquit\nr\n"), out)
    text = out.getvalue()
    assert text.count("m6800> ") == 4 and "error: unknown command: bogus" in text
    assert "LDAA #$05" in text
