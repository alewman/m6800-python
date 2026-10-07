"""validation/functional_test.asm and functional_test_6801.asm: the
self-checking functional test program from docs/handoff-polish.md's item 8.

Fast and infra-free: assembling the committed source reproduces the committed
.bin byte for byte (the same guarantee tests/datasheet.py's generation gets),
and running the assembled image through this project's own core reaches
SUCCESS with A = $AA on every part it claims to support. The sim68xx and
n6800 crosschecks are standalone scripts, like every other rung 5 check in
this project (scripts/crosscheck/sim68xx.py, scripts/crosscheck/n6800.py,
scripts/crosscheck/functional_test_n6800.py) -- not wrapped here, since they
need third_party/ built and take real time to run.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from conftest import Bus

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from asm6800 import Assembler  # noqa: E402

from m6800_python import M6800, M6803  # noqa: E402

VALIDATION = ROOT / "validation"
FILES = {
    "functional_test": ("6800", ["6800", "6803"]),
    "functional_test_6801": ("6803", ["6803"]),
}


def run_to_a_stop(part: str, data: bytes, origin: int, *, max_steps: int = 2000) -> tuple[int, int]:
    """Run from the reset vector until the PC stops changing; return (pc, A)."""
    bus = Bus()
    bus.load(origin, data)
    cpu = {"6800": M6800, "6803": M6803}[part](bus.read, bus.write)
    cpu.PC = bus.word(0xFFFE)
    for _ in range(max_steps):
        pc = cpu.PC
        cpu.step()
        if cpu.PC == pc:
            return pc, cpu.A
    raise AssertionError(f"did not stop within {max_steps} steps")


@pytest.mark.parametrize("name", sorted(FILES))
def test_source_assembles_to_the_committed_binary(name: str) -> None:
    source = (VALIDATION / f"{name}.asm").read_text()
    origin, data, _symbols = Assembler().assemble(source)
    assert origin == 0x1000
    assert data == (VALIDATION / f"{name}.bin").read_bytes()


@pytest.mark.parametrize("name", sorted(FILES))
def test_reaches_success_on_every_part_it_claims(name: str) -> None:
    _default_part, parts = FILES[name]
    data = (VALIDATION / f"{name}.bin").read_bytes()
    origin, _data2, symbols = Assembler().assemble((VALIDATION / f"{name}.asm").read_text())
    for part in parts:
        pc, a = run_to_a_stop(part, data, origin)
        assert pc == symbols["DONE"], f"{name} on {part} stopped at ${pc:04X}, not DONE"
        assert a == 0xAA, f"{name} on {part} reached DONE with A=${a:02X}, not $AA"


def test_every_documented_6800_mnemonic_except_wai_is_covered() -> None:
    import gen_functional_test as gen
    from datasheet import DATASHEET

    by_mnemonic: dict[str, list] = {}
    for entry in DATASHEET.values():
        by_mnemonic.setdefault(entry.mnemonic, []).append(entry)
    shared = {
        mn for mn, entries in by_mnemonic.items() if any(e.cycles_6800 is not None for e in entries)
    }
    only_6801 = set(by_mnemonic) - shared

    w6800 = gen.generate_6800()
    w6801 = gen.generate_6801()
    assert w6800.covered == shared - {"WAI"}
    assert w6801.covered == only_6801 | {"CPX"}  # CPX's 6801-only carry gets its own case too
