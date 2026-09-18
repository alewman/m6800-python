"""Rung 5: three-way diff of the core, MAME 0.285 and sim68xx on the MC6800 corpus.

    python scripts/crosscheck/sim68xx.py [--limit N] [--show 2]

sim68xx (Arne Riiber 1994-2004, Felix Erckenbrecht 2011;
https://github.com/dg1yfe/sim68xx, GPL-2.0) is an independent C simulator of
the 6800 family.  It is not committed here: clone and build it into
third_party/ with

    git clone https://github.com/dg1yfe/sim68xx third_party/sim68xx
    git -C third_party/sim68xx checkout d49c99a61e6437d84ec313b91511db23e02efb54
    make -C third_party/sim68xx/src CFLAGS='-O2 -std=gnu89 -w'

and this script links scripts/crosscheck/sim68xx_harness.c against its MC6800
objects.  Only the MC6800 is compared: sim68xx's 6801-family targets are the
Hitachi HD6301/HD6303, whose cycle counts are Hitachi's.

Every documented-opcode case of tests/vectors/m6800 (the MAME corpus) is run
through all three from the same initial state; registers and the final memory
at every address MAME touched are compared.  **Cycles are not**: sim68xx's
MC6800 opcode table (src/arch/m6800/optab.c) carries the Hitachi HD6301's
cycle counts -- NOP 1, BRA 3, INX 1 -- so it has no independent opinion on
MC6800 timing.  Each disagreement is
classified by which implementation is the odd one out.  **Tier: all three are
emulator-derived**; where two agree against the third, that is a lead, and
the manuals decide (docs/validation.md).
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

SIM = ROOT / "third_party" / "sim68xx"
HARNESS = ROOT / "third_party" / "sim68xx-harness"
VECTORS = ROOT / "tests" / "vectors" / "m6800"
FIELDS = ("pc", "s", "x", "a", "b", "cc", "cycles")
COMPARED = ("pc", "s", "x", "a", "b", "cc", "ram")  # not cycles: see the docstring


def build_harness() -> None:
    src = SIM / "src"
    if not (src / "arch" / "m6800" / "opfunc.o").exists():
        sys.exit(f"{SIM} is not built; see this script's docstring")
    names = "callstac command cpu io fileio memory reg opfunc optab instr ireg sci"
    objects = [f"arch/m6800/{name}.o" for name in names.split()]
    objects += [f"base/{name}.o" for name in ("error", "fprinthe", "symtab", "tty")]
    subprocess.run(
        [
            "gcc",
            "-O2",
            "-std=gnu89",
            "-w",
            "-DUSE_PROTOTYPES",
            "-DHAS_SCI",
            "-DM6800",
            "-I../inc/arch/m6800",
            "-I../inc/arch/m68xx",
            "-I../inc/base",
            "-o",
            str(HARNESS),
            str(ROOT / "scripts" / "crosscheck" / "sim68xx_harness.c"),
            *objects,
        ],
        cwd=src,
        check=True,
    )


def core_result(case: dict) -> dict:
    initial = case["initial"]
    memory = dict(map(tuple, initial["ram"]))
    cpu = M6800(memory.__getitem__, memory.__setitem__)
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
        "ram": memory,
    }


def compare(limit: int | None, show: int) -> int:
    cases = []
    for opcode, entry in sorted(DATASHEET.items()):
        if entry.cycles_6800 is None:
            continue
        with (VECTORS / f"{opcode:02X}.jsonl").open() as lines:
            for n, line in enumerate(lines):
                if limit is not None and n >= limit:
                    break
                cases.append((opcode, json.loads(line)))
    feed = []
    for _, case in cases:
        i = case["initial"]
        pairs = " ".join(f"{a} {v}" for a, v in i["ram"])
        feed.append(
            f"{i['pc']} {i['s']} {i['x']} {i['a']} {i['b']} {i['cc']} {len(i['ram'])} {pairs}"
        )
    run = subprocess.run(
        [str(HARNESS)], input="\n".join(feed) + "\n", capture_output=True, text=True, check=True
    )
    outputs = run.stdout.splitlines()
    if len(outputs) != len(cases):
        sys.exit(f"sim68xx harness returned {len(outputs)} lines for {len(cases)} cases")

    odd_one: dict[tuple[int, str, str], list] = defaultdict(list)
    agree = 0
    for (opcode, case), out in zip(cases, outputs, strict=True):
        values = [int(v) for v in out.split()]
        sim = dict(zip(FIELDS, values[:7], strict=True))
        sim["ram"] = dict(zip(values[7::2], values[8::2], strict=True))
        mame = {
            **case["final"],
            "cycles": case["cycles"],
            "ram": dict(map(tuple, case["final"]["ram"])),
        }
        core = core_result(case)
        mame["cc"] |= 0xC0  # sim68xx and the core both read bits 7-6 as 1
        differs = False
        for field in COMPARED:
            m, c, s = mame[field], core[field], sim[field]
            if m == c == s:
                continue
            differs = True
            if m == c:
                who = "sim68xx"
            elif m == s:
                who = "core"
            elif c == s:
                who = "MAME"
            else:
                who = "all three"
            odd_one[(opcode, field, who)].append((case["name"], m, c, s))
        agree += not differs
    print(f"== MC6800, {len(cases)} documented-opcode cases: {agree} agree three ways")
    by_who = Counter()
    for (opcode, field, who), found in sorted(odd_one.items()):
        by_who[who] += len(found)
        mnemonic = DATASHEET[opcode].mnemonic
        print(f"  ${opcode:02X} {mnemonic:5} {field:6} odd one out: {who:9} x{len(found)}")
        for name, m, c, s in found[:show]:
            if field == "ram":
                keys = sorted(
                    k for k in set(m) | set(c) | set(s) if not m.get(k) == c.get(k) == s.get(k)
                )
                m, c, s = ({k: d.get(k) for k in keys} for d in (m, c, s))
            print(f"      {name}: MAME {m}  core {c}  sim68xx {s}")
    print(f"  cases per odd one out: {dict(by_who)}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--limit", type=int, help="cases per opcode (default: all 1,000)")
    parser.add_argument("--show", type=int, default=2)
    args = parser.parse_args()
    if not VECTORS.exists():
        sys.exit("no corpus: run scripts/mame_corpus.py generate first")
    build_harness()
    sys.exit(compare(args.limit, args.show))


if __name__ == "__main__":
    main()
