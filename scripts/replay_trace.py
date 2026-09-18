"""Replay a MAME 0.285 boot trace of real arcade code through the core.

    python scripts/replay_trace.py dragrace [--trace mame-work/dragrace/error.log]
    python scripts/replay_trace.py kncljoe

Milestone 3 (docs/validation.md).  The trace comes from scripts/mame_trace.sh
with watchpoints on (see ``MACHINES`` for the exact command per game): one line
per instruction, ``pc a b x s cc wai totalcycles`` *before* it executes,
followed by ``R addr value`` / ``W addr value`` for every non-ROM read and
every write it made.

The core runs the same program from the same state:

* ROM comes from the game's zip, read in place, at the addresses the MAME
  driver maps; every other read is served the value MAME logged for it, and
  must be the same address in the same order;
* every write must match MAME's, address, value and order;
* registers are compared before every instruction;
* where MAME took an interrupt -- the next line is at a vector's target and
  the core's PC is not -- the same interrupt is raised on the core for one
  step, so the entry itself (frame, I bit, vector, cost) is compared too;
* ``totalcycles`` is compared as a running total, allowing for MAME's
  CLI/TAP artefact: those handlers run the next instruction inline and charge
  their own cycles only afterwards (docs/mame-oracle.md).

The replay stops at the first difference and says what it was.  **Tier:
emulator-derived** -- agreement here is agreement with MAME on real code.
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from collections import Counter, deque
from collections.abc import Iterator
from dataclasses import dataclass, field
from itertools import islice
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from m6800_python import M6800, M6803  # noqa: E402

ROMPATH = Path("/data/emu/source/myrient.erista.me/files/MAME/ROMs (non-merged)")


@dataclass
class Machine:
    part: str
    tag: str
    # (file in the zip, CPU address): read in place at the address MAME maps.
    roms: list[tuple[str, int]]
    # Address ranges served from the ROM image rather than from MAME's log.
    rom_ranges: list[tuple[int, int]]
    # (source, destination, length): mirrors of ROM the driver maps.
    mirrors: list[tuple[int, int, int]] = field(default_factory=list)
    address_mask: int = 0xFFFF
    watch_reads: str = ""
    seconds: int = 2
    press: str = ""  # M6800_PRESS for scripts/mame_trace.sh


MACHINES = {
    # atari/dragrace.cpp: RAM $0080-$00FF, I/O $0800-$0EFF, program ROM
    # $1000-$1FFF, and $F800-$FFFF mapping the upper 2K again (the vectors).
    "dragrace": Machine(
        part="6800",
        tag=":maincpu",
        roms=[("8513.c1", 0x1000), ("8514.a1", 0x1800)],
        rom_ranges=[(0x1000, 0x1FFF), (0xF800, 0xFFFF)],
        mirrors=[(0x1800, 0xF800, 0x800)],
        watch_reads="0000-0FFF,2000-F7FF",
    ),
    # seibu/kncljoe.cpp: MC6803 sound CPU, address bus masked to 15 bits,
    # kj-13 at $6000-$7FFF (so $E000-$FFFF too); on-chip registers and RAM
    # below $0100 are the CPU's own and are logged like any other I/O.
    "kncljoe": Machine(
        part="6803",
        tag=":soundcpu",
        roms=[("kj-13.bin", 0x6000)],
        rom_ranges=[(0x6000, 0x7FFF), (0xE000, 0xFFFF)],
        mirrors=[(0x6000, 0xE000, 0x2000)],
        address_mask=0x7FFF,
        # Only the low half: with the bus masked to 15 bits a watchpoint on
        # $8000-$DFFF covers the same cells, and every read is logged twice.
        watch_reads="0000-5FFF",
        seconds=10,
    ),
    # pinball/by6803.cpp: Bally's 6803 pinball MPU running Escape from the Lost
    # World (1988): PIAs at $0020 and $0040, battery RAM at $1000-$17FF, ROM
    # u2/u3 at $8000-$FFFF.  The only trace here that executes MUL.  It powers
    # up with its NVRAM empty, so clear mame-work/esclwrld/nvram before recording.
    "esclwrld": Machine(
        part="6803",
        tag=":maincpu",
        roms=[("u2.128", 0x8000), ("u3.128", 0xC000)],
        rom_ranges=[(0x8000, 0xFFFF)],
        watch_reads="0000-7FFF",
        seconds=8,
    ),
    # taito/bublbobl.cpp: Bubble Bobble's protection MCU, an MC6801U4 running its
    # 4K internal ROM a78-01.17 at $F000; everything below is on-chip registers,
    # RAM or the external bus, all logged.  It is the only trace here that runs
    # SUBD in real code, over a hundred thousand times.
    "bublbobl": Machine(
        part="6803",
        tag=":mcu",
        roms=[("a78-01.17", 0xF000)],
        rom_ranges=[(0xF000, 0xFFFF)],
        watch_reads="0000-EFFF",
        seconds=6,
    ),
    # irem/m62.cpp (irem_audio, m62_sound_map): the Irem M62 sound board's
    # MC6803, ROM $4000-$FFFF; below that the on-chip registers and RAM, the
    # IRQ acknowledge at $0800 and the ADPCM latches at $0801-$0802.  Driven
    # with a coin, a start and some play so that the sound engine has work.
    "kidniki": Machine(
        part="6803",
        tag=":irem_audio:iremsound",
        roms=[("dr00.3a", 0x4000), ("dr01.3cd", 0x8000), ("dr02.3f", 0xC000)],
        rom_ranges=[(0x4000, 0xFFFF)],
        watch_reads="0000-3FFF",
        seconds=40,
        press=(
            "SYSTEM:Coin 1:600:5;SYSTEM:1 Player Start:720:5;P1:P1 Right:900:1200;"
            "P1:P1 Button 1:1000:10;P1:P1 Button 2:1300:10;P1:P1 Button 1:1600:10;"
            "P1:P1 Button 2:1900:10"
        ),
    ),
}

INSTRUCTION = re.compile(
    r"^([0-9A-F]+) ([0-9A-F]+) ([0-9A-F]+) ([0-9A-F]+) ([0-9A-F]+) "
    r"([0-9A-F]+) ([0-9A-F]+) (\d+)$"
)
ACCESS = re.compile(r"^([RW]) ([0-9A-F]+) ([0-9A-F]+)$")
VECTORS = {"IRQ": 0xFFF8, "NMI": 0xFFFC, "ICF": 0xFFF6, "OCF": 0xFFF4, "TOF": 0xFFF2, "SCI": 0xFFF0}


class Divergence(Exception):
    pass


@dataclass
class Line:
    number: int
    pc: int
    a: int
    b: int
    x: int
    s: int
    cc: int
    wai: int
    cycles: int
    accesses: list[tuple[str, int, int]]


def parse(path: Path) -> Iterator[Line]:
    """Yield the trace's instruction lines, each with the accesses logged after it."""
    line: Line | None = None
    with path.open(errors="replace") as log:
        for number, text in enumerate(log, 1):
            text = text.strip().lstrip("\ufeff")
            m = INSTRUCTION.match(text)
            if m:
                if line is not None:
                    yield line
                pc, a, b, x, s, cc, wai = (int(v, 16) for v in m.groups()[:7])
                line = Line(number, pc, a, b, x, s, cc, wai, int(m.group(8)), [])
                continue
            m = ACCESS.match(text)
            if m and line is not None:
                line.accesses.append((m.group(1), int(m.group(2), 16), int(m.group(3), 16)))
    if line is not None:
        yield line


