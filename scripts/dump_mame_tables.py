"""Print MAME's view of the 6800/6801 instruction table, as a detector.

The table in docs/start-here.md is generated from the Motorola manuals by
scripts/extract_manual_tables.py --markdown, which borrows this script's
opcode grouping and names.  Run this one to see what MAME believes, and diff
the two after any MAME upgrade.  It reads four tables out of MAME's 6800 core:

    m6800.cpp   cycles_6800[256], m6800_insn[0x100]
    m6801.cpp   cycles_6803[256], m6803_insn[0x100]
    6800dasm.cpp  table[0x104][3]   mnemonic, addressing mode, per-CPU validity
    6800ops.hxx   the per-handler "/* $xx MNEM mode HNZVC */" comments

MAME is an *emulator-derived* source (docs/validation.md): this script tells
you what MAME believes, and the Motorola manuals decide whether MAME is right.
The flag column comes from MAME's handler *comments* (plus EXTRA_FLAGS for
handlers without one), and the manuals show it wrong on 52 documented opcodes
where MAME's *code* is right: H marked "?" on the subtracts, compares, NEG and
the left shifts; V missing on ASR/LSR/ROR and their D forms; C missing on TST;
Z on MUL; V on DAA given as 0 where the manuals say "not defined".  Never read
flags from this output.

    python scripts/dump_mame_tables.py [--mame-src DIR] > table.md

Default source directory: reference/mame0285, as fetched and hash-verified by
scripts/fetch_mame_source.py.  Run that first.
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

DEFAULT_SRC = Path(__file__).resolve().parents[1] / "reference" / "mame0285"

# Motorola's mnemonics where MAME's disassembler uses a shorter alias.
RENAME = {"LDA": "LDAA", "LDB": "LDAB", "STA": "STAA", "STB": "STAB",
          "ORA": "ORAA", "ORB": "ORAB", "CMPX": "CPX"}

# Opcodes MAME executes that Motorola's map does not assign on the part in
# question: the four "store immediate" slots and STD immediate on every part,
# and BRN and JSR-direct on the plain 6800 (both are real 6801 instructions).
# Subtracting these six from MAME's 203 6800-legal opcodes gives exactly
# Motorola's documented 197; subtracting the five from its 225 6801-legal
# opcodes gives 220.  See docs/undocumented-behavior.md.
NOT_MOTOROLA = {0x87, 0x8F, 0xC7, 0xCF, 0xCD, 0x9D, 0x21}

# Handlers whose "/* $xx ... */" comment carries no HNZVC field.
EXTRA_FLAGS = {0x01: "-----", 0x0A: "---0-", 0x0B: "---1-", 0x0C: "----0",
               0x0D: "----1", 0x0E: "-----", 0x0F: "-----", 0x19: "-**0*",
               0x3F: "-----", 0x8D: "-----"}

MODE_NAME = {"inh": "inherent", "rel": "relative", "imb": "immediate",
             "imw": "immediate", "dir": "direct", "idx": "indexed",
             "ext": "extended"}
MODE_BYTES = {"inh": 1, "rel": 2, "imb": 2, "imw": 3, "dir": 2, "idx": 2,
              "ext": 3, "imd": 3, "imx": 3, "sx1": 1}

OPERATION = {
    "ABA": "A ← A + B", "ABX": "X ← X + B (B unsigned)",
    "ADCA": "A ← A + M + C", "ADCB": "B ← B + M + C",
    "ADDA": "A ← A + M", "ADDB": "B ← B + M", "ADDD": "D ← D + M:M+1",
    "ANDA": "A ← A ∧ M", "ANDB": "B ← B ∧ M",
    "ASL": "M ← M << 1, C ← b7", "ASLA": "A ← A << 1, C ← b7",
    "ASLB": "B ← B << 1, C ← b7", "ASLD": "D ← D << 1, C ← b15",
    "ASR": "M ← M >> 1 arithmetic", "ASRA": "A ← A >> 1 arithmetic",
    "ASRB": "B ← B >> 1 arithmetic",
    "BCC": "branch if C=0", "BCS": "branch if C=1", "BEQ": "branch if Z=1",
    "BGE": "branch if N⊕V=0", "BGT": "branch if Z∨(N⊕V)=0",
    "BHI": "branch if C∨Z=0", "BITA": "A ∧ M, flags only",
    "BITB": "B ∧ M, flags only", "BLE": "branch if Z∨(N⊕V)=1",
    "BLS": "branch if C∨Z=1", "BLT": "branch if N⊕V=1", "BMI": "branch if N=1",
    "BNE": "branch if Z=0", "BPL": "branch if N=0", "BRA": "branch always",
    "BRN": "branch never (2-byte NOP)", "BSR": "push PC, branch to subroutine",
    "BVC": "branch if V=0", "BVS": "branch if V=1", "CBA": "A − B, flags only",
    "CLC": "C ← 0", "CLI": "I ← 0", "CLR": "M ← 0", "CLRA": "A ← 0",
    "CLRB": "B ← 0", "CLV": "V ← 0", "CMPA": "A − M, flags only",
    "CMPB": "B − M, flags only", "CPX": "X − M:M+1, flags only",
    "COM": "M ← ¬M", "COMA": "A ← ¬A", "COMB": "B ← ¬B",
    "DAA": "decimal adjust A after ADD/ADC/ABA", "DEC": "M ← M − 1",
    "DECA": "A ← A − 1", "DECB": "B ← B − 1", "DES": "SP ← SP − 1",
    "DEX": "X ← X − 1", "EORA": "A ← A ⊻ M", "EORB": "B ← B ⊻ M",
    "INC": "M ← M + 1", "INCA": "A ← A + 1", "INCB": "B ← B + 1",
    "INS": "SP ← SP + 1", "INX": "X ← X + 1", "JMP": "PC ← EA",
    "JSR": "push PC, PC ← EA", "LDAA": "A ← M", "LDAB": "B ← M",
    "LDD": "D ← M:M+1", "LDS": "SP ← M:M+1", "LDX": "X ← M:M+1",
    "LSR": "M ← M >> 1 logical", "LSRA": "A ← A >> 1 logical",
    "LSRB": "B ← B >> 1 logical", "LSRD": "D ← D >> 1 logical",
    "MUL": "D ← A × B (unsigned)", "NEG": "M ← 0 − M", "NEGA": "A ← 0 − A",
    "NEGB": "B ← 0 − B", "NOP": "no operation", "ORAA": "A ← A ∨ M",
    "ORAB": "B ← B ∨ M", "PSHA": "push A", "PSHB": "push B",
    "PSHX": "push X (low byte first)", "PULA": "pull A", "PULB": "pull B",
    "PULX": "pull X", "ROL": "M ← rotate left through C",
    "ROLA": "A ← rotate left through C", "ROLB": "B ← rotate left through C",
    "ROR": "M ← rotate right through C", "RORA": "A ← rotate right through C",
    "RORB": "B ← rotate right through C", "RTI": "pull CC,B,A,X,PC",
    "RTS": "pull PC", "SBA": "A ← A − B", "SBCA": "A ← A − M − C",
    "SBCB": "B ← B − M − C", "SEC": "C ← 1", "SEI": "I ← 1", "SEV": "V ← 1",
    "STAA": "M ← A", "STAB": "M ← B", "STD": "M:M+1 ← D", "STS": "M:M+1 ← SP",
    "STX": "M:M+1 ← X", "SUBA": "A ← A − M", "SUBB": "B ← B − M",
    "SUBD": "D ← D − M:M+1", "SWI": "software interrupt, vector $FFFA",
    "TAB": "B ← A", "TAP": "CC ← A", "TBA": "A ← B", "TPA": "A ← CC",
    "TST": "M − 0, flags only", "TSTA": "A − 0, flags only",
    "TSTB": "B − 0, flags only", "TSX": "X ← SP + 1", "TXS": "SP ← X − 1",
    "WAI": "stack state, wait for interrupt",
}


def _handlers(text: str, array: str, cls: str) -> list[str]:
    body = re.search(re.escape(array) + r"\[0x100\]\s*=\s*\{(.*?)\n\};", text, re.S).group(1)
    names = re.findall(r"&" + cls + r"::(\w+)", body)
    if len(names) != 256:
        raise SystemExit(f"{array}: expected 256 handlers, parsed {len(names)}")
    return names


def _cycles(text: str, array: str, cls: str) -> list[int]:
    # MAME uses an "XX" sentinel for illegal opcodes; its value is an invention
    # to stop the emulator hanging, not a measurement (docs/undocumented-behavior.md).
    sentinel = int(re.search(r"#define XX\s+(\d+)", text).group(1))
    body = re.search(re.escape(cls) + r"::" + re.escape(array) + r"\[256\]\s*=\s*\{(.*?)\n\};", text, re.S).group(1)
    body = re.sub(r"/\*.*?\*/", "", body)
    values = [v.strip() for v in body.replace("\n", " ").split(",") if v.strip()]
    if len(values) != 256:
        raise SystemExit(f"{array}: expected 256 cycle counts, parsed {len(values)}")
    return [sentinel if v == "XX" else int(v) for v in values]


def load(source: Path = DEFAULT_SRC) -> dict[str, dict[str, dict]]:
    """Group every opcode MAME executes by Motorola mnemonic and addressing mode."""
    m6800 = (source / "m6800.cpp").read_text()
    m6801 = (source / "m6801.cpp").read_text()
    dasm = (source / "6800dasm.cpp").read_text()
    ops = (source / "6800ops.hxx").read_text()

    insn_6800 = _handlers(m6800, "m6800_insn", "m6800_cpu_device")
    insn_6803 = _handlers(m6801, "m6803_insn", "m6801_cpu_device")
    cyc_6800 = _cycles(m6800, "cycles_6800", "m6800_cpu_device")
    cyc_6803 = _cycles(m6801, "cycles_6803", "m6801_cpu_device")

    table = re.sub(r"/\*.*?\*/", "", re.search(r"table\[0x104\]\[3\]\s*=\s*\{(.*?)\n\};", dasm, re.S).group(1))
    decoded = re.findall(r"\{\s*(\w+)\s*,\s*(\w+)\s*,\s*(\d+)\s*\}", table)[:256]

    flags = {int(m.group(1), 16): m.group(2)
             for m in re.finditer(r"/\*\s*\$([0-9a-fA-F]{2})\s+[A-Z0-9_]+\s+\S+\s+([-0-9*?@#]{5})\s*\*/", ops)}
    flags.update({op: f for op, f in EXTRA_FLAGS.items() if op not in flags})

    grouped: dict[str, dict[str, dict]] = defaultdict(dict)
    for opcode, (raw, mode, _validity) in enumerate(decoded):
        legal_6800 = not insn_6800[opcode].startswith("illegl")
        legal_6803 = not insn_6803[opcode].startswith("illegl")
        if raw == "ill" or not (legal_6800 or legal_6803):
            continue
        mnemonic = RENAME.get(raw.strip("_").upper(), raw.strip("_").upper())
        grouped[mnemonic][MODE_NAME.get(mode, mode)] = {
            "op": opcode, "bytes": MODE_BYTES.get(mode, 1),
            "c6800": cyc_6800[opcode], "c6803": cyc_6803[opcode],
            "legal_6800": legal_6800, "flags": flags.get(opcode, "?????"),
        }
    return grouped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mame-src", type=Path, default=DEFAULT_SRC)
    grouped = load(parser.parse_args().mame_src)

    def cell(entry: dict | None) -> str:
        if entry is None:
            return ""
        mark = "‡" if entry["op"] in NOT_MOTOROLA else ""
        if not entry["legal_6800"]:
            return f"`{entry['op']:02X}`{mark} {entry['bytes']}/{entry['c6803']}†"
        if entry["c6800"] != entry["c6803"]:
            return f"`{entry['op']:02X}`{mark} {entry['bytes']}/{entry['c6800']} · {entry['c6803']}"
        return f"`{entry['op']:02X}`{mark} {entry['bytes']}/{entry['c6800']}"

    print("| Mnemonic | Operation | IMM | DIR | IDX | EXT | INH / REL | HNZVC |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for mnemonic in sorted(grouped):
        modes = grouped[mnemonic]
        flag = next((modes[m]["flags"] for m in
                     ("immediate", "direct", "indexed", "extended", "inherent", "relative")
                     if m in modes), "?????")
        print("| **%s** | %s | %s | %s | %s | %s | %s | `%s` |" % (
            mnemonic, OPERATION.get(mnemonic, "?"),
            cell(modes.get("immediate")), cell(modes.get("direct")),
            cell(modes.get("indexed")), cell(modes.get("extended")),
            cell(modes.get("inherent") or modes.get("relative")), flag))


if __name__ == "__main__":
    main()
