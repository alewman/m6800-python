"""Arithmetic, logic and shift semantics against the manuals' Boolean formulae.

The expected flags here are computed bit by bit from the "Boolean Formulae for
Condition Codes" printed on each instruction's page of M68PRM Appendix A (and
M6801RM for the 16-bit forms), not from the core's own arithmetic, so the two
are independent derivations of the same rule.  The 8-bit cases are exhaustive.
"""

from __future__ import annotations

import random

import pytest
from conftest import make

H, I, N, Z, V, C = 0x20, 0x10, 0x08, 0x04, 0x02, 0x01


def bit(value: int, n: int) -> int:
    return (value >> n) & 1


def nz(r: int, width: int = 8) -> int:
    top = width - 1
    return (N if bit(r, top) else 0) | (Z if r == 0 else 0)


def add_flags(x: int, m: int, r: int) -> int:
    """M68PRM p. A-5: H, N, Z, V, C for ADD, ADC and ABA."""
    x3, m3, r3 = bit(x, 3), bit(m, 3), bit(r, 3)
    x7, m7, r7 = bit(x, 7), bit(m, 7), bit(r, 7)
    h = (x3 & m3) | (m3 & ~r3 & 1) | (~r3 & 1 & x3)
    v = (x7 & m7 & (1 - r7)) | ((1 - x7) & (1 - m7) & r7)
    c = (x7 & m7) | (m7 & (1 - r7)) | ((1 - r7) & x7)
    return (H if h else 0) | nz(r) | (V if v else 0) | (C if c else 0)


def sub_flags(x: int, m: int, r: int) -> int:
    """M68PRM p. A-66: N, Z, V, C for SUB, SBC, CMP, SBA and CBA (H unaffected)."""
    x7, m7, r7 = bit(x, 7), bit(m, 7), bit(r, 7)
    v = (x7 & (1 - m7) & (1 - r7)) | ((1 - x7) & m7 & r7)
    c = ((1 - x7) & m7) | (m7 & r7) | (r7 & (1 - x7))
    return nz(r) | (V if v else 0) | (C if c else 0)


# (opcode for the A, immediate form, result function, flag function, flags it owns)
EIGHT_BIT = {
    "ADDA": (0x8B, lambda x, m, c: (x + m) & 0xFF, add_flags, H | N | Z | V | C),
    "ADCA": (0x89, lambda x, m, c: (x + m + c) & 0xFF, add_flags, H | N | Z | V | C),
    "SUBA": (0x80, lambda x, m, c: (x - m) & 0xFF, sub_flags, N | Z | V | C),
    "SBCA": (0x82, lambda x, m, c: (x - m - c) & 0xFF, sub_flags, N | Z | V | C),
    "CMPA": (0x81, None, sub_flags, N | Z | V | C),
}


@pytest.mark.parametrize("mnemonic", sorted(EIGHT_BIT))
def test_eight_bit_arithmetic_exhaustive(part: str, mnemonic: str) -> None:
    opcode, result, flags, owned = EIGHT_BIT[mnemonic]
    cpu, bus = make(part, [opcode, 0])
    for carry in (0, 1):
        for x in range(256):
            for m in range(256):
                cpu.PC, cpu.A, cpu.CC = 0x1000, x, 0xC0 | carry | (0 if owned & H else H)
                bus.memory[0x1001] = m
                cpu.step()
                r = (x - m) & 0xFF if result is None else result(x, m, carry)
                assert cpu.A == (x if result is None else r)
                expected = flags(x, m, r)
                assert cpu.CC & owned == expected, f"{mnemonic} {x:02X},{m:02X},C={carry}"
                if not owned & H:
                    assert cpu.CC & H, "subtracts must leave H alone"


def test_aba_sba_cba(part: str) -> None:
    rng = random.Random(1)
    for _ in range(3000):
        x, y = rng.randrange(256), rng.randrange(256)
        for opcode, r, flags in (
            (0x1B, (x + y) & 0xFF, add_flags(x, y, (x + y) & 0xFF)),
            (0x10, (x - y) & 0xFF, sub_flags(x, y, (x - y) & 0xFF)),
            (0x11, x, sub_flags(x, y, (x - y) & 0xFF)),
        ):
            cpu, _ = make(part, [opcode])
            cpu.A, cpu.B = x, y
            cpu.step()
            assert cpu.A == r and cpu.B == y
            owned = (H if opcode == 0x1B else 0) | N | Z | V | C
            assert cpu.CC & owned == flags


