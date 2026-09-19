"""``python -m m6800_python``: loading images and running commands."""

from __future__ import annotations

import zipfile

import pytest

from m6800_python.__main__ import main


def test_load_a_binary_and_step(tmp_path, capsys) -> None:
    program = tmp_path / "program.bin"
    program.write_bytes(bytes([0x86, 0x2A, 0x4C, 0x20, 0xFE]))
    main(["--load", f"{program}@1000", "--pc", "1000", "-c", "step 2", "-c", "r", "--batch"])
    out = capsys.readouterr().out
    assert "> 1000  86 2A       LDAA #$2A" in out
    assert "A=2B" in out


def test_load_from_a_zip_and_reset(tmp_path, capsys) -> None:
    rom = bytearray(0x800)
    rom[-2:] = b"\xf8\x00"  # reset vector -> $F800
    rom[0:2] = b"\x20\xfe"  # BRA *
    archive = tmp_path / "game.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("rom.bin", bytes(rom))
    main(["--part", "6803", "--zip", f"{archive}:rom.bin@F800", "--reset", "--batch"])
    out = capsys.readouterr().out
    assert "PC=F800" in out and "D=0000" in out and "BRA $F800" in out


def test_bad_specs_are_explained(tmp_path) -> None:
    with pytest.raises(SystemExit, match="FILE@ADDRESS"):
        main(["--load", "nowhere.bin", "--batch"])
    big = tmp_path / "big.bin"
    big.write_bytes(bytes(0x200))
    with pytest.raises(SystemExit, match="do not fit"):
        main(["--load", f"{big}@FF00", "--batch"])
