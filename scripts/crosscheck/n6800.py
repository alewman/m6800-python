"""Rung 5: the core against Robert Baruch's n6800 RTL model, on the MC6800 corpus.

    python scripts/crosscheck/n6800.py [--limit N] [--show 2]

n6800 (https://github.com/RobertBaruch/n6800, GPL-3.0, "WORK IN PROGRESS") is a
cycle-by-cycle MC6800 written in nMigen, the design shdl6800 (named in the
handoff brief) is a partial SpinalHDL port of.  Neither was validated against
silicon: both are checked by their authors' own formal properties, and their
bus cycles were written from Motorola's cycle-by-cycle tables (MCSDD Table 8),
so on timing they are a second reading of the datasheet, not a measurement.
Running n6800 needs Python 3.9 and amaranth 0.3; none of it is committed:

    git clone https://github.com/RobertBaruch/n6800 third_party/n6800
    git -C third_party/n6800 checkout f117162866c14dff0d0f23e22f48fdd5f9ace923
    uv python install 3.9      # any CPython 3.9
    python3.9 -m venv third_party/n6800-venv
    third_party/n6800-venv/bin/pip install amaranth==0.3 'markupsafe<2.1'

For every documented-opcode case of tests/vectors/m6800 the core and n6800 run
from the same state, and this compares registers, final memory, the cycle
count, and the bus: every access the core makes must appear, in order, among
n6800's valid bus cycles (VMA high).  n6800 also makes the MC6800's dummy
reads -- VMA-high cycles whose data is ignored (MCSDD Table 8, "Irrelevant
Data") -- which neither the core nor MAME models; those are counted, not
treated as disagreements.  **Tier: emulator-derived** (RTL); differences are
leads for the manuals to settle.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from datasheet import DATASHEET  # noqa: E402

from m6800_python import M6800  # noqa: E402

N6800 = ROOT / "third_party" / "n6800"
PYTHON = ROOT / "third_party" / "n6800-venv" / "bin" / "python"
HARNESS = ROOT / "scripts" / "crosscheck" / "n6800_harness.py"
VECTORS = ROOT / "tests" / "vectors" / "m6800"


def run_core(initial: dict) -> dict:
    memory = dict(map(tuple, initial["ram"]))
    bus: list[list] = []

    def read(address: int) -> int:
        value = memory.get(address, 0)
        bus.append(["r", address, value])
        return value

    def write(address: int, value: int) -> None:
        memory[address] = value
        bus.append(["w", address, value])

    cpu = M6800(read, write)
    cpu.PC, cpu.SP, cpu.X = initial["pc"], initial["s"], initial["x"]
    cpu.A, cpu.B, cpu.CC = initial["a"], initial["b"], initial["cc"]
    cycles = cpu.step()
    return {
        "pc": cpu.PC,
        "s": cpu.SP,
        "x": cpu.X,
        "a": cpu.A,
        "b": cpu.B,
        "cc": cpu.CC,
        "cycles": cycles,
        "bus": bus,
        "ram": memory,
        "waiting": cpu.waiting,
    }


def subsequence(needle: list, haystack: list) -> bool:
    it = iter(haystack)
    return all(
        any(access[:2] == other[:2] and (access[2] == other[2] or other[2] is None) for other in it)
        for access in needle
    )


def compare(limit: int | None, show: int) -> int:
    cases = []
    for opcode, entry in sorted(DATASHEET.items()):
        if entry.cycles_6800 is None:
            continue
        with (VECTORS / f"{opcode:02X}.jsonl").open() as lines:
            for n, line in enumerate(lines):
                if limit is not None and n >= limit:
                    break
                cases.append((opcode, json.loads(line)["initial"]))
    feed = "\n".join(json.dumps(initial) for _, initial in cases) + "\n"
    run = subprocess.run(
        [str(PYTHON), "-W", "ignore", str(HARNESS)],
        input=feed,
        capture_output=True,
        text=True,
        cwd=N6800,
        check=True,
        env={"PYTHONPATH": str(N6800)},
    )
    results = [json.loads(line) for line in run.stdout.splitlines()]
    if len(results) != len(cases):
        sys.exit(f"n6800 harness returned {len(results)} results for {len(cases)} cases")

    differ: dict[tuple[int, str], list] = defaultdict(list)
    per_opcode: Counter = Counter()
    exact: Counter = Counter()
    dummy_reads = 0
    for (opcode, initial), rtl in zip(cases, results, strict=True):
        core = run_core(initial)
        per_opcode[opcode] += 1
        rtl["ram"] = dict(map(tuple, rtl["ram"]))
        fields = [field for field in ("pc", "s", "x", "a", "b") if core[field] != rtl[field]]
        if (core["cc"] & 0x3F) != (rtl["cc"] & 0x3F):
            fields.append("cc")
        if dict(core["ram"].items()) != {
            k: v for k, v in rtl["ram"].items() if k in core["ram"] or v is not None
        }:
            fields.append("ram")
        if core["waiting"]:
            if rtl["cycles"] is not None:
                fields.append("wai")
        elif core["cycles"] != rtl["cycles"]:
            fields.append("cycles")
        if not subsequence(core["bus"], rtl["bus"]):
            fields.append("bus")
        else:
            dummy_reads += len(rtl["bus"]) - len(core["bus"])
        for field in fields:
            differ[(opcode, field)].append((initial, core, rtl))
        if not fields:
            exact[opcode] += 1

    total = sum(per_opcode.values())
    print(
        f"== MC6800 vs n6800 (RTL), {total} documented-opcode cases: "
        f"{sum(exact.values())} agree on registers, memory, cycles and bus order"
    )
    print(f"   n6800's extra valid-bus cycles (dummy reads, MCSDD Table 8): {dummy_reads}")
    full = sorted(op for op in per_opcode if exact[op] == per_opcode[op])
    print(f"   opcodes agreeing on every case: {len(full)} of {len(per_opcode)}")
    by_mnemonic: dict[str, list] = defaultdict(list)
    for (opcode, field), found in sorted(differ.items()):
        by_mnemonic[DATASHEET[opcode].mnemonic].append((opcode, field, len(found), found))
    for mnemonic, rows in sorted(by_mnemonic.items()):
        summary = ", ".join(f"${op:02X} {field} x{n}" for op, field, n, _ in rows)
        print(f"  {mnemonic:5} {summary}")
        for opcode, field, _, found in rows[:1]:
            for initial, core, rtl in found[:show]:
                if field in ("cycles", "wai"):
                    detail = f"core {core['cycles']} n6800 {rtl['cycles']}"
                elif field == "bus":
                    detail = f"core {core['bus']} n6800 {rtl['bus']}"
                elif field == "ram":
                    detail = "memory differs"
                else:
                    detail = f"core {core[field]} n6800 {rtl[field]}"
                print(f"      ${opcode:02X} pc={initial['pc']:04X}: {detail}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--limit", type=int, help="cases per opcode (default: all 1,000)")
    parser.add_argument("--show", type=int, default=1)
    args = parser.parse_args()
    for needed in (VECTORS, N6800, PYTHON):
        if not needed.exists():
            sys.exit(f"{needed} missing; see this script's docstring")
    sys.exit(compare(args.limit, args.show))


if __name__ == "__main__":
    main()
