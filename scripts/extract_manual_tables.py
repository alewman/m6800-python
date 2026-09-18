"""Extract the per-instruction tables from the Motorola manuals' Appendix A.

M68PRM (the MC6800 programming reference) and M6801RM (the MC6801/6803
reference manual) each give every instruction a page in Appendix A: a prose
rule for each of H I N Z V C, then a table of addressing mode, cycles, bytes,
and the opcode written three times, in hex, octal and decimal.  This script
reads the OCR text layer bitsavers ships in both scans (``pdftotext -layout``
from poppler-utils) and turns those pages into one record per opcode.

The OCR is imperfect ("B" for "8", "O" for "0", "INO" for "IND"), so the
opcode is taken from the **octal and decimal columns, which must agree with
each other**, and the hex column is kept only as a third witness.  A row whose
three encodings disagree, or a page whose layout the text layer scrambles, is
not guessed at: it is listed as unparsed, and the fix goes into
``MANUAL_ROWS`` below with the page it was read from on the rendered image.

    python scripts/extract_manual_tables.py            # JSON on stdout
    python scripts/extract_manual_tables.py --report   # diff against MAME
    python scripts/extract_manual_tables.py --markdown # docs/start-here.md table
    python scripts/extract_manual_tables.py --python > tests/datasheet.py

The manuals are the judge in this repository (docs/validation.md); MAME is
the detector.  ``--report`` lists every cell where MAME 0.285's cycle table
disagrees with the manual, so each disagreement can be settled on the page.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "reference"

# PDF page ranges of Appendix A, found by reading the page headers.
MANUALS = {
    "M68PRM": ("M68PRM.pdf", range(36, 110)),
    "M6801RM": ("M6801RM.pdf", range(270, 358)),
}

FLAG_NAMES = "HINZVC"

# Rows the text layer loses or scrambles, read off the rendered page instead
# (pdftoppm -r 150).  Key: (manual, pdf page) -> list of
# (mode, cycles, bytes, opcode).  Each entry was checked on the image.
MANUAL_ROWS: dict[tuple[str, int], list[tuple[str, int, int, int]]] = {
    ("M68PRM", 70): [("INH", 4, 1, 0x34)],  # DES, A-37
    ("M68PRM", 109): [("INH", 9, 1, 0x3E)],  # WAI, A-76
    ("M6801RM", 316): [("IND", 6, 2, 0xAD)],  # JSR, A-49
    ("M6801RM", 319): [("DIR", 4, 2, 0x9E)],  # LDS, A-52
    ("M6801RM", 333): [("ACCA", 2, 1, 0x49)],  # ROL, A-66
    ("M6801RM", 339): [("INH", 2, 1, 0x0D)],  # SEC, A-72
    ("M6801RM", 354): [
        ("ACCA", 2, 1, 0x4D),
        ("ACCB", 2, 1, 0x5D),  # TST, A-87
        ("EXT", 6, 3, 0x7D),
        ("IND", 6, 2, 0x6D),
    ],
}

# Instruction pages that carry no opcode rows by design: DAA's table starts
# overleaf (M68PRM A-34), and the SWI worked examples (M68PRM A-68, M6801RM A-82).
NO_ROWS = {("M68PRM", 67), ("M68PRM", 101), ("M6801RM", 349)}

ROW = re.compile(
    r"^\s*(?:(?P<acc>[AB8])\s+)?['`]?(?P<mode>[A-Za-z]{1,8})\s+(?P<cyc>\d{1,2})\s+"
    r"(?P<bytes>[123])\s+(?P<hex>\S{1,3}?)[·.,]?\s+\.?(?P<oct>[0-7]{3})\s+(?P<dec>\d{3})\s*\S*\s*$"
)
# OCR reads the flag letters as "z", "c", "1" (for I) and sometimes puts a stray dot before them.
FLAG_LINE = re.compile(
    r"^\s*(?:Condition\s+Codes:|Codes:)?\s*\.?\s*(?P<f>[HINZVCzc1])\s*[:;,.]\s*(?P<t>\S.*)$"
)

SEPARATORS = {"I", "|", "'", "l", ".", "-", ".-", "·", "r", "T", "J", "-1", ","}

MODE_FIX = {
    "INH": "INH",
    "INO": "IND",
    "IND": "IND",
    "DIA": "DIR",
    "OIR": "DIR",
    "DIR": "DIR",
    "IMM": "IMM",
    "RMM": "IMM",
    "EXT": "EXT",
    "REL": "REL",
    "INHERENT": "INH",
    "A": "ACCA",
    "B": "ACCB",
    "8": "ACCB",
}


def page_text(pdf: Path, page: int) -> str:
    return subprocess.run(
        ["pdftotext", "-layout", "-f", str(page), "-l", str(page), str(pdf), "-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def classify(rule: str) -> str:
    """Map a manual's prose rule for one flag to Motorola's summary notation."""
    r = rule.strip().lower().replace("_", ".")
    if re.match(r"not?\s*a\w*ected", r):  # OCR: "No affected", "Not atTected"
        return "-"
    if r.startswith("not defined") or r.startswith("undefined"):
        return "?"
    if r.startswith("cleared") or r.startswith("reset."):
        return "0"
    if re.match(r"set\.?$", r) or r.startswith("set. "):
        return "1"
    return "*"


def parse_flags(lines: list[str]) -> str | None:
    """Return the six-character HINZVC rule string, or None if not stated per bit."""
    rules: dict[str, str] = {}
    in_cc = False
    for line in lines:
        if re.match(r"^\s*(Condition\s*$|Condition\s+Codes:|Codes:)", line):
            in_cc = True
        if re.match(r"^\s*Boolean|^\s*Addressing", line):
            in_cc = False
        if not in_cc:
            continue
        m = FLAG_LINE.match(line)
        if m:
            rules.setdefault(m.group("f").upper().replace("1", "I"), m.group("t"))
    if len(rules) == 6:
        return "".join(classify(rules[f]) for f in FLAG_NAMES)
    joined = " ".join(lines)
    if re.search(r"Codes:\s+Not:?\s+affected", joined):
        return "------"
    # RTI and TAP: every bit comes from the stack or from ACCA.
    if re.search(
        r"Codes:\s+(Restored to the states pulled|Set or reset according to the contents)", joined
    ):
        return "######"
    return None


def extract(manual: str) -> tuple[dict[int, dict], list[str]]:
    filename, pages = MANUALS[manual]
    pdf = REFERENCE / filename
    records: dict[int, dict] = {}
    problems: list[str] = []
    carried_flags = None
    for page in pages:
        lines = page_text(pdf, page).splitlines()
        body = [l for l in lines if l.strip()]
        if not body:
            continue
        folio = next(
            (l.strip() for l in reversed(body) if re.fullmatch(r"\s*A\s*-\s*\S+\s*", l)), "?"
        )
        title = body[0].split()[0] if body[0].split() else "?"
        flags = parse_flags(body)
        # DAA's and SWI's addressing tables spill onto the next page.
        if flags is None and carried_flags is not None:
            flags = carried_flags
        carried_flags = flags
        rows = []
        for line in body:
            # M6801RM prints its column rules, which OCR as "I", "|" or "'";
            # M68PRM has stray dots.  Neither is ever a whole cell.
            line = " ".join(t.rstrip("·") for t in line.split() if t not in SEPARATORS)
            m = ROW.match(line)
            if not m:
                continue
            octal, dec = int(m.group("oct"), 8), int(m.group("dec"))
            if octal != dec:
                problems.append(
                    f"{manual} p{page} ({folio}): octal/decimal disagree: {line.strip()}"
                )
                continue
            hex_ok = m.group("hex").upper().replace("O", "0") == f"{dec:02X}"
            mode = MODE_FIX.get(m.group("mode").upper().strip("'"), m.group("mode"))
            rows.append((mode, int(m.group("cyc")), int(m.group("bytes")), dec, hex_ok))
        for mode, cyc, nbytes, op in MANUAL_ROWS.get((manual, page), []):
            rows.append((mode, cyc, nbytes, op, True))
        for mode, cyc, nbytes, op, hex_ok in rows:
            if op in records:
                # M6801RM gives Motorola's alternate mnemonics their own pages
                # (BHS = BCC, BLO = BCS, LSL = ASL, LSLD = ASLD); they must agree.
                first = records[op]
                if (first["cycles"], first["bytes"], first["flags"]) != (cyc, nbytes, flags):
                    problems.append(
                        f"{manual} p{page}: opcode {op:02X} disagrees with p{first['pdf_page']}"
                    )
                first.setdefault("aliases", []).append(f"{title} p{page}")
                continue
            records[op] = {
                "title": title,
                "mode": mode,
                "cycles": cyc,
                "bytes": nbytes,
                "flags": flags,
                "pdf_page": page,
                "folio": folio,
                "hex_ocr_ok": hex_ok,
            }
        if not rows and (manual, page) not in NO_ROWS:
            problems.append(f"{manual} p{page} ({folio}) {title}: no opcode rows parsed")
        if rows and flags is None:
            problems.append(f"{manual} p{page} ({folio}) {title}: flag rules not parsed")
    return records, problems


def mame_cycles(manual: str) -> list[int]:
    src = REFERENCE / "mame0285"
    if manual == "M68PRM":
        text, array, cls = (src / "m6800.cpp").read_text(), "cycles_6800", "m6800_cpu_device"
    else:
        text, array, cls = (src / "m6801.cpp").read_text(), "cycles_6803", "m6801_cpu_device"
    body = re.search(
        re.escape(cls) + r"::" + array + r"\[256\]\s*=\s*\{(.*?)\n\};", text, re.S
    ).group(1)
    body = re.sub(r"/\*.*?\*/", "", body)
    return [
        -1 if v.strip() == "XX" else int(v) for v in body.replace("\n", " ").split(",") if v.strip()
    ]


def hnzvc(flags: str) -> str:
    """Drop the I column: the table's flag field is H N Z V C, as Motorola prints it."""
    return flags[0] + flags[2:]


