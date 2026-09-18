"""Readability contract for the instruction core, enforced the way correctness is.

Following z80-python's tests/test_readability.py: every opcode handler must be
findable by the mnemonic a 6800 programmer would grep for, and must live in the
module that owns that instruction group.  Checked from the source with
:mod:`ast`, without importing or executing it:

1. Every ``_op_*`` method's docstring starts with exactly one Motorola mnemonic,
   then ``--`` and a description that cites its manual page.
2. The handler lives in the module that owns that mnemonic.
3. Every documented mnemonic has a handler, and the handler is named after it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from datasheet import DATASHEET

SRC = Path(__file__).resolve().parents[1] / "src" / "m6800_python"

OWNERS: dict[str, frozenset[str]] = {
    module: frozenset(mnemonics.split())
    for module, mnemonics in {
        "_alu.py": "ABA ADCA ADCB ADDA ADDB SBA SBCA SBCB SUBA SUBB CBA CMPA CMPB ANDA ANDB "
        "BITA BITB EORA EORB ORAA ORAB CLR CLRA CLRB COM COMA COMB NEG NEGA NEGB INC INCA "
        "INCB DEC DECA DECB TST TSTA TSTB DAA CLC SEC CLV SEV ADDD SUBD MUL",
        "_shifts.py": "ASL ASLA ASLB ASR ASRA ASRB LSR LSRA LSRB ROL ROLA ROLB ROR RORA RORB "
        "ASLD LSRD",
        "_loads.py": "LDAA LDAB STAA STAB LDD STD TAB TBA TAP TPA",
        "_index.py": "LDX STX LDS STS CPX INX DEX ABX INS DES TSX TXS",
        "_stack.py": "PSHA PSHB PULA PULB PSHX PULX",
        "_branches.py": "BRA BRN BHI BLS BCC BCS BNE BEQ BVC BVS BPL BMI BGE BLT BGT BLE BSR "
        "JMP JSR RTS NOP",
        "_interrupts.py": "CLI SEI SWI WAI RTI",
    }.items()
}
MOTOROLA = frozenset().union(*OWNERS.values())
HEADLINE = re.compile(r"^(?P<mnemonic>[A-Z]+) -- (?P<text>.+)$")
CITATION = re.compile(r"\((M68PRM|M6801RM) (p|pp)\. A-\d+")


def handlers() -> list[tuple[str, ast.FunctionDef]]:
    found = []
    for path in sorted(SRC.glob("_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
            found += [
                (path.name, node)
                for node in cls.body
                if isinstance(node, ast.FunctionDef) and node.name.startswith("_op_")
            ]
    assert found
    return found


HANDLERS = handlers()


def headline(node: ast.FunctionDef) -> re.Match:
    doc = ast.get_docstring(node) or ""
    match = HEADLINE.match(doc.splitlines()[0] if doc else "")
    assert match, f"{node.name}: docstring must start 'MNEMONIC -- ...', got {doc[:40]!r}"
    return match


@pytest.mark.parametrize("module,node", HANDLERS, ids=lambda x: getattr(x, "name", x))
def test_docstring_names_one_motorola_mnemonic_and_cites_the_manual(module, node) -> None:
    match = headline(node)
    assert match.group("mnemonic") in MOTOROLA, f"{node.name}: not a Motorola mnemonic"
    assert node.name == "_op_" + match.group("mnemonic").lower()
    assert CITATION.search(match.group("text")), f"{node.name}: no manual page cited"


@pytest.mark.parametrize("module,node", HANDLERS, ids=lambda x: getattr(x, "name", x))
def test_handler_lives_in_owning_module(module, node) -> None:
    mnemonic = headline(node).group("mnemonic")
    assert mnemonic in OWNERS[module], f"{mnemonic} is misfiled in {module}"


def test_every_documented_mnemonic_has_exactly_one_handler() -> None:
    names = [headline(node).group("mnemonic") for _, node in HANDLERS]
    assert len(names) == len(set(names)), "a handler is defined twice"
    assert set(names) == {o.mnemonic for o in DATASHEET.values()} == MOTOROLA
