"""Milestone 4: a Williams sound board built on the core, against MAME 0.285.

    python scripts/williams_sound.py [--capture mame-work/williams/robotron.capture]

The first host for the core that is a real board rather than a test bus: the
Williams sound board (scripts/williams_board.py has the memory map and PIA).

The inputs come from MAME: scripts/williams_capture.lua records each sound
command the main 6809 sends, with its machine time, and every write the sound
CPU makes to its PIA.  This script runs the board from reset, applies each
command at the same time, converted to CPU cycles, and compares the core's PIA
writes -- and the DAC bytes they produce -- with MAME's.

    cd mame-work/williams && rm -rf nvram && WILLIAMS_CAPTURE_FILE=robotron.capture \\
      M6800_PRESS="IN2:Advance:680:20;IN2:Coin 1:800:5;IN0:1 Player Start:860:5;\\
    IN0:Move Left:900:120;IN1:Fire Right:950:400;IN0:Move Up:1100:100;IN0:Fire Down:1200:300" \\
      /usr/games/mame robotron -rompath ROMPATH -video none -sound none -nothrottle \\
      -noreadconfig -skip_gameinfo -seconds_to_run 30 \\
      -autoboot_script ../../scripts/williams_capture.lua

Clear ``nvram/`` first: with Robotron's CMOS saved from an earlier run the game
boots past its "press Advance" wait and the input schedule no longer lines up.

**Tier: emulator-derived.**  The PIA model is williams_board.py's own, written
from MAME's 6821pia.cpp.  The board's ``step()`` is the one the debugger drives
(scripts/williams_debug.py), so this comparison vouches for that too.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from williams_board import (
    CAPTURE,
    CLOCK,
    IDLE_LOOP,
    IRQ_HANDLER,
    PIA6821,
    WilliamsSoundBoard,
    load_capture,
    robotron_rom,
)


def dac_stream(writes):
    """The DAC bytes a sequence of PIA writes produces (port A outputs)."""
    board = PIA6821(lambda value: stream.append(value))
    stream: list[int] = []
    for _, offset, value in writes:
        board.write(offset, value)
    return stream


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--capture", type=Path, default=CAPTURE)
    args = parser.parse_args()
    if not args.capture.exists():
        sys.exit(f"{args.capture} missing; see this script's docstring for the MAME command")
    commands, mame_writes, end = load_capture(args.capture)
    board = WilliamsSoundBoard(robotron_rom(), commands)
    cpu = board.cpu
    left_idle_loop = handler_runs = 0
    was_idle = False
    while board.cycle < end:
        pc_before = cpu.PC
        board.step()
        if cpu.PC == IRQ_HANDLER and pc_before != IRQ_HANDLER:
            handler_runs += 1
            if was_idle:
                left_idle_loop += 1
        was_idle = pc_before == IDLE_LOOP

    ours = [(offset, value) for _, offset, value in board.pia_writes]
    theirs = [(offset, value) for _, offset, value in mame_writes]
    print(
        f"Williams sound board (Robotron ROM), {board.cycle:,} cycles = "
        f"{board.cycle / CLOCK:.2f} s, {len(commands)} commands from MAME"
    )
    print(
        f"  IRQ handler ${IRQ_HANDLER:04X} entered {handler_runs} times, "
        f"{left_idle_loop} of them from the ${IDLE_LOOP:04X} idle loop"
    )
    print(f"  PIA writes: core {len(ours):,}, MAME {len(theirs):,}")
    first = next((i for i, (a, b) in enumerate(zip(ours, theirs, strict=False)) if a != b), None)
    if first is None and len(ours) == len(theirs):
        print("  every PIA write agrees, in order and value")
    else:
        index = first if first is not None else min(len(ours), len(theirs))
        print(
            f"  first difference at PIA write {index}: core {ours[index : index + 3]} "
            f"MAME {theirs[index : index + 3]}"
        )
        if index < len(board.pia_writes) and index < len(mame_writes):
            print(
                f"    at core cycle {board.pia_writes[index][0]:,}, "
                f"MAME cycle {mame_writes[index][0]:,}"
            )
    ours_dac = [value for _, value in board.dac_bytes]
    theirs_dac = dac_stream(mame_writes)
    same = ours_dac == theirs_dac
    print(
        f"  DAC bytes: core {len(ours_dac):,}, MAME {len(theirs_dac):,}: "
        f"{'identical sequences' if same else 'sequences differ'}"
    )
    timing = [abs(a[0] - b[0]) for a, b in zip(board.pia_writes, mame_writes, strict=False)]
    if timing:
        print(
            f"  |core cycle - MAME cycle| over matched writes: max {max(timing)}, "
            f"mean {sum(timing) / len(timing):.1f}"
        )
    if board.unmapped:
        print(f"  unmapped accesses: {board.unmapped[:5]} ({len(board.unmapped)} in all)")
    sys.exit(0 if same and first is None else 1)


if __name__ == "__main__":
    main()
