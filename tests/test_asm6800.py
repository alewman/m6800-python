"""scripts/asm6800.py: the small two-pass assembler written for item 8's
functional test, since no system assembler (asl, vasm6800_std, a68) was found
on this machine. Exercises the syntax validation/functional_test.asm uses:
labels (forward and backward), EQU, every addressing mode's operand syntax,
FCB/FDB/RMB, a non-contiguous ORG gap, and the error cases.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from asm6800 import Assembler, AssemblerError, to_s19  # noqa: E402


def assemble(source: str) -> tuple[int, bytes, dict[str, int]]:
    return Assembler().assemble(source)


def test_inherent_and_immediate() -> None:
    origin, data, _symbols = assemble("\tORG $1000\n\tNOP\n\tLDAA #$42\n\tLDX #$1234\n")
    assert origin == 0x1000
    assert data == bytes([0x01, 0x86, 0x42, 0xCE, 0x12, 0x34])


def test_direct_and_extended_forced() -> None:
    _origin, data, _symbols = assemble("\tORG $1000\n\tLDAA <$20\n\tLDAA >$0020\n")
    assert data == bytes([0x96, 0x20, 0xB6, 0x00, 0x20])


def test_direct_extended_auto_pick_from_a_numeric_literal() -> None:
    _origin, data, _symbols = assemble("\tORG $1000\n\tLDAA $20\n\tLDAA $1234\n")
    assert data == bytes([0x96, 0x20, 0xB6, 0x12, 0x34])


def test_bare_label_operand_is_ambiguous_for_a_direct_extended_mnemonic() -> None:
    with pytest.raises(AssemblerError, match="ambiguous"):
        assemble("\tORG $1000\nFOO EQU $20\n\tLDAA FOO\n")


def test_bare_label_operand_is_fine_for_a_single_mode_mnemonic() -> None:
    # JMP has only extended and indexed -- no ambiguity, even forward-referenced.
    _origin, data, symbols = assemble("\tORG $1000\n\tJMP TARGET\nTARGET:\tNOP\n")
    assert data == bytes([0x7E, 0x10, 0x03, 0x01])
    assert symbols["TARGET"] == 0x1003


def test_indexed() -> None:
    _origin, data, _symbols = assemble("\tORG $1000\n\tLDAA $10,X\n\tLDAA ,X\n")
    assert data == bytes([0xA6, 0x10, 0xA6, 0x00])


def test_relative_forward_and_backward_and_self() -> None:
    source = "\tORG $1000\nSTART:\tBRA MID\nMID:\tBRA START\nLOOP:\tBRA LOOP\n"
    _origin, data, symbols = assemble(source)
    # MID is immediately after BRA MID (offset 0); BRA START jumps back 4; LOOP is self (-2).
    assert data == bytes([0x20, 0x00, 0x20, 0xFC, 0x20, 0xFE])
    assert symbols == {"START": 0x1000, "MID": 0x1002, "LOOP": 0x1004}


def test_relative_out_of_range_is_an_error() -> None:
    far = "\tRMB 200\n"
    source = f"\tORG $1000\nSTART:\tBRA TARGET\n{far}TARGET:\tNOP\n"
    with pytest.raises(AssemblerError, match="branch out of range"):
        assemble(source)


def test_equ_fcb_fdb_rmb() -> None:
    source = "\tORG $1000\nN\tEQU 5\n\tFCB 1,2,N\n\tFDB $1234,N\n\tRMB 3\n\tNOP\n"
    _origin, data, symbols = assemble(source)
    assert data == bytes([1, 2, 5, 0x12, 0x34, 0x00, 0x05, 0, 0, 0, 0x01])
    assert symbols["N"] == 5


def test_label_and_instruction_share_a_line() -> None:
    _origin, data, symbols = assemble("\tORG $1000\nSTART:\tLDAA #$01\n\tBRA START\n")
    assert symbols["START"] == 0x1000
    assert data == bytes([0x86, 0x01, 0x20, 0xFC])


def test_expression_addition_and_subtraction() -> None:
    source = "\tORG $1000\nBASE\tEQU $40\n\tLDAA <BASE+1\n\tLDAA <BASE-1\n"
    _origin, data, _symbols = assemble(source)
    assert data == bytes([0x96, 0x41, 0x96, 0x3F])


def test_non_contiguous_org_pads_the_gap_with_ff() -> None:
    source = "\tORG $1000\n\tNOP\n\tORG $1004\n\tNOP\n"
    origin, data, _symbols = assemble(source)
    assert origin == 0x1000
    assert data == bytes([0x01, 0xFF, 0xFF, 0xFF, 0x01])


def test_org_may_not_go_backward_over_emitted_bytes() -> None:
    with pytest.raises(AssemblerError, match="backward"):
        assemble("\tORG $1000\n\tNOP\n\tNOP\n\tORG $1000\n\tNOP\n")


def test_unknown_mnemonic_is_an_error() -> None:
    with pytest.raises(AssemblerError, match="unknown mnemonic"):
        assemble("\tORG $1000\n\tFROB #$01\n")


def test_mode_the_mnemonic_does_not_have_is_an_error() -> None:
    with pytest.raises(AssemblerError, match="no immediate mode"):
        assemble("\tORG $1000\n\tSTAA #$01\n")


def test_fcb_value_out_of_range_is_an_error() -> None:
    with pytest.raises(AssemblerError, match="out of range"):
        assemble("\tORG $1000\n\tFCB 256\n")


def test_undefined_symbol_is_an_error() -> None:
    with pytest.raises(AssemblerError, match="undefined symbol"):
        assemble("\tORG $1000\n\tLDAA <NOPE\n")


def test_s19_round_trips_through_a_loader() -> None:
    _origin, data, _symbols = assemble("\tORG $1000\n\tLDAA #$42\n\tNOP\n")
    s19 = to_s19(0x1000, data)
    lines = s19.strip().splitlines()
    assert lines[0].startswith("S1")
    assert lines[-1] == "S9030000FC"
    # Decode the one S1 record by hand and check it matches the assembled bytes.
    record = lines[0]
    count = int(record[2:4], 16)
    body = bytes.fromhex(record[4 : 4 + (count - 1) * 2])
    address = int.from_bytes(body[:2], "big")
    payload = body[2:]
    assert address == 0x1000
    assert payload == data


def test_comments_and_blank_lines_are_ignored() -> None:
    source = "\t; a comment\n\tORG $1000  ; origin\n\n\tNOP ; inline\n\n"
    _origin, data, _symbols = assemble(source)
    assert data == bytes([0x01])
