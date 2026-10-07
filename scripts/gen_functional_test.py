"""Generate validation/functional_test.asm and validation/functional_test_6801.asm.

docs/handoff-polish.md's stretch item 8 asks for a self-checking MC6800
functional test program, in the spirit of Klaus Dormann's 6502 test: every
documented opcode exercised, each failing check landing at its own trap
address, success at a known PC with a known value in A.

Scope, stated plainly: this covers every documented *mnemonic* once (118 of
them: 107 shared with the MC6800, 11 that only the MC6801/6803 add), not
every opcode byte x addressing-mode combination. Mode and operand-value
exhaustiveness already exist at the unit level -- rung 1 (tests/datasheet.py,
the decode table itself) and rung 2 (scripts/mame_corpus.py, MAME's own
handlers single-stepped exhaustively) -- so repeating that here would not
raise this family's evidence ceiling. What raises it is being a single,
portable, *continuously executing* binary a real board can just run, which
is what this is. A few mnemonics whose correctness hinges on more than one
scenario (DAA's correction table, CPX's part-dependent carry) get more than
one check; that is a deliberate exception to "one case", not an oversight.

``WAI`` is the one documented opcode this program cannot exercise: it halts
the CPU until an interrupt arrives, and a freestanding ROM with no external
interrupt source has no self-contained way to supply one. That is a real
limit of what a CPU-only self-test can prove, not a tooling gap -- see
validation.md.

Every expected value here is computed from the independent Boolean-formula
functions in tests/test_alu.py (themselves transcribed from M68PRM/M6801RM
Appendix A, not from this core's own arithmetic) or, for DAA, from the
nine-row correction table in docs/start-here.md -- never by running the core
under test and recording what it did.

Run directly to regenerate both .asm files and their assembled .s19/.bin
siblings:

    python scripts/gen_functional_test.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_alu as oracle  # noqa: E402
import test_cpx as cpx_oracle  # noqa: E402
from asm6800 import Assembler, to_s19  # noqa: E402
from datasheet import DATASHEET  # noqa: E402

H, I, N, Z, V, C = oracle.H, oracle.I, oracle.N, oracle.Z, oracle.V, oracle.C
BITS = {"H": H, "I": I, "N": N, "Z": Z, "V": V, "C": C}
POSITIONS = "HINZVC"  # datasheet flags-string column order

MODES: dict[str, dict[str, tuple[int, int]]] = {}
for _opcode, _entry in DATASHEET.items():
    MODES.setdefault(_entry.mnemonic, {})[_entry.mode] = (_opcode, _entry.length)

ORIGIN_SYMBOL = "ORIGIN"
SCRATCH = "SCRATCH"  # one direct-page byte (two, for a 16-bit memory operand)
SAVE = "SAVE"  # two direct-page bytes, for stack round-trip checks


def cc(h: int = 1, i: int = 1, n: int = 0, z: int = 0, v: int = 0, c: int = 0) -> int:
    return (h << 5) | (i << 4) | (n << 3) | (z << 2) | (v << 1) | c


@dataclass
class Writer:
    lines: list[str] = field(default_factory=list)
    counter: int = 0
    covered: set[str] = field(default_factory=set)

    def raw(self, text: str = "") -> None:
        self.lines.append(text)

    def comment(self, text: str) -> None:
        self.raw(f"; {text}")

    def label(self, name: str) -> None:
        self.raw(f"{name}:")

    def insn(self, mnemonic: str, operand: str | None = None, *, label: str | None = None) -> None:
        prefix = f"{label}:" if label else ""
        if operand is None:
            self.raw(f"{prefix}\t{mnemonic}")
        else:
            self.raw(f"{prefix}\t{mnemonic} {operand}")

    def names(self) -> tuple[str, str]:
        self.counter += 1
        return f"OK{self.counter:03d}", f"FAIL{self.counter:03d}"

    def assert_a(self, expected: int) -> None:
        ok, fail = self.names()
        self.insn("CMPA", f"#${expected & 0xFF:02X}")
        self.insn("BEQ", ok)
        self.insn("BRA", fail, label=fail)
        self.label(ok)

    def assert_b(self, expected: int) -> None:
        ok, fail = self.names()
        self.insn("CMPB", f"#${expected & 0xFF:02X}")
        self.insn("BEQ", ok)
        self.insn("BRA", fail, label=fail)
        self.label(ok)

    def assert_x(self, expected: int) -> None:
        ok, fail = self.names()
        self.insn("CPX", f"#${expected & 0xFFFF:04X}")
        self.insn("BEQ", ok)
        self.insn("BRA", fail, label=fail)
        self.label(ok)

    def assert_x_mem(self, addr: str) -> None:
        ok, fail = self.names()
        self.insn("CPX", f"<{addr}")
        self.insn("BEQ", ok)
        self.insn("BRA", fail, label=fail)
        self.label(ok)

    def assert_mem8(self, addr: str, expected: int) -> None:
        self.insn("LDAA", f"<{addr}")
        self.assert_a(expected)

    def assert_mem16(self, addr: str, expected: int) -> None:
        self.insn("LDX", f"<{addr}")
        self.assert_x(expected)

    def assert_cc(self, flags: str, preset: int, bits: int) -> None:
        """``flags`` is a datasheet-style 6-char H I N Z V C string; ``bits`` is
        the OR of the CC-constant bits this specific case computed as set among
        the '*' positions (unset '*' positions are simply absent from ``bits``).
        A '-' position is checked against ``preset`` (must be left alone); a
        '0'/'1' position is checked against that literal; a '?' position is
        not checked at all.
        """
        mask = 0
        expected = 0
        for position, ch in zip(POSITIONS, flags, strict=True):
            bit = BITS[position]
            if ch == "?":
                continue
            mask |= bit
            if ch == "*":
                expected |= bits & bit
            elif ch == "0":
                pass
            elif ch == "1":
                expected |= bit
            elif ch == "-":
                expected |= preset & bit
            else:
                raise AssertionError(f"bad flags char {ch!r} in {flags!r}")
        ok, fail = self.names()
        self.insn("TPA")
        self.insn("ANDA", f"#${mask:02X}")
        self.insn("CMPA", f"#${expected & 0xFF:02X}")
        self.insn("BEQ", ok)
        self.insn("BRA", fail, label=fail)
        self.label(ok)

    def check_a_result(self, flags: str, preset: int, bits: int, expected: int) -> None:
        """Flags-then-value check when the op's result sits in A.

        ``assert_cc`` reads CC through TPA, which overwrites A; stash A on
        the stack across it (PSHA/PULA are both flags-transparent, '------')
        so the value check that follows sees the op's real result, not the
        flags byte.
        """
        self.insn("PSHA")
        self.assert_cc(flags, preset, bits)
        self.insn("PULA")
        self.assert_a(expected)

    def set_cc(self, value: int) -> None:
        self.insn("LDAA", f"#${value & 0x3F:02X}")
        self.insn("TAP")

    def check(self, mnemonic: str, text: str) -> None:
        self.covered.add(mnemonic)
        self.comment(text)


def nz(r: int, width: int = 8) -> int:
    return oracle.nz(r, width)


def sub16_flags(x: int, m: int, r: int) -> tuple[int, int, int]:
    """(bits, v, c) for a 16-bit subtract -- M6801RM pp. A-7/A-10's formula,
    transcribed from tests/test_alu.py's ``test_addd_subd_random_and_edges``.
    """
    x15, m15, r15 = oracle.bit(x, 15), oracle.bit(m, 15), oracle.bit(r, 15)
    v = (x15 & (1 - m15) & (1 - r15)) | ((1 - x15) & m15 & r15)
    c = ((1 - x15) & m15) | (m15 & r15) | (r15 & (1 - x15))
    return nz(r, 16) | (V if v else 0) | (C if c else 0), v, c


def add16_flags(x: int, m: int, r: int) -> int:
    x15, m15, r15 = oracle.bit(x, 15), oracle.bit(m, 15), oracle.bit(r, 15)
    v = (x15 & m15 & (1 - r15)) | ((1 - x15) & (1 - m15) & r15)
    c = (x15 & m15) | (m15 & (1 - r15)) | ((1 - r15) & x15)
    return nz(r, 16) | (V if v else 0) | (C if c else 0)


def daa_result(a: int, h: int, c: int) -> tuple[int, int]:
    """(result, carry-out) -- docs/start-here.md's nine-row table, M68PRM A-34/A-35."""
    low, high = a & 0x0F, a & 0xF0
    cf = 0
    if low > 9 or h:
        cf |= 0x06
    if high > 0x80 and low > 9:
        cf |= 0x60
    if high > 0x90 or c:
        cf |= 0x60
    result = (a + cf) & 0xFF
    carry_out = 1 if (a + cf) > 0xFF else 0
    return result, c | carry_out


