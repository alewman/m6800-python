"""Branches, jumps, subroutine calls and the stack (M68PRM pp. A-9..A-25, A-43,
A-44, A-52, A-53, A-57; M6801RM pp. A-28, A-63, A-65)."""

from __future__ import annotations

import pytest
from conftest import make

N, Z, V, C = 0x08, 0x04, 0x02, 0x01

# opcode: the manual's branch condition over N, Z, V, C
CONDITIONS = {
    0x20: lambda n, z, v, c: True,  # BRA
    0x22: lambda n, z, v, c: not (c or z),  # BHI
    0x23: lambda n, z, v, c: bool(c or z),  # BLS
    0x24: lambda n, z, v, c: not c,  # BCC
    0x25: lambda n, z, v, c: bool(c),  # BCS
    0x26: lambda n, z, v, c: not z,  # BNE
    0x27: lambda n, z, v, c: bool(z),  # BEQ
    0x28: lambda n, z, v, c: not v,  # BVC
    0x29: lambda n, z, v, c: bool(v),  # BVS
    0x2A: lambda n, z, v, c: not n,  # BPL
    0x2B: lambda n, z, v, c: bool(n),  # BMI
    0x2C: lambda n, z, v, c: n == v,  # BGE
    0x2D: lambda n, z, v, c: n != v,  # BLT
    0x2E: lambda n, z, v, c: not z and n == v,  # BGT
    0x2F: lambda n, z, v, c: bool(z) or n != v,  # BLE
}


@pytest.mark.parametrize("opcode", sorted(CONDITIONS), ids=lambda op: f"{op:02X}")
def test_branch_conditions_and_targets(part: str, opcode: int) -> None:
    for flags in range(16):
        n, z, v, c = bool(flags & N), bool(flags & Z), bool(flags & V), bool(flags & C)
        for offset, target in ((0x10, 0x1012), (0xFE, 0x1000), (0x80, 0x0F82), (0x7F, 0x1081)):
            cpu, _ = make(part, [opcode, offset])
            cpu.CC = 0xC0 | flags
            cycles = cpu.step()
            taken = CONDITIONS[opcode](n, z, v, c)
            assert cpu.PC == (target if taken else 0x1002)
            assert cycles == (4 if part == "6800" else 3)  # taken or not
            assert cpu.CC == 0xC0 | flags


def test_brn_never_branches_on_the_6803() -> None:
    cpu, _ = make("6803", [0x21, 0x40])
    assert cpu.step() == 3
    assert cpu.PC == 0x1002


def test_branch_wraps_around_the_address_space(part: str) -> None:
    cpu, _ = make(part, [0x20, 0x10], at=0xFFF0)
    cpu.step()
    assert cpu.PC == 0x0002


def test_bsr_pushes_the_return_address_low_byte_first(part: str) -> None:
    cpu, bus = make(part, [0x8D, 0x20])
    cpu.SP = 0xEFFF
    cycles = cpu.step()
    assert cycles == (8 if part == "6800" else 6)
    assert cpu.PC == 0x1022
    assert cpu.SP == 0xEFFD
    assert bus.writes() == [(0xEFFF, 0x02), (0xEFFE, 0x10)]  # PCL, then PCH


def test_jsr_extended_matches_the_manual_example(part: str) -> None:
    # M68PRM p. A-44: JSR CHARLI at $0FFF, SP $EFFF -> PC $2077, stack 10 02.
    cpu, bus = make(part, [0xBD, 0x20, 0x77], at=0x0FFF)
    cpu.SP = 0xEFFF
    cpu.step()
    assert cpu.PC == 0x2077 and cpu.SP == 0xEFFD
    assert bus.memory[0xEFFE] == 0x10 and bus.memory[0xEFFF] == 0x02


def test_jsr_indexed_and_direct(part: str) -> None:
    cpu, bus = make(part, [0xAD, 0x05])
    cpu.X = 0x3000
    cpu.step()
    assert cpu.PC == 0x3005 and bus.word(cpu.SP + 1) == 0x1002
    if part == "6803":
        cpu, bus = make(part, [0x9D, 0x40])
        assert cpu.step() == 5
        assert cpu.PC == 0x0040 and bus.word(cpu.SP + 1) == 0x1002