def rom_image(machine: Machine, game: str) -> bytearray:
    image = bytearray(0x10000)
    with zipfile.ZipFile(ROMPATH / f"{game}.zip") as archive:
        for name, address in machine.roms:
            data = archive.read(name)
            image[address : address + len(data)] = data
    for source, destination, length in machine.mirrors:
        image[destination : destination + length] = image[source : source + length]
    return image


class ReplayBus:
    """ROM from the zip; every other access checked against MAME's log."""

    def __init__(self, machine: Machine, rom: bytearray) -> None:
        self.rom = rom
        self.mask = machine.address_mask
        self.is_rom = bytearray(0x10000)
        for first, last in machine.rom_ranges:
            self.is_rom[first : last + 1] = b"\x01" * (last - first + 1)
        self.queue: deque = deque()

    def read(self, address: int) -> int:
        if self.is_rom[address]:
            return self.rom[address]
        if not self.queue:
            raise Divergence(f"core read ${address:04X}; MAME logged no further access")
        kind, logged, value = self.queue.popleft()
        if kind != "R" or logged & self.mask != address & self.mask:
            raise Divergence(
                f"core read ${address:04X}; MAME's next access was {kind} ${logged:04X}"
            )
        return value

    def write(self, address: int, value: int) -> None:
        if not self.queue:
            raise Divergence(f"core wrote ${value:02X} to ${address:04X}; MAME logged nothing")
        kind, logged, logged_value = self.queue.popleft()
        if kind != "W" or logged & self.mask != address & self.mask or logged_value != value:
            raise Divergence(
                f"core wrote ${value:02X} to ${address:04X}; MAME's next access was "
                f"{kind} ${logged:04X} ${logged_value:02X}"
            )


