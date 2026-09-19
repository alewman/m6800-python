"""The Williams sound board under the debugger (scripts/williams_debug.py).

Skipped unless Robotron's ROM is present (it is copyrighted and never
committed); the MAME comparison through the debugger also needs the capture
that scripts/williams_sound.py describes, and is slow.
"""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import williams_board  # noqa: E402
import williams_debug  # noqa: E402

from m6800_python import BoundaryKind, CommandDebugger, DebugSession, StopReason  # noqa: E402

if not williams_board.ROBOTRON_ZIP.exists():
    pytest.skip("no robotron.zip", allow_module_level=True)

ROM = williams_board.robotron_rom()


def run(debugger: CommandDebugger, command: str) -> tuple[str, ...]:
    return debugger.execute(command).lines


def idle_board(schedule=()):
    """A board past its reset code, parked in the F044 loop with interrupts on."""
    board, debugger = williams_debug.make_debugger(ROM, schedule)
    run(debugger, "break F044")
    assert run(debugger, "run 1000")[0].startswith("stopped: breakpoint")
    run(debugger, "step")  # onto the loop, so the next run leaves the breakpoint
    run(debugger, "delete F044")
    return board, debugger


def test_hand_sent_command_is_taken_by_the_irq_handler() -> None:
    board, debugger = idle_board()
    assert not board.cpu.irq
    lines = run(debugger, "sound DB")
    assert "PIA IRQ=1" in lines[0] and board.cpu.irq  # IRQ line up before the next step
    record = debugger.session.step()
    assert record.kind is BoundaryKind.IRQ and record.after.pc == williams_board.IRQ_HANDLER
    # The handler reads port B, which acknowledges the PIA and drops IRQ.
    run(debugger, "watch 0402 r")
    result = debugger.session.run(max_steps=100)
    assert result.reason is StopReason.WATCHPOINT and result.hits == (("r", 0x0402, 0xDB),)
    assert not board.pia.irq() and not board.cpu.irq


def test_peeking_the_pia_acknowledges_nothing() -> None:
    board, debugger = idle_board()
    run(debugger, "sound DB")
    assert run(debugger, "m 0400 4")[0].startswith("0400  00 3C DB B7")
    assert run(debugger, "pia")[-1] == "IRQ output: 1"
    assert board.pia.cr[1] & 0x80


def test_sound_always_makes_a_cb1_edge() -> None:
    board, debugger = idle_board()
    run(debugger, "sound DB")
    board.pia.cr[1] &= 0x3F  # as if the handler had read it
    run(debugger, "sound DB")
    assert board.pia.irq()
    assert [value for _, value in board.delivered] == [0xDB, 0xFF, 0xDB]


def test_nextsound_delivers_on_schedule_and_the_dac_plays(tmp_path) -> None:
    board, debugger = williams_debug.make_debugger(ROM, [(200_000, 0xDB)])
    assert run(debugger, "schedule") == ("$DB at cycle 200,000 (0.223492 s)",)
    lines = run(debugger, "nextsound")
    assert lines[0].startswith("command $DB arrived at cycle 200,0")
    assert board.delivered[0][0] >= 200_000 and board.cycle - 200_000 < 16
    assert run(debugger, "schedule") == ("no scheduled commands left",)
    run(debugger, "run 60000")
    assert len(board.dac_bytes) > 1000
    assert "commands delivered" in run(debugger, "time")[1]
    assert run(debugger, "wav " + str(tmp_path / "db.wav") + " 0.1")[0].startswith("wrote 0.10 s")
    with wave.open(str(tmp_path / "db.wav")) as sound:
        frames = sound.readframes(sound.getnframes())
    assert len(set(frames)) > 10


def test_help_lists_host_commands_and_clashes_are_refused() -> None:
    _, debugger = williams_debug.make_debugger(ROM)
    assert "Host commands:" in run(debugger, "help")
    with pytest.raises(ValueError, match="clash"):
        CommandDebugger(debugger.session, commands={"step": (lambda a: (), "step")})


def test_session_drives_the_board_and_tracks_the_cpus_bus() -> None:
    board = williams_board.WilliamsSoundBoard(ROM)
    session = DebugSession(board, peek_byte=board.peek, track_accesses=True)
    assert session.cpu is board.cpu and board.cpu.read_byte is not board.read
    record = session.step()
    assert record.instruction.text == "SEI" and board.cycle == record.cycles
    session.close()
    assert board.cpu.read_byte == board.read


@pytest.mark.slow
def test_debugger_path_matches_mame() -> None:
    """The first 13 seconds, run through DebugSession with tracking on, make
    the PIA writes MAME made."""
    if not williams_board.CAPTURE.exists():
        pytest.skip("no Robotron capture (see scripts/williams_sound.py)")
    commands, mame_writes, _ = williams_board.load_capture(williams_board.CAPTURE)
    board, debugger = williams_debug.make_debugger(ROM, commands)
    result = debugger.session.run(max_steps=10_000_000, max_cycles=round(13 * williams_board.CLOCK))
    assert result.reason is StopReason.CYCLE_LIMIT
    ours = [(offset, value) for _, offset, value in board.pia_writes]
    assert len(ours) > 1000
    assert ours == [(offset, value) for _, offset, value in mame_writes[: len(ours)]]