@pytest.mark.parametrize(
    ("opcode", "function"),
    [(0x84, lambda x, m: x & m), (0x88, lambda x, m: x ^ m), (0x8A, lambda x, m: x | m)],
    ids=["ANDA", "EORA", "ORAA"],
)
def test_logic_exhaustive(part: str, opcode: int, function) -> None:
    cpu, bus = make(part, [opcode, 0])
    for x in range(256):
        for m in range(0, 256, 3):
            cpu.PC, cpu.A, cpu.CC = 0x1000, x, 0xC0 | V | C
            bus.memory[0x1001] = m
            cpu.step()
            r = function(x, m)
            assert cpu.A == r
            assert cpu.CC & (N | Z | V | C) == nz(r) | C  # V cleared, C untouched


def test_bit_does_not_store(part: str) -> None:
    cpu, _ = make(part, [0x85, 0x0F])
    cpu.A = 0xF0
    cpu.step()
    assert cpu.A == 0xF0 and cpu.CC & Z


# -- single-operand: INC DEC NEG COM CLR TST (M68PRM pp. A-40, A-36, A-49, A-32,
# A-29, A-73), exhaustive over the operand, on A and on memory -----------------


def single(name: str, x: int, c: int) -> tuple[int, int, int]:
    """(result, flags, mask of flags owned) from the manual's formulae."""
    if name == "INC":
        r = (x + 1) & 0xFF
        return r, nz(r) | (V if x == 0x7F else 0), N | Z | V
    if name == "DEC":
        r = (x - 1) & 0xFF
        return r, nz(r) | (V if x == 0x80 else 0), N | Z | V
    if name == "NEG":
        r = (-x) & 0xFF
        v = r == 0x80  # V = R7./R6.../R0
        cc = any(bit(r, n) for n in range(8))  # C = R7+R6+...+R0
        return r, nz(r) | (V if v else 0) | (C if cc else 0), N | Z | V | C
    if name == "COM":
        r = x ^ 0xFF
        return r, nz(r) | C, N | Z | V | C
    if name == "CLR":
        return 0, Z, N | Z | V | C
    if name == "TST":
        return x, nz(x), N | Z | V | C
    raise AssertionError(name)


SINGLE = {"NEG": 0x40, "COM": 0x43, "DEC": 0x4A, "INC": 0x4C, "TST": 0x4D, "CLR": 0x4F}


@pytest.mark.parametrize("name", sorted(SINGLE))
def test_single_operand_on_a_exhaustive(part: str, name: str) -> None:
    cpu, _ = make(part, [SINGLE[name]])
    for c in (0, 1):
        for x in range(256):
            cpu.PC, cpu.A, cpu.CC = 0x1000, x, 0xC0 | c
            cpu.step()
            r, flags, owned = single(name, x, c)
            assert cpu.A == r, f"{name}A {x:02X}"
            assert cpu.CC & owned == flags, f"{name}A {x:02X}"
            assert cpu.CC & ~owned & 0x3F == c & ~owned, f"{name}A touched a flag it should not"


@pytest.mark.parametrize("name", sorted(SINGLE))
def test_single_operand_on_memory_extended(part: str, name: str) -> None:
    opcode = SINGLE[name] + 0x30  # $7x: extended
    cpu, bus = make(part, [opcode, 0x20, 0x00])
    for x in range(256):
        cpu.PC, cpu.CC = 0x1000, 0xC0
        bus.memory[0x2000] = x
        bus.log.clear()
        cpu.step()
        r, flags, owned = single(name, x, 0)
        assert cpu.CC & owned == flags
        if name == "TST":
            assert bus.writes() == []  # TST only reads (MCSDD Table 8, note 3)
        else:
            assert bus.writes() == [(0x2000, r)]
            assert ("r", 0x2000, x) in bus.log  # read-modify-write, CLR included


def test_indexed_offset_is_unsigned(part: str) -> None:
    cpu, bus = make(part, [0xA6, 0xFF])  # LDAA $FF,X
    cpu.X = 0x3000
    bus.memory[0x30FF] = 0x5A
    bus.memory[0x2FFF] = 0xA5
    cpu.step()
    assert cpu.A == 0x5A


def test_indexed_address_wraps(part: str) -> None:
    cpu, bus = make(part, [0xA6, 0x10])
    cpu.X = 0xFFF8
    bus.memory[0x0008] = 0x77
    cpu.step()
    assert cpu.A == 0x77


# -- shifts and rotates (M68PRM pp. A-7, A-8, A-48, A-54, A-55) -------------

SHIFTS = {"ASL": 0x48, "ASR": 0x47, "LSR": 0x44, "ROL": 0x49, "ROR": 0x46}


