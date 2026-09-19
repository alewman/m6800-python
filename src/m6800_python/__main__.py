"""Load a program and step through it: ``python -m m6800_python``.

    python -m m6800_python --load program.bin@1000 --pc 1000
    python -m m6800_python --part 6803 --zip ROMPATH/kncljoe.zip:kj-13.bin@E000 --reset
    python -m m6800_python --zip robotron.zip:video_sound_rom_3_std_767.ic12@F000 \\
        --reset -c "break FB11" -c "run 100000"

The host is flat 64K RAM holding every image loaded, so ROM is writable and
there are no devices: good for reading and stepping through code, not for
running a board (for that, write a host -- scripts/williams_sound.py is one).
Commands given with ``-c`` run first; then the prompt reads stdin, unless
``--batch`` is given.  ``help`` lists the commands.
"""

import argparse
import sys
import zipfile
from pathlib import Path

from m6800_python.console import CommandDebugger, CommandError, parse_number
from m6800_python.cpu import M6800, M6803
from m6800_python.debug import DebugSession


def _image(spec: str, zipped: bool) -> tuple[bytes, int]:
    source, _, where = spec.rpartition("@")
    if not source:
        raise SystemExit(f"{spec!r}: give the load address as FILE@ADDRESS")
    address = parse_number(where, "load address", maximum=0xFFFF)
    if zipped:
        archive, _, member = source.rpartition(":")
        if not archive:
            raise SystemExit(f"{spec!r}: give --zip as ZIPFILE:MEMBER@ADDRESS")
        with zipfile.ZipFile(archive) as z:
            data = z.read(member)
    else:
        data = Path(source).read_bytes()
    if address + len(data) > 0x10000:
        raise SystemExit(f"{spec!r}: {len(data)} bytes do not fit at ${address:04X}")
    return data, address


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m m6800_python",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--part", default="6800", choices=["6800", "6802", "6808", "6801", "6803"])
    parser.add_argument(
        "--load",
        action="append",
        default=[],
        metavar="FILE@ADDRESS",
        help="load a binary file at a hex address",
    )
    parser.add_argument(
        "--zip",
        action="append",
        default=[],
        metavar="ZIP:MEMBER@ADDRESS",
        help="load one file out of a zip (a MAME ROM set) at a hex address",
    )
    start = parser.add_mutually_exclusive_group()
    start.add_argument("--pc", help="start at this hex address")
    start.add_argument("--reset", action="store_true", help="start from the $FFFE vector")
    parser.add_argument("--undocumented", default="strict", choices=["strict", "measured", "mame"])
    parser.add_argument(
        "-c",
        "--command",
        action="append",
        default=[],
        help="a debugger command to run first (repeatable)",
    )
    parser.add_argument("--batch", action="store_true", help="exit after the -c commands")
    args = parser.parse_args(argv)

    memory = bytearray(0x10000)
    for spec in args.load:
        data, address = _image(spec, zipped=False)
        memory[address : address + len(data)] = data
    for spec in args.zip:
        data, address = _image(spec, zipped=True)
        memory[address : address + len(data)] = data
    cls = M6800 if args.part in ("6800", "6802", "6808") else M6803
    cpu = cls(memory.__getitem__, memory.__setitem__, undocumented=args.undocumented)
    if args.reset:
        cpu.reset()
    elif args.pc is not None:
        cpu.PC = parse_number(args.pc, "pc", maximum=0xFFFF)
    session = DebugSession(cpu, peek_byte=memory.__getitem__, track_accesses=True)
    debugger = CommandDebugger(session)
    for command in ["registers", "disassemble", *args.command]:
        print(f"m{session.part}> {command}")
        try:
            result = debugger.execute(command)
        except CommandError as exc:
            print(f"error: {exc}")
            continue
        for line in result.lines:
            print(line)
        if result.quit:
            return
    if not args.batch:
        debugger.interact(sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