def flags_for(mnemonic: str, part: str = "6800") -> str:
    entries = [e for e in DATASHEET.values() if e.mnemonic == mnemonic]
    flags = entries[0].flags_6800 if part == "6800" else entries[0].flags_6801
    assert flags is not None, f"{mnemonic} has no documented flags for part {part}"
    return flags


# -- 8-bit ALU, register op immediate-operand M: ADD/ADC/SUB/SBC, A and B ----


def gen_add_sub(w: Writer, part: str) -> None:
    cases = [
        ("ADDA", "A", oracle.add_flags, lambda x, m, c: (x + m) & 0xFF, 0x3F, 0x3C, 0),
        ("ADCA", "A", oracle.add_flags, lambda x, m, c: (x + m + c) & 0xFF, 0x01, 0x01, 1),
        ("SUBA", "A", oracle.sub_flags, lambda x, m, c: (x - m) & 0xFF, 0x10, 0x20, 0),
        ("SBCA", "A", oracle.sub_flags, lambda x, m, c: (x - m - c) & 0xFF, 0x10, 0x0F, 1),
        ("ADDB", "B", oracle.add_flags, lambda x, m, c: (x + m) & 0xFF, 0x7F, 0x02, 0),
        ("ADCB", "B", oracle.add_flags, lambda x, m, c: (x + m + c) & 0xFF, 0x7E, 0x01, 1),
        ("SUBB", "B", oracle.sub_flags, lambda x, m, c: (x - m) & 0xFF, 0x80, 0x01, 0),
        ("SBCB", "B", oracle.sub_flags, lambda x, m, c: (x - m - c) & 0xFF, 0x80, 0x00, 1),
    ]
    for mnemonic, reg, formula, result_fn, x, m, cin in cases:
        r = result_fn(x, m, cin)
        preset = 0x3F if cin else 0x3E  # a carry-consuming op needs C=cin going in
        w.check(mnemonic, f"{mnemonic} #${x:02X} + #${m:02X} (+C={cin}) = ${r:02X}")
        w.set_cc(preset)
        w.insn(f"LDA{reg}", f"#${x:02X}")
        w.insn(mnemonic, f"#${m:02X}")
        flags = flags_for(mnemonic, part)
        if reg == "A":
            w.check_a_result(flags, preset, formula(x, m, r), r)
        else:
            w.assert_cc(flags, preset, formula(x, m, r))
            w.assert_b(r)


