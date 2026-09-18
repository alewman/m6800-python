"""Replay the MAME single-step corpus through the core and report every difference.

    python scripts/compare_mame_corpus.py [--part 6800|6803] [--limit N] [--show 3]

Reads tests/vectors/m6800/XX.jsonl and tests/vectors/m6803/XX.jsonl (made by
scripts/mame_corpus.py), runs each case through ``M6800``/``M6803`` with
``mame_compat=True`` -- so that the opcodes Motorola does not assign follow
MAME too -- and compares registers, final memory, cycles, the exact sequence
of bus reads and writes, and whether WAI left the CPU waiting.

MAME is emulator-derived: a disagreement is a *question*, not a bug.  Each
kind of disagreement the core has on purpose is listed in ``EXPLAINED`` with
the higher-tier source it follows; anything else is reported as unexplained
and makes the exit status 1.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from m6800_python import M6800, M6803  # noqa: E402

VECTORS = ROOT / "tests" / "vectors"

#: (part, opcode, field) -> why the core differs from MAME there, and on whose
#: authority.  "part" is "6800", "6803" or "*".
EXPLAINED: dict[tuple[str, int, str], str] = {
    ("*", 0x06, "cc"): (
        "TAP transfers bits 0-5 of A only and CC bits 7-6 stay 1 (M68PRM p. A-70, and TPA/"
        "SWI/WAI all show them set, pp. A-67/A-72/A-76); MAME copies all eight bits of A"
    ),
    ("*", 0x3B, "cc"): (
        "RTI: CC bits 7-6 read as 1 (M68PRM pp. A-67, A-72); MAME restores the stacked byte "
        "as-is, so a stacked byte with bits 7-6 clear leaves them clear"
    ),
}


class Memory:
    """The case's sparse memory, logging accesses in MAME's format."""

    def __init__(self, cells: list[list[int]]) -> None:
        self.cells = dict(cells)
        self.log: list[list] = []

    def read(self, address: int) -> int:
        value = self.cells[address]  # MAME recorded every address it read
        self.log.append(["r", address, value])
        return value

    def write(self, address: int, value: int) -> None:
        self.cells[address] = value
        self.log.append(["w", address, value])


def run_case(cls, case: dict) -> dict[str, tuple]:
    """Return {field: (mame, core)} for every field that differs."""
    initial, final = case["initial"], case["final"]
    memory = Memory(initial["ram"])
    cpu = cls(memory.read, memory.write, mame_compat=True)
    cpu.PC, cpu.SP, cpu.X = initial["pc"], initial["s"], initial["x"]
    cpu.A, cpu.B, cpu.CC = initial["a"], initial["b"], initial["cc"]
    try:
        cycles = cpu.step()
    except KeyError as missing:  # the core read an address MAME did not
        return {"bus": (case["bus"], f"core read ${missing.args[0]:04X}, which MAME did not")}
    diffs: dict[str, tuple] = {}
    got = {"pc": cpu.PC, "s": cpu.SP, "x": cpu.X, "a": cpu.A, "b": cpu.B, "cc": cpu.CC}
    for field, value in got.items():
        if final[field] != value:
            diffs[field] = (final[field], value)
    if dict(map(tuple, final["ram"])) != memory.cells:
        diffs["ram"] = (final["ram"], sorted(memory.cells.items()))
    if case["cycles"] != cycles:
        diffs["cycles"] = (case["cycles"], cycles)
    if case["bus"] != memory.log:
        diffs["bus"] = (case["bus"], memory.log)
    if case["wai"] != cpu.waiting:
        diffs["wai"] = (case["wai"], cpu.waiting)
    return diffs


def explained(part: str, opcode: int, field: str) -> str | None:
    return EXPLAINED.get((part, opcode, field)) or EXPLAINED.get(("*", opcode, field))


def compare(part: str, limit: int | None, show: int) -> tuple[int, int, int]:
    cls = M6800 if part == "6800" else M6803
    total = agree = 0
    unexplained: dict[tuple[int, str], list] = defaultdict(list)
    explained_counts: Counter = Counter()
    for opcode in range(256):
        path = VECTORS / f"m{part}" / f"{opcode:02X}.jsonl"
        with path.open() as lines:
            for n, line in enumerate(lines):
                if limit is not None and n >= limit:
                    break
                case = json.loads(line)
                total += 1
                diffs = run_case(cls, case)
                if not diffs:
                    agree += 1
                    continue
                for field, pair in diffs.items():
                    if explained(part, opcode, field):
                        explained_counts[(opcode, field)] += 1
                    else:
                        unexplained[(opcode, field)].append((case["name"], pair))
    print(f"== MC{part}: {total} cases, {agree} agree exactly with MAME 0.285")
    for (opcode, field), count in sorted(explained_counts.items()):
        print(f"  explained  ${opcode:02X} {field:6} x{count}: {explained(part, opcode, field)}")
    for (opcode, field), cases in sorted(unexplained.items()):
        print(f"  UNEXPLAINED ${opcode:02X} {field:6} x{len(cases)}")
        for name, (mame, core) in cases[:show]:
            print(f"      {name}: MAME {mame}  core {core}")
    return total, agree, sum(len(c) for c in unexplained.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--part", choices=["6800", "6803"], action="append")
    parser.add_argument("--limit", type=int, help="cases per opcode (default: all)")
    parser.add_argument("--show", type=int, default=3, help="examples per unexplained group")
    args = parser.parse_args()
    if not (VECTORS / "m6800").exists():
        sys.exit("no corpus: run scripts/mame_corpus.py generate first")
    failures = 0
    for part in args.part or ["6800", "6803"]:
        failures += compare(part, args.limit, args.show)[2]
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