def markdown(prm: dict[int, dict], rm: dict[int, dict]) -> None:
    """Print docs/start-here.md's instruction table from the manuals.

    Grouping and mnemonics come from MAME's disassembler table (names are not
    a judgement); every byte count, cycle count and flag rule comes from the
    manuals.  Cells marked with a double dagger are opcodes MAME executes that
    Motorola does not assign on that part, and only their cycle counts are
    MAME's.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import dump_mame_tables as mame

    order = ("immediate", "direct", "indexed", "extended", "inherent", "relative")

    def cell(entry: dict | None) -> str:
        if entry is None:
            return ""
        op = entry["op"]
        on_6800, on_6801 = prm.get(op), rm.get(op)
        if on_6800 is None and on_6801 is None:
            cycles = entry["c6800"] if entry["legal_6800"] else entry["c6803"]
            if entry["legal_6800"] and entry["c6800"] != entry["c6803"]:
                cycles = f"{entry['c6800']} · {entry['c6803']}"
            return f"`{op:02X}`‡ {entry['bytes']}/{cycles}"
        if on_6800 is None:
            mark = "†‡" if entry["legal_6800"] else "†"
            return f"`{op:02X}`{mark} {on_6801['bytes']}/{on_6801['cycles']}"
        if on_6800["bytes"] != on_6801["bytes"]:
            raise SystemExit(f"{op:02X}: byte counts differ between the manuals")
        if on_6800["cycles"] != on_6801["cycles"]:
            return f"`{op:02X}` {on_6800['bytes']}/{on_6800['cycles']} · {on_6801['cycles']}"
        return f"`{op:02X}` {on_6800['bytes']}/{on_6800['cycles']}"

    def flags(modes: dict[str, dict]) -> str:
        documented = [modes[m]["op"] for m in order if m in modes and modes[m]["op"] in prm | rm]
        f6800 = {hnzvc(prm[op]["flags"]) for op in documented if op in prm}
        f6801 = {hnzvc(rm[op]["flags"]) for op in documented if op in rm}
        if len(f6800) > 1 or len(f6801) > 1:
            raise SystemExit(f"flag rules differ between addressing modes: {documented}")
        if f6800 and f6801 and f6800 != f6801:
            return f"`{f6800.pop()}` · `{f6801.pop()}`"
        return f"`{(f6800 or f6801).pop()}`"

    print("| Mnemonic | Operation | IMM | DIR | IDX | EXT | INH / REL | HNZVC |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    grouped = mame.load()
    for mnemonic in sorted(grouped):
        modes = grouped[mnemonic]
        print(
            "| **{}** | {} | {} | {} | {} | {} | {} | {} |".format(
                mnemonic,
                mame.OPERATION.get(mnemonic, "?"),
                cell(modes.get("immediate")),
                cell(modes.get("direct")),
                cell(modes.get("indexed")),
                cell(modes.get("extended")),
                cell(modes.get("inherent") or modes.get("relative")),
                flags(modes),
            )
        )


def python_module(prm: dict[int, dict], rm: dict[int, dict]) -> None:
    """Print tests/datasheet.py: one record per documented opcode, from the manuals."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import dump_mame_tables as mame

    names = {}
    for mnemonic, modes in mame.load().items():
        for mode, entry in modes.items():
            names[entry["op"]] = (mnemonic, mode)
    print('"""Per-opcode datasheet for the MC6800 and MC6801/6803, transcribed from the manuals.')
    print()
    print("Generated by ``scripts/extract_manual_tables.py --python`` from M68PRM Appendix A")
    print("(MC6800) and M6801RM Appendix A (MC6801/6803); do not edit by hand.  ``flags``")
    print("strings cover H I N Z V C in Motorola's notation: ``-`` not affected, ``0``")
    print("cleared, ``1`` set, ``*`` set by a rule, ``?`` not defined, ``#`` loaded.")
    print("A ``None`` cycle count means the opcode is not documented on that part.")
    print('"""')
    print()
    print("from typing import NamedTuple")
    print()
    print()
    print("class Opcode(NamedTuple):")
    print("    mnemonic: str")
    print("    mode: str")
    print("    length: int")
    print("    cycles_6800: int | None")
    print("    cycles_6801: int | None")
    print("    flags_6800: str | None")
    print("    flags_6801: str | None")
    print("    page_6800: str | None")
    print("    page_6801: str | None")
    print()
    print()
    print("DATASHEET: dict[int, Opcode] = {")
    for op in sorted(set(prm) | set(rm)):
        a, b = prm.get(op), rm.get(op)
        mnemonic, mode = names[op]
        length = (a or b)["bytes"]
        folio_a = a and f"M68PRM A-{a['pdf_page'] - 33}"
        folio_b = b and f"M6801RM A-{b['pdf_page'] - 267}"
        print(
            f"    0x{op:02X}: Opcode({mnemonic!r}, {mode!r}, {length}, "
            f"{a and a['cycles']!r}, {b and b['cycles']!r}, "
            f"{a and a['flags']!r}, {b and b['flags']!r}, {folio_a!r}, {folio_b!r}),"
        )
    print("}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--report", action="store_true", help="diff the manuals against MAME 0.285")
    parser.add_argument("--markdown", action="store_true", help="print docs/start-here.md's table")
    parser.add_argument("--python", action="store_true", help="print tests/datasheet.py")
    args = parser.parse_args()
    out = {}
    for manual in MANUALS:
        records, problems = extract(manual)
        out[manual] = {
            "records": {f"{op:02X}": r for op, r in sorted(records.items())},
            "problems": problems,
        }
    tables = [{int(k, 16): v for k, v in out[m]["records"].items()} for m in MANUALS]
    if args.markdown:
        markdown(*tables)
        return
    if args.python:
        python_module(*tables)
        return
    if not args.report:
        json.dump(out, sys.stdout, indent=1)
        return
    for manual, data in out.items():
        recs = {int(k, 16): v for k, v in data["records"].items()}
        print(f"== {manual}: {len(recs)} opcodes parsed")
        for p in data["problems"]:
            print("  PROBLEM", p)
        for op, r in sorted(recs.items()):
            if not r["hex_ocr_ok"]:
                print(f"  note {op:02X}: hex OCR differs (octal/decimal agree) p{r['pdf_page']}")
        mame = mame_cycles(manual)
        for op in range(256):
            m, r = mame[op], recs.get(op)
            if r is None and m != -1:
                print(f"  MAME-only {op:02X}: MAME {m} cycles, not in {manual}")
            elif r is not None and m != r["cycles"]:
                print(
                    f"  CYCLES {op:02X} {r['title']} {r['mode']}: {manual} {r['cycles']} "
                    f"(p{r['pdf_page']} {r['folio']}) vs MAME {m}"
                )


if __name__ == "__main__":
    main()