def gen_cmp_bit(w: Writer, part: str) -> None:
    for mnemonic, reg, x, m in (
        ("CMPA", "A", 0x50, 0x30),
        ("CMPB", "B", 0x18, 0x19),
        ("BITA", "A", 0xF0, 0x0F),
        ("BITB", "B", 0xAA, 0x55),
    ):
        w.check(mnemonic, f"{mnemonic} #${x:02X},#${m:02X} (flags only, A/B unchanged)")
        w.set_cc(0x3F)
        w.insn(f"LDA{reg}", f"#${x:02X}")
        w.insn(mnemonic, f"#${m:02X}")
        flags = flags_for(mnemonic, part)
        if mnemonic.startswith("CMP"):
            r = (x - m) & 0xFF
            bits = oracle.sub_flags(x, m, r)
        else:
            bits = nz(x & m)
        # BITA/BITB/CMPA/CMPB never store: the register must still read x.
        if reg == "A":
            w.check_a_result(flags, 0x3F, bits, x)
        else:
            w.assert_cc(flags, 0x3F, bits)
            w.assert_b(x)


def gen_logic(w: Writer, part: str) -> None:
    for mnemonic, reg, fn, x, m in (
        ("ANDA", "A", lambda a, b: a & b, 0xF0, 0x3C),
        ("ANDB", "B", lambda a, b: a & b, 0x0F, 0xC3),
        ("ORAA", "A", lambda a, b: a | b, 0x40, 0x01),
        ("ORAB", "B", lambda a, b: a | b, 0x80, 0x01),
        ("EORA", "A", lambda a, b: a ^ b, 0xFF, 0x0F),
        ("EORB", "B", lambda a, b: a ^ b, 0xAA, 0xFF),
    ):
        r = fn(x, m)
        w.check(mnemonic, f"{mnemonic} #${x:02X},#${m:02X} = ${r:02X}")
        w.set_cc(0x3F)
        w.insn(f"LDA{reg}", f"#${x:02X}")
        w.insn(mnemonic, f"#${m:02X}")
        flags = flags_for(mnemonic, part)
        if reg == "A":
            w.check_a_result(flags, 0x3F, nz(r), r)
        else:
            w.assert_cc(flags, 0x3F, nz(r))
            w.assert_b(r)


def gen_aba_sba_cba(w: Writer, part: str) -> None:
    x, y = 0x3C, 0x45
    for mnemonic in ("ABA", "SBA", "CBA"):
        w.check(mnemonic, f"{mnemonic} A=${x:02X} B=${y:02X}")
        w.set_cc(0x3F)
        w.insn("LDAA", f"#${x:02X}")
        w.insn("LDAB", f"#${y:02X}")
        w.insn(mnemonic)
        flags = flags_for(mnemonic, part)
        if mnemonic == "ABA":
            r = (x + y) & 0xFF
            w.check_a_result(flags, 0x3F, oracle.add_flags(x, y, r), r)
        elif mnemonic == "SBA":
            r = (x - y) & 0xFF
            w.check_a_result(flags, 0x3F, oracle.sub_flags(x, y, r), r)
        else:
            r = (x - y) & 0xFF
            w.check_a_result(flags, 0x3F, oracle.sub_flags(x, y, r), x)  # CBA does not store
        w.assert_b(y)


# -- single-operand: NEG/COM/DEC/INC/TST/CLR, on A, on B, and on memory -----


def gen_single_operand(w: Writer, part: str) -> None:
    for family in ("NEG", "COM", "DEC", "INC", "TST", "CLR"):
        x = {"NEG": 0x80, "COM": 0x3C, "DEC": 0x01, "INC": 0x7F, "TST": 0x00, "CLR": 0x55}[family]
        for suffix, reg in (("A", "A"), ("B", "B"), ("", None)):
            mnemonic = family + suffix
            r, bits, _owned = oracle.single(family, x, 0)
            w.check(mnemonic, f"{mnemonic} ${x:02X} = ${r:02X}")
            w.set_cc(0x3F)
            flags = flags_for(mnemonic, part)
            if reg == "A":
                w.insn("LDAA", f"#${x:02X}")
                w.insn(mnemonic)
                w.check_a_result(flags, 0x3F, bits, r)
            elif reg == "B":
                w.insn("LDAB", f"#${x:02X}")
                w.insn(mnemonic)
                w.assert_cc(flags, 0x3F, bits)
                w.assert_b(r)
            else:
                w.insn("LDAA", f"#${x:02X}")
                w.insn("STAA", f"<{SCRATCH}")
                w.insn(mnemonic, f">{SCRATCH}")
                w.assert_cc(flags, 0x3F, bits)
                w.assert_mem8(SCRATCH, x if family == "TST" else r)  # TST only reads


