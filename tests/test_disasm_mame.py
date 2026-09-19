"""The disassembler against MAME 0.285's own, over every traced instruction.

Each game's ``mame-work/GAME/GAME.trace`` (written by scripts/mame_trace.sh) is
MAME's disassembly of every instruction the CPU executed.  For each distinct
ROM address in it, this decodes the same bytes -- from the game's zip, as
scripts/replay_trace.py loads them -- and compares mnemonic and operands.
MAME spells a few mnemonics its own way (``lda`` for LDAA, ``cmpx`` for CPX)
and prints ``illegal`` for opcodes it does not decode; those are mapped.
Skipped unless the traces exist locally; marked slow.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import replay_trace  # noqa: E402

from m6800_python import disassemble  # noqa: E402

pytestmark = pytest.mark.slow

MAME_NAMES = {
    "LDA": "LDAA",
    "LDB": "LDAB",
    "STA": "STAA",
    "STB": "STAB",
    "ORA": "ORAA",
    "ORB": "ORAB",
    "CMPX": "CPX",
    "ILLEGAL": "FCB",
}
LINE = re.compile(r"^([0-9A-F]{4}): (\S+)\s*(.*)$")


@pytest.mark.parametrize("game", sorted(replay_trace.MACHINES))
def test_disassembly_matches_mame(game: str) -> None:
    trace = ROOT / "mame-work" / game / f"{game}.trace"
    if not trace.exists():
        pytest.skip(f"no MAME trace for {game}")
    machine = replay_trace.MACHINES[game]
    rom = replay_trace.rom_image(machine, game)
    in_rom = replay_trace.ReplayBus(machine, rom).is_rom
    seen: dict[int, tuple[str, str]] = {}
    for text in trace.read_text(errors="replace").splitlines():
        match = LINE.match(text.strip())
        if match and in_rom[int(match.group(1), 16)]:
            seen[int(match.group(1), 16)] = (match.group(2).upper(), match.group(3).upper())
    assert seen, f"{trace}: no instruction lines in ROM"
    mismatches = []
    for address, (mnemonic, operands) in sorted(seen.items()):
        ours = disassemble(rom.__getitem__, address, part=machine.part, undocumented="mame")
        want_mnemonic = MAME_NAMES.get(mnemonic, mnemonic)
        same_operands = want_mnemonic == "FCB" or ",".join(ours.operands) == operands.replace(
            " ", ""
        )
        if ours.mnemonic != want_mnemonic or not same_operands:
            mismatches.append((f"{address:04X}", mnemonic, operands, ours.text))
    assert not mismatches, f"{len(mismatches)} of {len(seen)}: {mismatches[:10]}"
