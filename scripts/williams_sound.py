"""Milestone 4: a Williams sound board built on the core, against MAME 0.285.

    python scripts/williams_sound.py [--capture mame-work/williams/robotron.capture]

The first host for the core that is a real board rather than a test bus: the
sound board of Defender, Stargate, Robotron, Joust and their relatives
(midway/williams.cpp, ``williams_state::sound_map``), an MC6808 at 3.579545 MHz
/ 4 = 894,886.25 Hz with

    $0000-$00FF  RAM (the 6808's 128 bytes plus an MC6810)
    $0400-$0403  an MC6821 PIA, also at $8400 -- port A drives the DAC, port B
                 and CB1 receive the command from the main board, and the
                 PIA's two IRQ outputs are wired together onto the CPU's IRQ
    $B000-$FFFF  ROM (Robotron's 4K at $F000)

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

**Tier: emulator-derived.**  The PIA model here is this script's own, written
from the MC6821's behaviour as MAME implements it (6821pia.cpp); only the parts
this board uses are modelled.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from m6800_python import M6808  # noqa: E402

ROMPATH = Path("/data/emu/source/myrient.erista.me/files/MAME/ROMs (non-merged)")
CLOCK = 3_579_545 / 4  # the 6808 divides its crystal by four
IDLE_LOOP = 0xFB83  # Robotron: "FB83: beq $FB83", waiting for a command
IRQ_HANDLER = 0xFB11


class PIA6821:
    """The parts of an MC6821 this board uses.

    Register select: offset 0/2 is port A/B's data register when bit 2 of its
    control register is set and its data-direction register when it is clear;
    offset 1/3 is the control register.  A transition on CA1/CB1 in the
    direction bit 1 selects sets bit 7 of the control register; the port's
    IRQ output is bit 7 AND the enable, bit 0; reading the data register
    clears bits 7 and 6.
    """

    def __init__(self, dac) -> None:
        self.dac = dac
        self.cr = [0, 0]
        self.ddr = [0, 0]
        self.out = [0, 0]
        self.inputs = [0xFF, 0xFF]  # undriven inputs read high
        self.c1 = [0, 0]

    def irq(self) -> bool:
        return any(cr & 0x80 and cr & 0x01 for cr in self.cr)

    def read(self, offset: int) -> int:
        port = offset >> 1
        if offset & 1:
            return self.cr[port]
        if not self.cr[port] & 0x04:
            return self.ddr[port]
        self.cr[port] &= 0x3F  # reading the data register acknowledges the interrupt
        return (self.out[port] & self.ddr[port]) | (self.inputs[port] & ~self.ddr[port] & 0xFF)

    def write(self, offset: int, value: int) -> None:
        port = offset >> 1
        if offset & 1:
            self.cr[port] = (self.cr[port] & 0xC0) | (value & 0x3F)
            return
        if self.cr[port] & 0x04:
            self.out[port] = value
        else:
            self.ddr[port] = value
        if port == 0:
            # Port A drives the DAC; bits set as inputs float high.
            self.dac((self.out[0] & self.ddr[0]) | (~self.ddr[0] & 0xFF))

    def set_c1(self, port: int, level: int) -> None:
        if level == self.c1[port]:
            return
        rising = level > self.c1[port]
        self.c1[port] = level
        if rising == bool(self.cr[port] & 0x02):
            self.cr[port] |= 0x80


class WilliamsSoundBoard:
    def __init__(self, rom: bytes) -> None:
        self.ram = bytearray(0x100)
        self.rom = bytearray(0x10000)
        self.rom[0x10000 - len(rom) :] = rom
        self.cycle = 0
        self.pia_writes: list[tuple[int, int, int]] = []
        self.dac_bytes: list[tuple[int, int]] = []
        self.unmapped: list[tuple[str, int]] = []
        self.pia = PIA6821(lambda value: self.dac_bytes.append((self.cycle, value)))
        self.cpu = M6808(self.read, self.write)

    def read(self, address: int) -> int:
        if address < 0x0100:
            return self.ram[address]
        if address & 0x7FFC == 0x0400:
            return self.pia.read(address & 3)
        if address >= 0xB000:
            return self.rom[address]
        self.unmapped.append(("r", address))
        return 0

    def write(self, address: int, value: int) -> None:
        if address < 0x0100:
            self.ram[address] = value
        elif address & 0x7FFC == 0x0400:
            self.pia_writes.append((self.cycle, address & 3, value))
            self.pia.write(address & 3, value)
        else:
            self.unmapped.append(("w", address))

    def command(self, value: int) -> None:
        """What williams_m.cpp's deferred_snd_cmd_w does: port B, then CB1."""
        self.pia.inputs[1] = value
        self.pia.set_c1(1, 0 if value == 0xFF else 1)


def load_capture(path: Path):
    commands, writes, end = [], [], None
    for line in path.read_text().splitlines():
        fields = line.split()
        if fields[0] == "C":
            commands.append((round(float(fields[1]) * CLOCK), int(fields[2])))
        elif fields[0] == "W":
            writes.append((round(float(fields[1]) * CLOCK), int(fields[2]), int(fields[3])))
        elif fields[0] == "E":
            end = round(float(fields[1]) * CLOCK)
    if end is None:
        sys.exit(f"{path}: no end-of-run line; re-record with the current williams_capture.lua")
    return commands, writes, end


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
    parser.add_argument(
        "--capture", type=Path, default=ROOT / "mame-work" / "williams" / "robotron.capture"
    )
    args = parser.parse_args()
    if not args.capture.exists():
        sys.exit(f"{args.capture} missing; see this script's docstring for the MAME command")
    commands, mame_writes, end = load_capture(args.capture)
    with zipfile.ZipFile(ROMPATH / "robotron.zip") as archive:
        rom = archive.read("video_sound_rom_3_std_767.ic12")
    board = WilliamsSoundBoard(rom)
    cpu = board.cpu
    cpu.reset()
    pending = list(commands)
    left_idle_loop = handler_runs = 0
    was_idle = False
    while board.cycle < end:
        while pending and pending[0][0] <= board.cycle:
            board.command(pending.pop(0)[1])
        cpu.irq = board.pia.irq()
        pc_before = cpu.PC
        board.cycle += cpu.step()
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