def gen_shifts(w: Writer, part: str) -> None:
    for family in ("ASL", "ASR", "LSR", "ROL", "ROR"):
        x, cin = 0xB4, 1
        preset = cc(n=1, z=1, v=1, c=cin)
        for suffix, reg in (("A", "A"), ("B", "B"), ("", None)):
            mnemonic = family + suffix
            r, bits = oracle.shifted(family, x, cin)
            w.check(mnemonic, f"{mnemonic} ${x:02X} (Cin={cin}) = ${r:02X}")
            w.set_cc(preset)
            flags = flags_for(mnemonic, part)
            if reg == "A":
                w.insn("LDAA", f"#${x:02X}")
                w.insn(mnemonic)
                w.check_a_result(flags, preset, bits, r)
            elif reg == "B":
                w.insn("LDAB", f"#${x:02X}")
                w.insn(mnemonic)
                w.assert_cc(flags, preset, bits)
                w.assert_b(r)
            else:
                w.insn("LDAA", f"#${x:02X}")
                w.insn("STAA", f"<{SCRATCH}")
                w.insn(mnemonic, f">{SCRATCH}")
                w.assert_cc(flags, preset, bits)
                w.assert_mem8(SCRATCH, r)


# -- loads and stores: LDAA/LDAB/LDX/LDS(+LDD 6801), STAA/STAB/STX/STS(+STD) -


def gen_loads(w: Writer, part: str) -> None:
    for mnemonic, value in (
        ("LDAA", 0x92),
        ("LDAB", 0x6D),
        ("LDX", 0x8001),
        ("LDS", 0x0150),
    ):
        w.check(mnemonic, f"{mnemonic} #${value:04X}")
        w.set_cc(0x3F)
        width = 16 if mnemonic in ("LDX", "LDS") else 8
        digits = 4 if width == 16 else 2
        w.insn(mnemonic, f"#${value:0{digits}X}")
        flags = flags_for(mnemonic, part)
        if mnemonic == "LDAA":
            w.check_a_result(flags, 0x3F, nz(value, width), value)
            continue
        w.assert_cc(flags, 0x3F, nz(value, width))
        if mnemonic == "LDAB":
            w.assert_b(value)
        elif mnemonic == "LDX":
            w.assert_x(value)
        else:  # LDS: round-trip through TSX to read it back
            w.insn("TSX")
            w.assert_x((value + 1) & 0xFFFF)


def gen_stores(w: Writer, part: str) -> None:
    for mnemonic, reg, value in (
        ("STAA", "A", 0x92),
        ("STAB", "B", 0x6D),
        ("STX", "X", 0x8001),
        ("STS", "S", 0x0150),
    ):
        w.check(mnemonic, f"{mnemonic} ${value:04X} -> {SCRATCH}")
        w.set_cc(0x3F)
        width = 16 if mnemonic in ("STX", "STS") else 8
        if mnemonic == "STS":
            w.insn("LDS", f"#${value:04X}")
        elif reg in ("A", "B"):
            w.insn(f"LDA{reg}", f"#${value:02X}")
        else:
            w.insn("LDX", f"#${value:04X}")
        w.insn(mnemonic, f"<{SCRATCH}")
        flags = flags_for(mnemonic, part)
        w.assert_cc(flags, 0x3F, nz(value, width))
        if width == 8:
            w.assert_mem8(SCRATCH, value)
        else:
            w.assert_mem16(SCRATCH, value)


# -- CPX: N/Z/V shared with the 6800; the 6801 also sets C -------------------


def gen_cpx(w: Writer, part: str) -> None:
    # The MC6800 does NOT do a true 16-bit compare here: M68PRM p. A-33 gives
    # two 8-bit byte compares (N, V from the high byte alone; Z over both; C
    # left alone), while the MC6801/6803 do a true 16-bit compare and set C
    # too (M6801RM p. A-39) -- tests/test_cpx.py's docstring and its
    # ``mc6800_flags``/``mc6801_flags`` are this project's own independently-
    # settled oracles for the two algorithms. This file runs on *both* parts
    # from the same bytes, so x and m are chosen with no borrow across the
    # byte boundary (x > m, same high-byte sign, no low-byte borrow): under
    # those operands the two algorithms' N, Z and V agree, and C's true
    # 16-bit value (0, no borrow) matches the preset C left alone by the
    # 6800's reading of the same bits -- one case both parts actually agree
    # on, not a weakened check.
    x, m = 0x3000, 0x1000
    assert cpx_oracle.mc6800_flags(x, m, 0) == cpx_oracle.mc6801_flags(x, m) & (N | Z | V)
    bits = cpx_oracle.mc6800_flags(x, m, c_before=0)
    w.check("CPX", f"CPX X=${x:04X} #${m:04X} (6800 and 6801 algorithms agree here)")
    preset = cc(c=0)
    w.set_cc(preset)
    w.insn("LDX", f"#${x:04X}")
    w.insn("CPX", f"#${m:04X}")
    flags = flags_for("CPX", part)  # '-' for C on the 6800: checked against preset (0)
    w.assert_cc(flags, preset, bits)
    w.assert_x(x)  # CPX does not store


def gen_cpx_6801_carry(w: Writer) -> None:
    """The one case the 6800 file cannot make: a true 16-bit compare, C included."""
    x, m = 0x0001, 0x8000  # unsigned 1 < $8000: a borrow, so C=1
    bits = cpx_oracle.mc6801_flags(x, m)
    w.check("CPX", f"CPX (6801: true 16-bit) X=${x:04X} #${m:04X}")
    w.set_cc(0x3F)
    w.insn("LDX", f"#${x:04X}")
    w.insn("CPX", f"#${m:04X}")
    w.assert_cc("--****", 0x3F, bits)  # full 6801 flags, C included
    w.assert_x(x)


