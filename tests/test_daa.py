"""DAA over all 256 A values x H x C (M68PRM pp. A-34, A-35; M6801RM p. A-40).

The manual defines DAA by a nine-row table over (C, upper nibble, H, lower
nibble) that covers exactly the states a BCD addition can leave behind.  Those
384 inputs are checked against the table.  The other 640 of the 1,024 inputs
are not specified by Motorola; for them the core follows MAME's rule, and the
test says so rather than pretending the manual covers them.
"""

from __future__ import annotations

from conftest import make

H, N, Z, V, C = 0x20, 0x08, 0x04, 0x02, 0x01

# (C before, upper nibble range, H before, lower nibble range, added, C after)
MANUAL_TABLE = [
    (0, (0x0, 0x9), 0, (0x0, 0x9), 0x00, 0),
    (0, (0x0, 0x8), 0, (0xA, 0xF), 0x06, 0),
    (0, (0x0, 0x9), 1, (0x0, 0x3), 0x06, 0),
    (0, (0xA, 0xF), 0, (0x0, 0x9), 0x60, 1),
    (0, (0x9, 0xF), 0, (0xA, 0xF), 0x66, 1),
    (0, (0xA, 0xF), 1, (0x0, 0x3), 0x66, 1),
    (1, (0x0, 0x2), 0, (0x0, 0x9), 0x60, 1),
    (1, (0x0, 0x2), 0, (0xA, 0xF), 0x66, 1),
    (1, (0x0, 0x3), 1, (0x0, 0x3), 0x66, 1),
]


def manual_row(a: int, h: int, c: int) -> tuple[int, int] | None:
    upper, lower = a >> 4, a & 0xF
    for c0, (u0, u1), h0, (l0, l1), added, c_after in MANUAL_TABLE:
        if c == c0 and h == h0 and u0 <= upper <= u1 and l0 <= lower <= l1:
            return added, c_after
    return None


def mame_rule(a: int, h: int, c: int) -> tuple[int, int]:
    """MAME 0.285's daa (6800ops.hxx), for inputs the manual leaves undefined."""
    correction = 0
    if (a & 0x0F) > 9 or h:
        correction |= 0x06
    if (a & 0xF0) > 0x80 and (a & 0x0F) > 9:
        correction |= 0x60
    if (a & 0xF0) > 0x90 or c:
        correction |= 0x60
    return correction, 1 if (c or a + correction > 0xFF) else 0


def run_daa(part: str, a: int, cc: int):
    cpu, _ = make(part, [0x19])
    cpu.A, cpu.CC = a, 0xC0 | cc
    assert cpu.step() == 2
    return cpu


def test_all_1024_inputs(part: str) -> None:
    covered = 0
    for a in range(256):
        for h in (0, 1):
            for c in (0, 1):
                cpu = run_daa(part, a, (H if h else 0) | (C if c else 0) | V)
                row = manual_row(a, h, c)
                if row is not None:
                    covered += 1
                added, c_after = row if row is not None else mame_rule(a, h, c)
                r = (a + added) & 0xFF
                assert cpu.A == r, f"A={a:02X} H={h} C={c}"
                assert bool(cpu.CC & C) == bool(c_after)
                assert bool(cpu.CC & N) == bool(r & 0x80)
                assert bool(cpu.CC & Z) == (r == 0)
                assert bool(cpu.CC & H) == bool(h)  # H not affected
                # V is "not defined" in both manuals; the core clears it, as MAME does.
                assert not cpu.CC & V
    assert covered == 384


def test_every_bcd_addition(part: str) -> None:
    """ADDA/ADCA of two BCD bytes then DAA gives the decimal sum and carry."""
    for carry_in in (0, 1):
        for x in range(100):
            for y in range(100):
                bx, by = int(str(x), 16), int(str(y), 16)
                cpu, _ = make(part, [0x89 if carry_in else 0x8B, by, 0x19])
                cpu.A, cpu.CC = bx, 0xC0 | carry_in
                cpu.step()
                cpu.step()
                total = x + y + carry_in
                assert cpu.A == int(f"{total % 100:02d}", 16), f"{x}+{y}+{carry_in}"
                assert bool(cpu.CC & C) == (total >= 100)