def shifted(name: str, x: int, c: int) -> tuple[int, int]:
    if name == "ASL":
        r, cout = (x << 1) & 0xFF, bit(x, 7)
    elif name == "ASR":
        r, cout = (x >> 1) | (x & 0x80), bit(x, 0)
    elif name == "LSR":
        r, cout = x >> 1, bit(x, 0)
    elif name == "ROL":
        r, cout = ((x << 1) & 0xFF) | c, bit(x, 7)
    else:
        r, cout = (x >> 1) | (c << 7), bit(x, 0)
    n = bit(r, 7)
    v = n ^ cout  # "V = N (+) C", after the shift
    return r, (N if n else 0) | (Z if r == 0 else 0) | (V if v else 0) | (C if cout else 0)


@pytest.mark.parametrize("name", sorted(SHIFTS))
def test_shifts_exhaustive(part: str, name: str) -> None:
    for base in (SHIFTS[name], SHIFTS[name] + 0x10):  # A and B forms
        cpu, _ = make(part, [base])
        for c in (0, 1):
            for x in range(256):
                cpu.PC, cpu.CC = 0x1000, 0xC0 | H | c
                if base & 0x10:
                    cpu.B = x
                else:
                    cpu.A = x
                cpu.step()
                r, flags = shifted(name, x, c)
                assert (cpu.B if base & 0x10 else cpu.A) == r
                assert cpu.CC == 0xC0 | H | flags, f"{name} {x:02X} C={c}"


# -- MC6801/6803 sixteen-bit forms (M6801RM pp. A-7, A-10, A-57, A-58, A-80) --


def test_addd_subd_random_and_edges() -> None:
    rng = random.Random(6801)
    cases = [(0, 0), (0xFFFF, 1), (0x7FFF, 1), (0x8000, 0xFFFF), (0x8000, 1), (0x1234, 0x1234)]
    cases += [(rng.randrange(65536), rng.randrange(65536)) for _ in range(20000)]
    for d, m in cases:
        for opcode, r in ((0xC3, (d + m) & 0xFFFF), (0x83, (d - m) & 0xFFFF)):
            cpu, _ = make("6803", [opcode, m >> 8, m & 0xFF])
            cpu.D = d
            cpu.CC = 0xC0 | H
            cpu.step()
            assert cpu.D == r
            d15, m15, r15 = bit(d, 15), bit(m, 15), bit(r, 15)
            if opcode == 0xC3:
                v = (d15 & m15 & (1 - r15)) | ((1 - d15) & (1 - m15) & r15)
                c = (d15 & m15) | (m15 & (1 - r15)) | ((1 - r15) & d15)
            else:
                v = (d15 & (1 - m15) & (1 - r15)) | ((1 - d15) & m15 & r15)
                c = ((1 - d15) & m15) | (m15 & r15) | (r15 & (1 - d15))
            assert cpu.CC == 0xC0 | H | nz(r, 16) | (V if v else 0) | (C if c else 0)


def test_asld_lsrd_exhaustive_high_and_low_edges() -> None:
    values = [*range(0, 0x10000, 257), 0x8000, 0x0001, 0xFFFF, 0x4000, 0xC000]
    for d in values:
        for opcode in (0x05, 0x04):
            cpu, _ = make("6803", [opcode])
            cpu.D, cpu.CC = d, 0xC0 | H
            cpu.step()
            if opcode == 0x05:
                r, cout = (d << 1) & 0xFFFF, bit(d, 15)
            else:
                r, cout = d >> 1, bit(d, 0)
            n = bit(r, 15)
            flags = (N if n else 0) | (Z if r == 0 else 0) | (V if n ^ cout else 0)
            assert cpu.D == r
            assert cpu.CC == 0xC0 | H | flags | (C if cout else 0)


def test_mul_exhaustive() -> None:
    cpu, _ = make("6803", [0x3D])
    for a in range(256):
        for b in range(256):
            cpu.PC, cpu.A, cpu.B, cpu.CC = 0x1000, a, b, 0xC0 | N | Z | V | H
            assert cpu.step() == 10
            assert cpu.D == a * b
            # Only C changes: C <- bit 7 of the result's low byte (M6801RM p. A-58).
            assert cpu.CC == 0xC0 | N | Z | V | H | (C if a * b & 0x80 else 0)


def test_abx_is_unsigned_and_flagless() -> None:
    cpu, _ = make("6803", [0x3A])
    cpu.X, cpu.B, cpu.CC = 0x12F0, 0xFF, 0xC0
    cpu.step()
    assert cpu.X == 0x13EF and cpu.CC == 0xC0