# -- DAA: the nine-row BCD correction table, three scenarios -----------------


def gen_daa(w: Writer, part: str) -> None:
    # (0x09, 1, 0) and (0x99, 0, 1), the table's more obvious corner cases,
    # are two of the six inputs on which sim68xx's own DAA is independently
    # known to disagree with the manual's table (docs/validation.md, rung 5:
    # "its DAA breaks the manual's table on 6 inputs"). This file is meant to
    # pass under sim68xx too, so these three were chosen by checking them
    # against a real sim68xx run first: C-forced correction alone, low-nibble
    # correction alone, and the combined low+high correction with a genuine
    # carry out -- three different table rows, none of them on sim68xx's
    # six-input exception list.
    for a, h, cin in ((0x12, 0, 1), (0x8A, 0, 0), (0x9A, 0, 0)):
        r, cout = daa_result(a, h, cin)
        w.check("DAA", f"DAA A=${a:02X} H={h} Cin={cin} -> ${r:02X} Cout={cout}")
        preset = cc(h=h, c=cin)
        w.set_cc(preset)
        w.insn("LDAA", f"#${a:02X}")  # LDAA leaves H and C alone (flags '--**0-')
        w.insn("DAA")
        flags = flags_for("DAA", part)  # '--**?*': V undefined, not tested
        w.check_a_result(flags, preset, nz(r) | (C if cout else 0), r)


# -- MUL and ABX (6801-only) --------------------------------------------------


def gen_mul(w: Writer) -> None:
    a, b = 0x19, 0xEF
    d = a * b
    w.check("MUL", f"MUL ${a:02X} * ${b:02X} = ${d:04X}")
    tap_preset = 0x3F
    w.set_cc(tap_preset)
    w.insn("LDAA", f"#${a:02X}")
    w.insn("LDAB", f"#${b:02X}")
    # LDAB's own flags ('--**0-') are the last word on N, Z, V before MUL
    # (flags '-----*'); H, I and C still carry over from tap_preset.
    preset = (nz(b) & (N | Z)) | (tap_preset & ~(N | Z | V) & 0x3F)
    w.insn("MUL")
    w.check_a_result("-----*", preset, C if d & 0x80 else 0, (d >> 8) & 0xFF)
    w.assert_b(d & 0xFF)


def gen_abx(w: Writer) -> None:
    x, b = 0x12F0, 0xFF
    r = (x + b) & 0xFFFF
    w.check("ABX", f"ABX X=${x:04X} + B=${b:02X} = ${r:04X}")
    tap_preset = 0x3F
    w.set_cc(tap_preset)
    w.insn("LDX", f"#${x:04X}")
    w.insn("LDAB", f"#${b:02X}")
    # LDAB's own flags are the last word on N, Z, V before ABX (flags
    # '------': every bit must match whatever was there going in).
    preset = (nz(b) & (N | Z)) | (tap_preset & ~(N | Z | V) & 0x3F)
    w.insn("ABX")
    w.assert_cc("------", preset, 0)
    w.assert_x(r)


def gen_addd_subd(w: Writer) -> None:
    for mnemonic, d, m in (("ADDD", 0x7FFF, 0x0001), ("SUBD", 0x8000, 0x0001)):
        r = (d + m) & 0xFFFF if mnemonic == "ADDD" else (d - m) & 0xFFFF
        w.check(mnemonic, f"{mnemonic} D=${d:04X} #${m:04X} = ${r:04X}")
        w.set_cc(0x3F)
        w.insn("LDAA", f"#${d >> 8:02X}")
        w.insn("LDAB", f"#${d & 0xFF:02X}")
        w.insn(mnemonic, f"#${m:04X}")
        flags = flags_for(mnemonic, "6801")
        bits = add16_flags(d, m, r) if mnemonic == "ADDD" else sub16_flags(d, m, r)[0]
        w.check_a_result(flags, 0x3F, bits, (r >> 8) & 0xFF)
        w.assert_b(r & 0xFF)


def gen_asld_lsrd(w: Writer) -> None:
    for mnemonic, d, cin in (("ASLD", 0xC001, 1), ("LSRD", 0x8001, 1)):
        if mnemonic == "ASLD":
            r, cout = (d << 1) & 0xFFFF, oracle.bit(d, 15)
        else:
            r, cout = d >> 1, oracle.bit(d, 0)
        n = oracle.bit(r, 15)
        flags_bits = (N if n else 0) | (Z if r == 0 else 0) | (V if n ^ cout else 0)
        w.check(mnemonic, f"{mnemonic} D=${d:04X} = ${r:04X}")
        preset = cc(c=cin)
        w.set_cc(preset)
        w.insn("LDAA", f"#${d >> 8:02X}")
        w.insn("LDAB", f"#${d & 0xFF:02X}")
        w.insn(mnemonic)
        flags = flags_for(mnemonic, "6801")
        w.check_a_result(flags, preset, flags_bits | (C if cout else 0), (r >> 8) & 0xFF)
        w.assert_b(r & 0xFF)


