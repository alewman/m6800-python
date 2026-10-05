"""The Williams sound board as a host for the core: CPU, RAM, ROM and PIA.

The sound board of Defender, Stargate, Robotron, Joust and their relatives
(midway/williams.cpp, ``williams_state::sound_map``), an MC6808 at 3.579545 MHz
/ 4 = 894,886.25 Hz with

    $0000-$00FF  RAM (the 6808's 128 bytes plus an MC6810)
    $0400-$0403  an MC6821 PIA, also at $8400 -- port A drives the DAC, port B
                 and CB1 receive the command from the main board, and the
                 PIA's two IRQ outputs are wired together onto the CPU's IRQ
    $B000-$FFFF  ROM (Robotron's 4K at $F000)

``WilliamsSoundBoard.step()`` is the whole machine's step: one CPU boundary,
then the sound commands that have fallen due and the IRQ line brought up to
date.  scripts/williams_sound.py runs it against MAME; scripts/williams_debug.py
steps through it in the debugger.

**Tier: emulator-derived.**  The PIA model here is written from the MC6821's
behaviour as MAME implements it (6821pia.cpp); only the parts this board uses
are modelled.
"""

from __future__ import annotations

import os
import sys
import zipfile
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from m6800_python import M6808  # noqa: E402

# MAME's ROM directory: $ROMPATH (or $MAME_ROMPATH), else the working directory.
# Sets are read in place and never copied into this repository.
ROMPATH = Path(os.environ.get("ROMPATH") or os.environ.get("MAME_ROMPATH") or ".")
ROBOTRON_ZIP = ROMPATH / "robotron.zip"
ROBOTRON_SOUND_ROM = "video_sound_rom_3_std_767.ic12"
CAPTURE = ROOT / "mame-work" / "williams" / "robotron.capture"
CLOCK = 3_579_545 / 4  # the 6808 divides its crystal by four
IDLE_LOOP = 0xFB83  # Robotron: "FB83: beq $FB83", waiting for a command
IRQ_HANDLER = 0xFB11
SILENCE = 0xFF  # the command the main board sends between sounds; CB1 goes low


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

    def peek(self, offset: int) -> int:
        """What ``read`` would return, without acknowledging anything."""
        port = offset >> 1
        if offset & 1:
            return self.cr[port]
        if not self.cr[port] & 0x04:
            return self.ddr[port]
        return (self.out[port] & self.ddr[port]) | (self.inputs[port] & ~self.ddr[port] & 0xFF)

    def read(self, offset: int) -> int:
        value = self.peek(offset)
        if not offset & 1 and self.cr[offset >> 1] & 0x04:
            self.cr[offset >> 1] &= 0x3F  # reading the data register acknowledges the interrupt
        return value

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

    def describe(self) -> tuple[str, ...]:
        """The registers, one line per port, for a debugger."""
        lines = []
        for port, name in enumerate("AB"):
            cr = self.cr[port]
            lines.append(
                f"port {name}: CR={cr:02X} DDR={self.ddr[port]:02X} OUT={self.out[port]:02X} "
                f"IN={self.inputs[port]:02X} C1={self.c1[port]}  "
                f"flag={cr >> 7} enable={cr & 1} edge={'rise' if cr & 2 else 'fall'} "
                f"select={'data' if cr & 4 else 'ddr'}"
            )
        lines.append(f"IRQ output: {int(self.irq())}")
        return tuple(lines)


class WilliamsSoundBoard:
    """The board.  ``schedule`` holds ``(cycle, value)`` sound commands to
    deliver as the board's clock reaches them (from a MAME capture, say)."""

    def __init__(self, rom: bytes, schedule=()) -> None:
        self.ram = bytearray(0x100)
        self.rom = bytearray(0x10000)
        self.rom[0x10000 - len(rom) :] = rom
        self.cycle = 0
        self.schedule = deque(sorted(schedule))
        self.delivered: list[tuple[int, int]] = []  # (cycle, value)
        self.pia_writes: list[tuple[int, int, int]] = []
        self.dac_bytes: list[tuple[int, int]] = []
        self.unmapped: list[tuple[str, int]] = []
        self.pia = PIA6821(lambda value: self.dac_bytes.append((self.cycle, value)))
        self.cpu = M6808(self.read, self.write)
        self.cpu.reset()
        self.settle()

    # -- the bus -------------------------------------------------------------

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

    def peek(self, address: int) -> int:
        """A side-effect-free read, for disassembly and memory dumps."""
        if address < 0x0100:
            return self.ram[address]
        if address & 0x7FFC == 0x0400:
            return self.pia.peek(address & 3)
        if address >= 0xB000:
            return self.rom[address]
        return 0

    # -- running -------------------------------------------------------------

    def command(self, value: int) -> None:
        """What williams_m.cpp's deferred_snd_cmd_w does: port B, then CB1."""
        self.pia.inputs[1] = value
        self.pia.set_c1(1, 0 if value == SILENCE else 1)
        self.delivered.append((self.cycle, value))

    def settle(self) -> None:
        """Deliver the commands due by now and drive the CPU's IRQ from the PIA."""
        while self.schedule and self.schedule[0][0] <= self.cycle:
            self.command(self.schedule.popleft()[1])
        self.cpu.irq = self.pia.irq()

    def step(self) -> int:
        """One CPU boundary, then the devices; returns its cycles."""
        cycles = self.cpu.step()
        self.cycle += cycles
        self.settle()
        return cycles

    def capture_state(self):
        return self.cpu.capture_state()


def robotron_rom(zip_path: Path = ROBOTRON_ZIP) -> bytes:
    with zipfile.ZipFile(zip_path) as archive:
        return archive.read(ROBOTRON_SOUND_ROM)


def load_capture(path: Path):
    """``(commands [(cycle, value)], PIA writes [(cycle, offset, value)], end cycle)``."""
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
