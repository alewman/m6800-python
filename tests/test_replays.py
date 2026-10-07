"""Rungs 3 and 4 under pytest: real code replayed against MAME 0.285 traces.

Each test is skipped unless its trace or capture exists locally (they are made
from copyrighted ROMs and are gitignored; scripts/replay_trace.py GAME and
scripts/williams_sound.py print the commands that record them).  Marked slow:
the Kid Niki replay alone is ten million instructions.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import m6803_board  # noqa: E402
import replay_trace  # noqa: E402
import williams_sound  # noqa: E402

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("game", sorted(replay_trace.MACHINES))
def test_trace_replays_without_divergence(game: str, capsys) -> None:
    trace = ROOT / "mame-work" / game / "error.log"
    if not trace.exists():
        pytest.skip(f"no MAME trace for {game} (python scripts/replay_trace.py {game})")
    assert replay_trace.replay(game, trace) == 0, capsys.readouterr().out


def test_m6803_board_matches_mame(capsys) -> None:
    """esclwrld's on-chip timer, generating its own interrupts (scripts/m6803_board.py)."""
    trace = ROOT / "mame-work" / m6803_board.GAME / "error.log"
    if not trace.exists():
        pytest.skip(
            f"no MAME trace for {m6803_board.GAME} "
            f"(python scripts/replay_trace.py {m6803_board.GAME})"
        )
    assert m6803_board.replay(trace) == 0, capsys.readouterr().out


def test_williams_board_matches_mame(monkeypatch, capsys) -> None:
    capture = ROOT / "mame-work" / "williams" / "robotron.capture"
    if not capture.exists():
        pytest.skip("no Robotron capture (see scripts/williams_sound.py)")
    monkeypatch.setattr(sys, "argv", ["williams_sound.py", "--capture", str(capture)])
    with pytest.raises(SystemExit) as exited:
        williams_sound.main()
    out = capsys.readouterr().out
    assert exited.value.code == 0, out
    assert "every PIA write agrees" in out