def gen_ldd_std(w: Writer) -> None:
    value = 0x8001
    w.check("LDD", f"LDD #${value:04X}")
    w.set_cc(0x3F)
    w.insn("LDD", f"#${value:04X}")
    w.check_a_result(flags_for("LDD", "6801"), 0x3F, nz(value, 16), (value >> 8) & 0xFF)
    w.assert_b(value & 0xFF)

    w.check("STD", f"STD ${value:04X} -> {SCRATCH}")
    w.set_cc(0x3F)
    w.insn("LDD", f"#${value:04X}")
    w.insn("STD", f"<{SCRATCH}")
    w.assert_cc(flags_for("STD", "6801"), 0x3F, nz(value, 16))
    w.assert_mem16(SCRATCH, value)


def gen_brn(w: Writer) -> None:
    w.check("BRN", "BRN never branches")
    w.set_cc(0x3F)
    taken, fall = w.names()
    w.insn("BRN", taken)
    w.label(fall)  # BRN must fall through to here, not to `taken`
    done = "BRN_DONE"
    w.insn("BRA", done)
    w.label(taken)
    w.insn("BRA", taken)  # trapped: BRN wrongly branched
    w.label(done)


def gen_pshx_pulx(w: Writer) -> None:
    value = 0x1234
    w.check("PSHX", "PSHX / PULX round-trip")
    w.check("PULX", "PSHX / PULX round-trip")
    w.set_cc(0x3F)
    w.insn("LDX", f"#${value:04X}")
    w.insn("PSHX")
    w.insn("LDX", "#$0000")
    w.insn("PULX")
    w.assert_x(value)


# -- control flow: branches, BSR/JSR/RTS, PSHA/PULA, PSHB/PULB, TSX/TXS,
#    INS/DES, TAP/TPA, SWI/RTI, NOP -----------------------------------------

# Each preset makes exactly the branch's documented condition true; H and I
# (irrelevant to every branch condition) stay at cc()'s default of 1.
BRANCHES_TAKEN = {
    "BCC": cc(c=0),  # C=0
    "BCS": cc(c=1),  # C=1
    "BEQ": cc(z=1),  # Z=1
    "BNE": cc(z=0),  # Z=0
    "BGE": cc(n=1, v=1),  # N^V=0
    "BGT": cc(n=1, v=1, z=0),  # N^V=0 and Z=0
    "BHI": cc(c=0, z=0),  # C=0 and Z=0
    "BLE": cc(z=1),  # Z=1 (satisfies N^V=1 OR Z=1 regardless of N,V)
    "BLS": cc(c=1),  # C=1 (satisfies C=1 OR Z=1 regardless of Z)
    "BLT": cc(n=1, v=0),  # N^V=1
    "BMI": cc(n=1),  # N=1
    "BPL": cc(n=0),  # N=0
    "BVC": cc(v=0),  # V=0
    "BVS": cc(v=1),  # V=1
}


def gen_branches(w: Writer) -> None:
    w.check("BRA", "BRA always branches")
    w.set_cc(0x00)
    taken, fail = w.names()
    w.insn("BRA", taken)
    w.insn("BRA", fail, label=fail)
    w.label(taken)

    for mnemonic, preset in sorted(BRANCHES_TAKEN.items()):
        w.check(mnemonic, f"{mnemonic} taken (CC=${preset:02X})")
        w.set_cc(preset)
        ok, fail = w.names()
        w.insn(mnemonic, ok)
        w.insn("BRA", fail, label=fail)
        w.label(ok)


def gen_bsr_jsr_rts(w: Writer) -> None:
    for mnemonic in ("BSR", "JSR"):
        w.check(mnemonic, f"{mnemonic} / RTS round-trip, SP preserved")
        w.check("RTS", f"{mnemonic} / RTS round-trip, SP preserved")
        over_label = f"OVER_{mnemonic}"
        sub_label = f"SUB_{mnemonic}"
        w.insn("TSX")
        w.insn("STX", f"<{SAVE}")
        if mnemonic == "BSR":
            w.insn("BSR", sub_label)
        else:
            w.insn("JSR", f">{sub_label}")
        w.insn("TSX")
        w.assert_x_mem(SAVE)
        w.insn("BRA", over_label)
        w.label(sub_label)
        w.insn("RTS")
        w.label(over_label)


def gen_jmp(w: Writer) -> None:
    w.check("JMP", "JMP extended")
    target = "JMP_TARGET"
    fail = "FAIL_JMP"
    w.insn("JMP", f">{target}")
    w.insn("BRA", fail, label=fail)
    w.label(target)


