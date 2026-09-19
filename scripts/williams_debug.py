"""Step through the Robotron sound board in the debugger, PIA and all.

    python scripts/williams_debug.py                  # with MAME's captured commands
    python scripts/williams_debug.py --no-capture     # silent board; send commands by hand
    python scripts/williams_debug.py -c "nextsound" -c "step 5" --batch

The board is scripts/williams_board.py's -- the one scripts/williams_sound.py
runs against MAME -- started from reset.  With a capture
(mame-work/williams/robotron.capture, recorded as williams_sound.py describes),
the 176 sound commands Robotron's main CPU sent during MAME's 30 seconds arrive
at the cycles they arrived there; without one, nothing arrives until you send
it with ``sound``.

Every ordinary debugger command works (``help``), on the real bus: watchpoints
see PIA traffic, and ``memory``/``disassemble`` peek the PIA without
acknowledging it.  The board adds:

    pia                   the PIA's registers and IRQ output
    sound VALUE           send a command now, as the main board does (port B, CB1)
    nextsound             run until the next scheduled command has arrived
    schedule [COUNT]      the commands still to come
    time                  the board clock, and commands delivered so far
    dac [COUNT]           the latest DAC bytes, with their cycles
    wav FILE [SECONDS]    write the DAC output so far (or its last SECONDS) as a WAV

A command is the byte the main board writes to port B: Robotron sends
``$C0 | sound`` and ``$FF`` (silence, CB1 low) between sounds.  ``sound``
drops CB1 first when it is already high, so every command makes an edge.
After reset the board waits at $F044 (``BRA *``), and after a sound at $FB83;
the IRQ handler is at $FB11, so ``break FB11``, ``continue`` stops as each
command is taken.
"""

from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

from williams_board import (
    CAPTURE,
    CLOCK,
    ROBOTRON_ZIP,
    SILENCE,
    WilliamsSoundBoard,
    load_capture,
    robotron_rom,
)

from m6800_python import CommandDebugger, CommandError, DebugSession, StopReason
from m6800_python.console import format_run, parse_number

WAV_RATE = 44_100


def _count(arguments: list[str], default: int) -> int:
    if not arguments:
        return default
    value = parse_number(arguments[0], "count", maximum=100_000, decimal=True)
    if value == 0:
        raise CommandError("count must be positive")
    return value


def _when(cycle: int) -> str:
    return f"cycle {cycle:,} ({cycle / CLOCK:.6f} s)"


def dac_samples(dac_bytes, start: int, end: int, rate: int = WAV_RATE) -> bytes:
    """Sample the DAC's output (it holds each byte until the next) at ``rate``
    from board cycle ``start`` to ``end``, as unsigned 8-bit PCM."""
    samples = bytearray()
    level = dac_bytes[0][1] if dac_bytes else 0x80
    index = 0
    count = int((end - start) / CLOCK * rate)
    for n in range(count):
        cycle = start + n * CLOCK / rate
        while index < len(dac_bytes) and dac_bytes[index][0] <= cycle:
            level = dac_bytes[index][1]
            index += 1
        samples.append(level)
    return bytes(samples)