def test_rts_matches_the_manual_example(part: str) -> None:
    # M68PRM p. A-57: SP $EFFD, stack 10 02 -> PC $1002, SP $EFFF.
    cpu, bus = make(part, [0x39], at=0x30A2)
    cpu.SP = 0xEFFD
    bus.load(0xEFFE, [0x10, 0x02])
    assert cpu.step() == 5
    assert cpu.PC == 0x1002 and cpu.SP == 0xEFFF


def test_jmp(part: str) -> None:
    cpu, _ = make(part, [0x7E, 0xAB, 0xCD])
    assert cpu.step() == 3 and cpu.PC == 0xABCD
    cpu, _ = make(part, [0x6E, 0x10])
    cpu.X = 0x2000
    cpu.step()
    assert cpu.PC == 0x2010


def test_psh_pul_order_and_stack_pointer(part: str) -> None:
    cpu, bus = make(part, [0x36, 0x37, 0x32, 0x33])  # PSHA PSHB PULA PULB
    cpu.A, cpu.B, cpu.SP = 0x11, 0x22, 0x0200
    cpu.step()
    cpu.step()
    assert bus.writes() == [(0x0200, 0x11), (0x01FF, 0x22)]
    assert cpu.SP == 0x01FE
    cpu.step()
    cpu.step()
    assert (cpu.A, cpu.B, cpu.SP) == (0x22, 0x11, 0x0200)


def test_pshx_pushes_low_byte_first_and_pulx_restores() -> None:
    cpu, bus = make("6803", [0x3C, 0xCE, 0x00, 0x00, 0x38])  # PSHX LDX #0 PULX
    cpu.X, cpu.SP = 0xBEEF, 0x0200
    assert cpu.step() == 4
    assert bus.writes() == [(0x0200, 0xEF), (0x01FF, 0xBE)]  # IXL, then IXH
    assert bus.word(0x01FF) == 0xBEEF  # so memory reads high:low upwards
    cpu.step()
    assert cpu.X == 0
    assert cpu.step() == 5
    assert cpu.X == 0xBEEF and cpu.SP == 0x0200


def test_tsx_txs_ins_des(part: str) -> None:
    cpu, _ = make(part, [0x30, 0x35, 0x31, 0x34])
    cpu.SP = 0x01F0
    cpu.step()
    assert cpu.X == 0x01F1  # TSX: X <- SP + 1
    cpu.X = 0x0400
    cpu.step()
    assert cpu.SP == 0x03FF  # TXS: SP <- X - 1
    cpu.step()
    assert cpu.SP == 0x0400
    cpu.step()
    assert cpu.SP == 0x03FF


def test_inx_dex_touch_only_z(part: str) -> None:
    cpu, _ = make(part, [0x08, 0x09, 0x09])
    cpu.X, cpu.CC = 0xFFFF, 0xC0 | N | V | C
    cpu.step()
    assert cpu.X == 0 and cpu.CC == 0xC0 | N | V | C | Z
    cpu.step()
    assert cpu.X == 0xFFFF and cpu.CC == 0xC0 | N | V | C


def test_ldx_stx_lds_sts_flags(part: str) -> None:
    cpu, bus = make(part, [0xCE, 0x80, 0x00, 0xFF, 0x20, 0x00, 0x8E, 0x00, 0x00, 0xBF, 0x20, 0x02])
    cpu.CC = 0xC0 | V | C
    cpu.step()
    assert cpu.X == 0x8000 and cpu.CC == 0xC0 | N | C  # V cleared, C kept
    cpu.step()
    assert bus.word(0x2000) == 0x8000
    cpu.step()
    assert cpu.SP == 0 and cpu.CC == 0xC0 | Z | C
    cpu.step()
    assert bus.word(0x2002) == 0