def gen_pairs(w: Writer) -> None:
    # PSHA/PULA
    w.check("PSHA", "PSHA / PULA round-trip")
    w.check("PULA", "PSHA / PULA round-trip")
    w.set_cc(0x3F)
    w.insn("LDAA", "#$5A")
    w.insn("PSHA")
    w.insn("CLRA")
    w.insn("PULA")
    w.assert_a(0x5A)

    # PSHB/PULB
    w.check("PSHB", "PSHB / PULB round-trip")
    w.check("PULB", "PSHB / PULB round-trip")
    w.insn("LDAB", "#$A5")
    w.insn("PSHB")
    w.insn("CLRB")
    w.insn("PULB")
    w.assert_b(0xA5)

    # TXS/TSX round trip
    w.check("TXS", "TXS / TSX round-trip")
    w.check("TSX", "TXS / TSX round-trip")
    w.insn("LDX", "#$0150")
    w.insn("TXS")
    w.insn("TSX")
    w.assert_x(0x0150)

    # INS/DES: two DES and one INS should net to SP-1
    w.check("DES", "DES DES INS nets to SP-1")
    w.check("INS", "DES DES INS nets to SP-1")
    w.insn("LDX", "#$0150")
    w.insn("TXS")
    w.insn("DES")
    w.insn("DES")
    w.insn("INS")
    w.insn("TSX")
    w.assert_x(0x014F)

    # TAP/TPA round trip
    w.check("TAP", "TAP / TPA round-trip")
    w.check("TPA", "TAP / TPA round-trip")
    w.insn("LDAA", "#$2D")
    w.insn("TAP")
    w.insn("TPA")
    w.assert_a(0x2D | 0xC0)

    # TAB/TBA round trip
    w.check("TAB", "TAB / TBA round-trip")
    w.check("TBA", "TAB / TBA round-trip")
    w.set_cc(0x3F)
    w.insn("LDAA", "#$7E")
    w.insn("TAB")
    w.assert_cc(flags_for("TAB"), 0x3F, nz(0x7E))
    w.assert_b(0x7E)
    w.set_cc(0x3F)  # assert_b's own CMPB just overwrote CC; TBA's check needs C=1 again
    w.insn("LDAA", "#$00")  # not CLRA: CLR forces C=0, which would spoil TBA's "C unaffected"
    w.insn("TBA")
    w.check_a_result(flags_for("TBA"), 0x3F, nz(0x7E), 0x7E)

    # CC single-bit setters/clearers
    for mnemonic, bit_const, want in (
        ("SEC", C, 1),
        ("CLC", C, 0),
        ("SEV", V, 1),
        ("CLV", V, 0),
        ("SEI", I, 1),
        ("CLI", I, 0),
    ):
        w.check(mnemonic, f"{mnemonic}")
        w.set_cc(0x3F if want else 0x00)
        w.insn(mnemonic)
        w.insn("TPA")
        w.insn("ANDA", f"#${bit_const:02X}")
        w.assert_a(bit_const if want else 0)

    # NOP: just confirm it doesn't disturb A or CC. LDAA's own flags
    # ('--**0-') replace N, Z and V as it loads $77 (N=Z=0 here); only H, I
    # and C survive from the $2A set just before it -- that combination,
    # not the pre-LDAA $2A itself, is what NOP must leave alone.
    w.check("NOP", "NOP changes nothing")
    tap_preset = 0x2A
    w.set_cc(tap_preset)
    w.insn("LDAA", "#$77")
    preset = (nz(0x77) & (N | Z)) | (tap_preset & ~(N | Z | V) & 0x3F)
    w.insn("NOP")
    w.check_a_result("------", preset, 0, 0x77)

    # INX/DEX -- check the flag INX/DEX itself set (via TPA) before CPX's own
    # comparison flags (from checking X's value) overwrite CC.
    w.check("INX", "INX sets Z on wraparound to 0")
    w.insn("LDX", "#$FFFF")
    w.insn("INX")
    w.insn("TPA")
    w.insn("ANDA", f"#${Z:02X}")
    w.assert_a(Z)
    w.assert_x(0x0000)

    w.check("DEX", "DEX sets Z landing on 0")
    w.insn("LDX", "#$0001")
    w.insn("DEX")
    w.insn("TPA")
    w.insn("ANDA", f"#${Z:02X}")
    w.assert_a(Z)
    w.assert_x(0x0000)


def gen_swi_rti(w: Writer) -> None:
    w.check("SWI", "SWI / RTI round-trip through the $FFFA/$FFFB vector")
    w.check("RTI", "SWI / RTI round-trip through the $FFFA/$FFFB vector")
    w.insn("LDX", "#$0150")
    w.insn("TXS")
    tap_preset = 0x2A
    w.set_cc(tap_preset)
    w.insn("LDAA", "#$11")
    w.insn("LDAB", "#$22")
    w.insn("LDX", "#$3344")
    # LDX's own flags ('--**0-') are the last word on N, Z, V before SWI
    # pushes CC; H, I and C still carry over from tap_preset.
    preset = (nz(0x3344, 16) & (N | Z)) | (tap_preset & ~(N | Z | V) & 0x3F)
    w.insn("SWI")
    # SWI pushes the return PC as the address of *this* instruction -- the
    # one right after SWI, where RTI (down in the handler below) will land.
    # SWI_HANDLER must NOT sit here: it is reached only through the $FFFA
    # vector, never by falling through from SWI, or RTI's landing right back
    # on the handler would loop forever instead of resuming the check.
    #
    # Check CC (via TPA) before CMPB/CPX below get a chance to overwrite it
    # with their own comparison flags; check_a_result's PSHA/PULA keeps A's
    # restored value (0x11) safe across that TPA too.
    w.check_a_result("------", preset, 0, 0x11)
    w.assert_b(0x22)
    w.assert_x(0x3344)
    after = "AFTER_SWI"
    w.insn("BRA", after)
    w.label("SWI_HANDLER")
    # Scramble every register SWI should have pushed, so RTI restoring the
    # original values proves it read the right stack slots, not merely that
    # nothing touched them.
    w.insn("LDAA", "#$00")
    w.insn("LDAB", "#$00")
    w.insn("LDX", "#$0000")
    w.insn("RTI")
    w.label(after)