class WilliamsCommands:
    """The board's debugger commands, for ``CommandDebugger(commands=...)``."""

    def __init__(self, board: WilliamsSoundBoard, session: DebugSession) -> None:
        self.board = board
        self.session = session

    def pia(self, arguments):
        _arity("pia", arguments, 0, 0)
        return self.board.pia.describe()

    def sound(self, arguments):
        _arity("sound", arguments, 1, 1)
        value = parse_number(arguments[0], "command", maximum=0xFF)
        board = self.board
        if value != SILENCE and board.pia.c1[1]:
            board.command(SILENCE)  # CB1 low first, so the command is an edge
        board.command(value)
        board.settle()
        return (f"command ${value:02X} at {_when(board.cycle)}; PIA IRQ={int(board.pia.irq())}",)

    def nextsound(self, arguments):
        _arity("nextsound", arguments, 0, 0)
        board = self.board
        if not board.schedule:
            raise CommandError("no scheduled commands left (use sound VALUE)")
        due, value = board.schedule[0]
        delivered = len(board.delivered)
        lines = []
        while len(board.delivered) == delivered:
            result = self.session.run(max_steps=10_000_000, max_cycles=max(1, due - board.cycle))
            if result.reason is not StopReason.CYCLE_LIMIT:
                return format_run(result)
        lines.append(f"command ${value:02X} arrived at {_when(board.cycle)}")
        lines.append(f"PIA IRQ={int(board.pia.irq())}; PC={board.cpu.PC:04X}")
        return tuple(lines)

    def schedule(self, arguments):
        _arity("schedule", arguments, 0, 1)
        upcoming = list(self.board.schedule)[: _count(arguments, 10)]
        if not upcoming:
            return ("no scheduled commands left",)
        return tuple(f"${value:02X} at {_when(cycle)}" for cycle, value in upcoming)

    def time(self, arguments):
        _arity("time", arguments, 0, 0)
        board = self.board
        lines = [
            f"board clock {_when(board.cycle)}",
            f"{len(board.delivered)} commands delivered, {len(board.schedule)} still scheduled",
        ]
        if board.delivered:
            cycle, value = board.delivered[-1]
            lines.append(f"last command ${value:02X} at {_when(cycle)}")
        lines.append(f"{len(board.dac_bytes):,} DAC bytes, {len(board.pia_writes):,} PIA writes")
        if board.unmapped:
            lines.append(f"{len(board.unmapped)} unmapped accesses, first {board.unmapped[0]}")
        return tuple(lines)

    def dac(self, arguments):
        _arity("dac", arguments, 0, 1)
        recent = self.board.dac_bytes[-_count(arguments, 16) :]
        return tuple(f"${value:02X} at {_when(cycle)}" for cycle, value in recent) or (
            "no DAC bytes yet",
        )

    def wav(self, arguments):
        _arity("wav", arguments, 1, 2)
        board = self.board
        start = 0
        if len(arguments) == 2:
            try:
                seconds = float(arguments[1])
            except ValueError as exc:
                raise CommandError(f"seconds must be a number, not {arguments[1]!r}") from exc
            start = max(0, board.cycle - round(seconds * CLOCK))
        samples = dac_samples(board.dac_bytes, start, board.cycle)
        with wave.open(arguments[0], "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(1)
            out.setframerate(WAV_RATE)
            out.writeframes(samples)
        return (f"wrote {len(samples) / WAV_RATE:.2f} s to {arguments[0]}",)

    def table(self):
        return {
            "pia": (self.pia, "pia                           The PIA's registers and IRQ output"),
            "sound": (self.sound, "sound VALUE                   Send a command now (port B, CB1)"),
            "nextsound": (
                self.nextsound,
                "nextsound                     Run until the next scheduled command arrives",
            ),
            "schedule": (
                self.schedule,
                "schedule [COUNT]              The commands still to come",
            ),
            "time": (self.time, "time                          The board clock, commands so far"),
            "dac": (self.dac, "dac [COUNT]                   The latest DAC bytes"),
            "wav": (
                self.wav,
                "wav FILE [SECONDS]            Write the DAC output (or its last SECONDS) as WAV",
            ),
        }


def _arity(name: str, arguments: list[str], minimum: int, maximum: int) -> None:
    if not minimum <= len(arguments) <= maximum:
        expected = str(minimum) if minimum == maximum else f"{minimum}..{maximum}"
        raise CommandError(f"{name} takes {expected} argument(s)")


def make_debugger(rom: bytes, schedule=()) -> tuple[WilliamsSoundBoard, CommandDebugger]:
    board = WilliamsSoundBoard(rom, schedule)
    session = DebugSession(board, peek_byte=board.peek, track_accesses=True)
    debugger = CommandDebugger(session, commands=WilliamsCommands(board, session).table())
    return board, debugger


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--capture", type=Path, default=CAPTURE)
    parser.add_argument("--no-capture", action="store_true", help="schedule no commands")
    parser.add_argument("--rom", type=Path, default=ROBOTRON_ZIP, help="robotron.zip")
    parser.add_argument("-c", "--command", action="append", default=[], metavar="COMMAND")
    parser.add_argument("--batch", action="store_true", help="run the -c commands and exit")
    args = parser.parse_args(argv)
    schedule = []
    if not args.no_capture:
        if not args.capture.exists():
            sys.exit(f"{args.capture} missing (see scripts/williams_sound.py), or --no-capture")
        schedule, _, _ = load_capture(args.capture)
    _, debugger = make_debugger(robotron_rom(args.rom), schedule)
    print(f"Williams sound board, Robotron ROM; {len(schedule)} commands scheduled")
    for command in ("registers", "disassemble", *args.command):
        print(f"williams> {command}")
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
        debugger.interact(sys.stdin, sys.stdout, prompt="williams> ")


if __name__ == "__main__":
    main()