def replay(game: str, trace: Path, limit: int | None = None) -> int:
    machine = MACHINES[game]
    lines = parse(trace)
    if limit:
        lines = islice(lines, limit)
    line, nxt = next(lines, None), next(lines, None)
    if line is None or nxt is None:
        sys.exit(f"{trace}: no instruction lines")
    rom = rom_image(machine, game)
    bus = ReplayBus(machine, rom)
    cls = M6800 if machine.part == "6800" else M6803
    cpu = cls(bus.read, bus.write, undocumented="mame")
    targets = {name: (rom[v] << 8) | rom[v + 1] for name, v in VECTORS.items()}
    first = line
    cpu.PC, cpu.A, cpu.B, cpu.X, cpu.SP, cpu.CC = (
        first.pc,
        first.a,
        first.b,
        first.x,
        first.s,
        first.cc,
    )
    total = first.cycles
    open_inlines: list[int] = []  # cycles MAME has not yet charged for CLI/TAP
    opcodes: Counter = Counter()
    interrupts: Counter = Counter()
    resyncs = 0
    history: deque = deque(maxlen=3)
    i = 0

    while nxt is not None:
        got = (cpu.PC, cpu.A, cpu.B, cpu.X, cpu.SP, cpu.CC)
        want = (line.pc, line.a, line.b, line.x, line.s, line.cc)
        if got[:5] != want[:5] or (got[5] & 0x3F) != (want[5] & 0x3F):
            report(
                game,
                i,
                [*history, line, nxt],
                f"registers differ: core {fmt(got)} MAME {fmt(want)}",
            )
            return 1
        if total - sum(open_inlines) != line.cycles:
            report(
                game,
                i,
                [*history, line, nxt],
                f"totalcycles: core {total - sum(open_inlines)} MAME {line.cycles}",
            )
            return 1

        opcode = rom[cpu.PC] if bus.is_rom[cpu.PC] else None
        inlines = opcode == 0x06 or (opcode == 0x0E and cpu.CC & 0x10)
        bus.queue = deque(line.accesses)
        try:
            cycles = cpu.step()
            opcodes[opcode] += 1
            if inlines:
                open_inlines.append(cycles)
            else:
                open_inlines.clear()
            total += cycles
            # Interrupt entries MAME made before the next traced instruction.
            # Each stacked frame is seven writes, PCL first; an entry out of
            # WAI stacks nothing.  Entry k's target is the PC the next frame
            # pushes, or the next line's PC for the last entry.
            frames = pushed_frames(bus.queue)
            chain = [*frames, nxt.pc]
            entries = len(frames) + (1 if cpu.waiting else 0)
            if not entries and cpu.PC != nxt.pc:
                raise Divergence(f"core went to ${cpu.PC:04X}, MAME to ${nxt.pc:04X}")
            for k in range(entries):
                target = chain[k] if cpu.waiting else chain[k + 1]
                taken = [name for name, vector_target in targets.items() if vector_target == target]
                if not taken:
                    raise Divergence(f"MAME entered ${target:04X}, which no vector points at")
                was_waiting = cpu.waiting
                if "NMI" in taken:
                    cpu.pulse_nmi()
                    kind = "NMI"
                elif "IRQ" in taken:
                    cpu.irq = True
                    kind = "IRQ"
                else:
                    cpu.irq2 = VECTORS[taken[0]]
                    kind = taken[0]
                total += cpu.step()
                cpu.irq = False
                if machine.part == "6803":
                    cpu.irq2 = None
                interrupts[kind + (" out of WAI" if was_waiting else "")] += 1
                if entries > 1:
                    interrupts["back-to-back entries"] += 1
                if was_waiting:
                    # MAME idles in WAI until its timeslice ends; resynchronise.
                    total = nxt.cycles
                    resyncs += 1
            if bus.queue:
                raise Divergence(f"MAME logged {list(bus.queue)} that the core did not do")
        except Divergence as problem:
            report(game, i, [*history, line, nxt], str(problem))
            return 1
        history.append(line)
        line, nxt = nxt, next(lines, None)
        i += 1

    print(
        f"{game}: {i} instructions replayed, all registers, bus accesses and "
        f"cycle totals agree with MAME 0.285"
    )
    print(f"  interrupts injected where MAME took them: {dict(interrupts)}")
    if resyncs:
        print(f"  cycle total resynchronised after {resyncs} WAI exits (MAME eats the timeslice)")
    undocumented = {
        f"${op:02X}": n
        for op, n in opcodes.items()
        if op is not None and not documented(machine.part, op)
    }
    print(
        f"  distinct opcodes executed: {len(opcodes)}; undocumented ones (MAME's "
        f"behaviour, via undocumented='mame'): {undocumented or 'none'}"
    )
    if machine.part == "6803":
        only = {
            f"${op:02X}": n
            for op, n in sorted(opcodes.items(), key=lambda kv: kv[0] or 0)
            if op is not None and documented("6803", op) and not documented("6800", op)
        }
        print(f"  MC6801-only opcodes executed: {only}")
    return 0