def generate_6800() -> Writer:
    w = Writer()
    w.insn("LDS", "#$01FF")
    gen_add_sub(w, "6800")
    gen_cmp_bit(w, "6800")
    gen_logic(w, "6800")
    gen_aba_sba_cba(w, "6800")
    gen_single_operand(w, "6800")
    gen_shifts(w, "6800")
    gen_loads(w, "6800")
    gen_stores(w, "6800")
    gen_cpx(w, "6800")
    gen_daa(w, "6800")
    gen_jmp(w)
    gen_branches(w)
    gen_bsr_jsr_rts(w)
    gen_pairs(w)
    gen_swi_rti(w)
    return w


def generate_6801() -> Writer:
    w = Writer()
    w.insn("LDS", "#$01FF")
    gen_cpx_6801_carry(w)
    gen_mul(w)
    gen_abx(w)
    gen_addd_subd(w)
    gen_asld_lsrd(w)
    gen_ldd_std(w)
    gen_brn(w)
    gen_pshx_pulx(w)
    return w


HEADER = """; {filename} -- a self-checking MC6800{part_note} test.
;
; Copyright (c) 2026 the m6800-python contributors.
;
; Permission is hereby granted, free of charge, to any person obtaining a
; copy of this software and associated documentation files (the "Software"),
; to deal in the Software without restriction, including without limitation
; the rights to use, copy, modify, merge, publish, distribute, sublicense,
; and/or sell copies of the Software, and to permit persons to whom the
; Software is furnished to do so, subject to the following conditions:
;
; The above copyright notice and this permission notice shall be included in
; all copies or substantial portions of the Software.
;
; THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
; IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
; FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
; AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
; LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
; FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
; DEALINGS IN THE SOFTWARE.
;
; Generated by scripts/gen_functional_test.py -- see that file's docstring
; for how each expected value was derived, and for this program's scope (one
; representative case per documented mnemonic; WAI is the one mnemonic no
; freestanding self-test can exercise, for want of an interrupt source).
;
; Every check follows the same shape: set up registers and flags, run the
; opcode under test, then verify -- flags first (any comparison instruction
; would itself overwrite them), then any result value. A wrong answer lands
; on its own FAILnnn trap, a tight BRA to itself, so the program counter
; alone identifies which check failed; a correct run reaches SUCCESS with A
; holding $AA.
;
; Change ORIGIN and SCRATCH below to match your board's RAM map, reassemble
; with scripts/asm6800.py, and burn or load the result. See docs/README.md
; and the "Hardware owners" section of validation.md for how to report back.

{origin_sym}\tEQU\t${origin:04X}
{scratch}\tEQU\t${scratch_addr:02X}
{save}\tEQU\t${save_addr:02X}

\tORG\t{origin_sym}
START:
"""

FOOTER = """
SUCCESS:
\tLDAA\t#$AA
DONE:\tBRA\tDONE

; A board's own peripherals could raise IRQ or NMI during this test (a free-
; running timer, say); route anything this program did not arrange itself to
; a trap with its own identifiable address rather than into whatever happens
; to sit at the vector target.
UNEXPECTED_INTERRUPT:
\tBRA\tUNEXPECTED_INTERRUPT

\tORG\t$FFF8
\tFDB\tUNEXPECTED_INTERRUPT\t; IRQ ($FFF8/$FFF9)
\tFDB\t{swi_vector}\t\t; SWI  ($FFFA/$FFFB)
\tFDB\tUNEXPECTED_INTERRUPT\t; NMI  ($FFFC/$FFFD)
\tFDB\tSTART\t\t\t; RESET ($FFFE/$FFFF)
\tEND
"""


def render(writer: Writer, *, filename: str, part_note: str, swi_vector: str) -> str:
    header = HEADER.format(
        filename=filename,
        part_note=part_note,
        origin_sym=ORIGIN_SYMBOL,
        origin=0x1000,
        scratch=SCRATCH,
        scratch_addr=0x40,
        save=SAVE,
        save_addr=0x42,
    )
    body = "\n".join(writer.lines)
    footer = FOOTER.format(swi_vector=swi_vector)
    return header + body + footer


def main() -> None:
    validation = ROOT / "validation"
    validation.mkdir(exist_ok=True)

    w6800 = generate_6800()
    (validation / "functional_test.asm").write_text(
        render(
            w6800,
            filename="validation/functional_test.asm",
            part_note="",
            swi_vector="SWI_HANDLER",
        )
    )

    w6801 = generate_6801()
    (validation / "functional_test_6801.asm").write_text(
        render(
            w6801,
            filename="validation/functional_test_6801.asm",
            part_note="/MC6801/MC6803-only extension",
            swi_vector="UNEXPECTED_INTERRUPT",
        )
    )

    for name in ("functional_test", "functional_test_6801"):
        src = validation / f"{name}.asm"
        origin, data, _symbols = Assembler().assemble(src.read_text())
        (validation / f"{name}.bin").write_bytes(data)
        (validation / f"{name}.s19").write_text(to_s19(origin, data))
        print(f"{name}: origin=${origin:04X} length={len(data)} bytes")

    print("6800 file covers", len(w6800.covered), "mnemonics:", sorted(w6800.covered))
    print("6801 file covers", len(w6801.covered), "mnemonics:", sorted(w6801.covered))


if __name__ == "__main__":
    main()
