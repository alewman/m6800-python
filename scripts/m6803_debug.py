"""Step through esclwrld's MC6803 in the debugger, its on-chip timer and all.

    python scripts/m6803_debug.py
    python scripts/m6803_debug.py -c "break C412" -c "continue" -c "timer" --batch

The board is scripts/m6803_board.py's ``EsclwrldBoard`` -- the one
scripts/m6803_board.py runs against MAME -- started from Escape from the Lost
World's reset vector. Every ordinary debugger command works (``help``); the
timer registers ($08-$0C) are the board's own, computed as the CPU reads and
writes them, not played back from a trace. ($0D/$0E, input capture, and the
external IRQ1/NMI lines are not modelled here; see scripts/m6803_board.py's
module docstring for why.)

The board adds:

    timer                 TCSR decoded, the counter, OC, and what irq2 is armed to
    irq2 VECTOR | off      Assert the on-chip request directly (for testing), or drop it

After reset the game's boot code runs for a while before the timer is ever
touched; ``break 08`` -- no address does that; use ``watch`` on $08 instead,
or run with ``-c "run 400000"`` to land past the first output-compare
interrupt (see scripts/m6803_board.py's module docstring for the counts).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from m6803_board import (  # noqa: E402
    TCSR_EICI,
    TCSR_EOCI,
    TCSR_ETOI,
    TCSR_ICF,
    TCSR_IEDG,
    TCSR_OCF,
    TCSR_OLVL,
    TCSR_TOF,
    EsclwrldBoard,
)
from replay_trace import MACHINES, ROMPATH, rom_image  # noqa: E402

from m6800_python import CommandDebugger, CommandError, DebugSession  # noqa: E402
from m6800_python.console import parse_number  # noqa: E402

GAME = "esclwrld"
MACHINE = MACHINES[GAME]


def _flags(timer) -> str:
    bits = (
        (TCSR_ICF, "ICF"),
        (TCSR_OCF, "OCF"),
        (TCSR_TOF, "TOF"),
        (TCSR_EICI, "EICI"),
        (TCSR_EOCI, "EOCI"),
        (TCSR_ETOI, "ETOI"),
        (TCSR_IEDG, "IEDG"),
        (TCSR_OLVL, "OLVL"),
    )
    return " ".join(name for mask, name in bits if timer.tcsr & mask) or "none"


class M6803BoardCommands:
    """``timer`` and ``irq2``, for ``CommandDebugger(commands=...)``."""

    def __init__(self, board: EsclwrldBoard) -> None:
        self.board = board

    def timer(self, arguments):
        _arity("timer", arguments, 0, 0)
        timer = self.board.timer
        vector = self.board.cpu.irq2
        armed = "none" if vector is None else f"${vector:04X}"
        return (
            f"TCSR={timer.tcsr:02X}  flags set: {_flags(timer)}",
            f"counter=${timer.counter:04X}  OC=${timer.oc:04X}",
            f"irq2 armed: {armed}",
        )

    def irq2(self, arguments):
        _arity("irq2", arguments, 1, 1)
        cpu = self.board.cpu
        if arguments[0].lower() == "off":
            cpu.irq2 = None
            return ("irq2 withdrawn",)
        vector = parse_number(arguments[0], "vector", maximum=0xFFFF)
        cpu.irq2 = vector
        return (f"irq2 asserted: ${vector:04X}",)

    def table(self):
        return {
            "timer": (self.timer, "timer                         TCSR, the counter, OC, irq2"),
            "irq2": (self.irq2, "irq2 VECTOR | off             Assert or withdraw irq2 directly"),
        }


def _arity(name: str, arguments: list[str], minimum: int, maximum: int) -> None:
    if not minimum <= len(arguments) <= maximum:
        expected = str(minimum) if minimum == maximum else f"{minimum}..{maximum}"
        raise CommandError(f"{name} takes {expected} argument(s)")


def make_debugger(rom: bytearray) -> tuple[EsclwrldBoard, CommandDebugger]:
    board = EsclwrldBoard(rom)
    session = DebugSession(board, peek_byte=lambda a: board.rom[a] if board.is_rom[a] else 0)
    debugger = CommandDebugger(session, commands=M6803BoardCommands(board).table())
    return board, debugger


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--rompath", type=Path, default=ROMPATH)
    parser.add_argument("-c", "--command", action="append", default=[], metavar="COMMAND")
    parser.add_argument("--batch", action="store_true", help="run the -c commands and exit")
    args = parser.parse_args(argv)
    try:
        rom = rom_image(MACHINE, GAME)
    except FileNotFoundError:
        sys.exit(f"{args.rompath / (GAME + '.zip')} missing; see scripts/replay_trace.py --help")
    board, debugger = make_debugger(rom)
    board.cpu.PC = (board.rom[0xFFFE] << 8) | board.rom[0xFFFF]
    print(f"esclwrld's MC6803, from reset ($FFFE -> ${board.cpu.PC:04X})")
    for command in ("registers", "disassemble", *args.command):
        print(f"m6803> {command}")
        try:
            result = debugger.execute(command)
        except (CommandError, ValueError) as exc:
            print(f"error: {exc}")
            continue
        for line in result.lines:
            print(line)
        if result.quit:
            return
    if not args.batch:
        debugger.interact(sys.stdin, sys.stdout, prompt="m6803> ")


if __name__ == "__main__":
    main()