def pushed_frames(queue: deque) -> list[int]:
    """The PCs pushed by each whole seven-write interrupt frame left in ``queue``."""
    accesses = list(queue)
    pcs = []
    while len(accesses) >= 7 and all(kind == "W" for kind, _, _ in accesses[:7]):
        frame, accesses = accesses[:7], accesses[7:]
        addresses = [address for _, address, _ in frame]
        if addresses != [(addresses[0] - n) & 0xFFFF for n in range(7)]:
            break
        pcs.append((frame[1][2] << 8) | frame[0][2])  # PCL at S, PCH at S-1
    return pcs


def documented(part: str, opcode: int) -> bool:
    sys.path.insert(0, str(ROOT / "tests"))
    from datasheet import DATASHEET

    entry = DATASHEET.get(opcode)
    if entry is None:
        return False
    return (entry.cycles_6800 if part == "6800" else entry.cycles_6801) is not None


def fmt(state: tuple) -> str:
    pc, a, b, x, s, cc = state
    return f"PC={pc:04X} A={a:02X} B={b:02X} X={x:04X} S={s:04X} CC={cc:02X}"


def report(game: str, i: int, context: list[Line], problem: str) -> None:
    line = context[-2]
    print(
        f"{game}: DIVERGED at instruction {i} (error.log line {line.number}), "
        f"PC=${line.pc:04X}: {problem}"
    )
    for c in context:
        print(
            f"    {c.pc:04X} A={c.a:02X} B={c.b:02X} X={c.x:04X} S={c.s:04X} CC={c.cc:02X} "
            f"tc={c.cycles} {c.accesses}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("game", choices=sorted(MACHINES))
    parser.add_argument("--trace", type=Path)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    trace = args.trace or ROOT / "mame-work" / args.game / "error.log"
    if not trace.exists():
        m = MACHINES[args.game]
        press = f'M6800_PRESS="{m.press}" ' if m.press else ""
        sys.exit(
            f"{trace} missing; make it with:\n  {press}M6800_WATCH_READS={m.watch_reads} "
            f"M6800_WATCH_WRITES=0000-FFFF scripts/mame_trace.sh {args.game} "
            f"{m.seconds} {m.tag} mame-work/{args.game}"
        )
    sys.exit(replay(args.game, trace, args.limit))


if __name__ == "__main__":
    main()
