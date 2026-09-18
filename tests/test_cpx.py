"""CPX: the one documented flag rule that differs between the parts.

MC6800 (M68PRM p. A-33): two byte compares.  Z = both byte results zero;
N = RH7 and V = IXH7./M7./RH7 + /IXH7.M7.RH7 from the high byte alone (no
borrow from the low byte); C not affected.  MC6801/6803 (M6801RM p. A-39): a
16-bit subtract setting N, Z, V and C.
"""

from __future__ import annotations

import random

from conftest import make

N, Z, V, C = 0x08, 0x04, 0x02, 0x01


def bit(value: int, n: int) -> int:
    return (value >> n) & 1


def mc6800_flags(x: int, m: int, c_before: int) -> int:
    xh, mh = x >> 8, m >> 8
    rh, rl = (xh - mh) & 0xFF, ((x & 0xFF) - (m & 0xFF)) & 0xFF
    v = (bit(xh, 7) & (1 - bit(mh, 7)) & (1 - bit(rh, 7))) | (
        (1 - bit(xh, 7)) & bit(mh, 7) & bit(rh, 7)
    )
    return (N if bit(rh, 7) else 0) | (Z if rh == rl == 0 else 0) | (V if v else 0) | c_before


def mc6801_flags(x: int, m: int) -> int:
    r = (x - m) & 0xFFFF
    x15, m15, r15 = bit(x, 15), bit(m, 15), bit(r, 15)
    v = (x15 & (1 - m15) & (1 - r15)) | ((1 - x15) & m15 & r15)
    c = ((1 - x15) & m15) | (m15 & r15) | (r15 & (1 - x15))
    return (N if r15 else 0) | (Z if r == 0 else 0) | (V if v else 0) | (C if c else 0)


def cases() -> list[tuple[int, int]]:
    rng = random.Random(0x8C)
    edges = [0x0000, 0x0001, 0x00FF, 0x0100, 0x7FFF, 0x8000, 0x80FF, 0xFFFF, 0x7F00, 0x8001]
    out = [(x, m) for x in edges for m in edges]
    out += [(rng.randrange(65536), rng.randrange(65536)) for _ in range(20000)]
    # High bytes equal but low bytes differ: the case where the parts disagree most.
    out += [(h << 8 | rng.randrange(256), h << 8 | rng.randrange(256)) for h in range(256)]
    return out


def test_mc6800_cpx() -> None:
    for x, m in cases():
        for c_before in (0, C):
            cpu, _ = make("6800", [0x8C, m >> 8, m & 0xFF])
            cpu.X, cpu.CC = x, 0xC0 | c_before
            assert cpu.step() == 3
            assert cpu.CC & 0x0F == mc6800_flags(x, m, c_before), f"X={x:04X} M={m:04X}"
            assert cpu.X == x


def test_mc6803_cpx() -> None:
    for x, m in cases():
        cpu, _ = make("6803", [0x8C, m >> 8, m & 0xFF])
        cpu.X, cpu.CC = x, 0xC0
        assert cpu.step() == 4
        assert cpu.CC & 0x0F == mc6801_flags(x, m), f"X={x:04X} M={m:04X}"


def test_the_manual_bhi_example_works_only_on_the_6803() -> None:
    # M6801RM section 4.3.3.3: LDX #$8000 / CPX #$7FFF / BHI HANG "will take branch".
    program = [0xCE, 0x80, 0x00, 0x8C, 0x7F, 0xFF, 0x22, 0x01, 0x01, 0x20, 0xFE]
    cpu, _ = make("6803", program)
    for _ in range(3):
        cpu.step()
    assert cpu.PC == 0x1009  # branched over the NOP to HANG
    # On the MC6800 CPX leaves C alone and the high-byte compare sets V, so the
    # outcome depends on the C left by LDX (unchanged) -- not a valid idiom.
    cpu, _ = make("6800", program)
    cpu.CC = 0xC0 | C
    for _ in range(3):
        cpu.step()
    assert cpu.PC == 0x1008
