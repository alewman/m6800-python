"""A small two-pass MC6800/6801/6803 assembler, for validation/functional_test.asm.

No system assembler was found on this machine (``asl``, ``vasm6800_std``,
``vasm6800_oldstyle``, ``a68`` -- none on PATH), so docs/handoff-polish.md's
stretch item asks for one here instead. The opcode/mode/length table is
tests/datasheet.py's ``DATASHEET``, never duplicated by hand.

Syntax, kept deliberately small (this does exactly two passes, no fixed-point
iteration over instruction lengths):

    label:                      a label alone on its own line
    label: MNEMONIC operand     or sharing a line with an instruction
    MNEMONIC                    inherent                  (NOP, TAB, RTS, ...)
    MNEMONIC #expr              immediate                 (width from the opcode's length)
    MNEMONIC <expr              direct, forced
    MNEMONIC >expr              extended, forced
    MNEMONIC expr               direct/extended auto-picked from a *numeric* expr;
                                 a bare label is legal here only when the mnemonic has
                                 just one of {direct, extended} (e.g. JMP, JSR: extended
                                 only) -- otherwise use < or > to say which
    MNEMONIC expr,X             indexed (expr a 0..255 numeric offset; no label indexing)
    MNEMONIC label              relative (Bxx/BSR: the only mode they have)

Directives:

    label EQU expr
    ORG expr
    FCB b[,b...]                one byte each
    FDB w[,w...]                one big-endian word each
    RMB n                       reserve n bytes (advances the address, emits nothing)
    END

Expressions: a decimal integer, ``$hex``, a label, or two such terms joined by
``+`` or ``-``. ``;`` starts a comment; blank lines are ignored.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from datasheet import DATASHEET  # noqa: E402

DIRECTIVES = {"EQU", "ORG", "FCB", "FDB", "RMB", "END"}

# (mnemonic, mode) -> (opcode, length); modes available per mnemonic.
_BY_NAME: dict[str, dict[str, tuple[int, int]]] = {}
for _opcode, _entry in DATASHEET.items():
    _BY_NAME.setdefault(_entry.mnemonic, {})[_entry.mode] = (_opcode, _entry.length)


class AssemblerError(Exception):
    def __init__(self, message: str, line_no: int | None = None) -> None:
        self.line_no = line_no
        super().__init__(f"line {line_no}: {message}" if line_no else message)


@dataclass
class _Token:
    """One parsed source line, address-independent."""

    line_no: int
    label: str | None
    op: str | None  # mnemonic or directive, uppercased
    operand: str | None  # raw operand text, unparsed


def _strip_comment(text: str) -> str:
    out = []
    for ch in text:
        if ch == ";":
            break
        out.append(ch)
    return "".join(out)


def _tokenize(source: str) -> list[_Token]:
    tokens: list[_Token] = []
    for line_no, raw in enumerate(source.splitlines(), start=1):
        text = _strip_comment(raw).strip()
        if not text:
            continue
        words = text.split(None, 1)
        first = words[0]
        rest = words[1].strip() if len(words) > 1 else ""
        first_bare = first[:-1] if first.endswith(":") else first
        is_known = first_bare.upper() in DIRECTIVES or first_bare.upper() in _BY_NAME
        if is_known:
            label = None
            op, operand = first_bare.upper(), rest
        else:
            label = first_bare
            if not rest:
                op, operand = None, None
            else:
                op_rest = rest.split(None, 1)
                op = op_rest[0].upper()
                operand = op_rest[1].strip() if len(op_rest) > 1 else ""
        tokens.append(_Token(line_no, label, op, operand or None))
    return tokens


def _parse_number(text: str, line_no: int) -> int:
    text = text.strip()
    if text.startswith("$"):
        return int(text[1:], 16)
    if text.lower().startswith("0x"):
        return int(text, 16)
    try:
        return int(text, 10)
    except ValueError as exc:
        raise AssemblerError(f"not a number: {text!r}", line_no) from exc


def _is_number(text: str) -> bool:
    text = text.strip()
    if text.startswith("$") or text.lower().startswith("0x"):
        return True
    return text.lstrip("-").isdigit()


def _split_term(expr: str) -> tuple[str, str | None, str | None]:
    """Split ``a+b`` or ``a-b`` into (left, op, right); a bare term gives (expr, None, None)."""
    depth = 0
    for i, ch in enumerate(expr):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch in "+-" and depth == 0 and i > 0:
            return expr[:i], ch, expr[i + 1 :]
    return expr, None, None


class Assembler:
    """Two-pass assembler: :meth:`assemble` returns ``(origin, bytes, symbols)``."""

    def __init__(self) -> None:
        self.symbols: dict[str, int] = {}

    def _eval(self, expr: str, line_no: int) -> int:
        expr = expr.strip()
        left, op, right = _split_term(expr)
        if op is None:
            left = left.strip()
            if _is_number(left):
                return _parse_number(left, line_no)
            if left not in self.symbols:
                raise AssemblerError(f"undefined symbol: {left!r}", line_no)
            return self.symbols[left]
        lv = self._eval(left, line_no)
        rv = self._eval(right, line_no)
        return lv + rv if op == "+" else lv - rv

    def _operand_mode(self, mnemonic: str, operand: str | None, line_no: int) -> tuple[str, str]:
        """The addressing mode and the bare expression text (value not yet evaluated).

        Needs no symbol to be already defined, except that an auto-picked
        direct/extended choice on a *numeric* operand is decided here (its
        value does not depend on any label), so pass 1 can size the
        instruction without a second pass over lengths.
        """
        modes = _BY_NAME.get(mnemonic)
        if modes is None:
            raise AssemblerError(f"unknown mnemonic: {mnemonic!r}", line_no)
        if operand is None:
            if "inherent" not in modes:
                raise AssemblerError(f"{mnemonic} needs an operand", line_no)
            return "inherent", ""
        operand = operand.strip()
        if operand.endswith((",X", ",x")):
            if "indexed" not in modes:
                raise AssemblerError(f"{mnemonic} has no indexed mode", line_no)
            return "indexed", operand[:-2].strip() or "0"
        if operand.startswith("#"):
            if "immediate" not in modes:
                raise AssemblerError(f"{mnemonic} has no immediate mode", line_no)
            return "immediate", operand[1:]
        if operand.startswith("<"):
            if "direct" not in modes:
                raise AssemblerError(f"{mnemonic} has no direct mode", line_no)
            return "direct", operand[1:]
        if operand.startswith(">"):
            if "extended" not in modes:
                raise AssemblerError(f"{mnemonic} has no extended mode", line_no)
            return "extended", operand[1:]
        if "relative" in modes:
            return "relative", operand
        has_direct, has_extended = "direct" in modes, "extended" in modes
        if has_direct and has_extended:
            if not _is_number(operand):
                raise AssemblerError(
                    f"{mnemonic} {operand}: ambiguous direct/extended label operand; "
                    "use < or > to say which",
                    line_no,
                )
            value = self._eval(operand, line_no)
            return ("direct" if 0 <= value <= 0xFF else "extended"), operand
        if has_extended:
            return "extended", operand
        if has_direct:
            return "direct", operand
        raise AssemblerError(f"{mnemonic} has no memory-reference mode", line_no)

    def assemble(self, source: str) -> tuple[int, bytes, dict[str, int]]:
        tokens = _tokenize(source)
        self.symbols = {}
        origin = 0
        pc = 0
        sizes: list[int] = []
        # Pass 1: addresses and EQUs. ORG/RMB/FCB/FDB sizes are address-independent;
        # instruction sizes depend only on the operand syntax above, never on a
        # label's eventual value, so one pass over lengths is enough.
        first_org_seen = False
        for tok in tokens:
            if tok.op == "END":
                break
            if tok.op == "ORG":
                pc = self._eval(tok.operand, tok.line_no)
                if not first_org_seen:
                    origin = pc
                    first_org_seen = True
                sizes.append(0)
                if tok.label is not None:
                    self.symbols[tok.label] = pc
                continue
            if tok.op == "EQU":
                if tok.label is None:
                    raise AssemblerError("EQU needs a label", tok.line_no)
                self.symbols[tok.label] = self._eval(tok.operand, tok.line_no)
                sizes.append(0)
                continue
            if tok.label is not None:
                self.symbols[tok.label] = pc
            if tok.op is None:
                sizes.append(0)
                continue
            if tok.op == "FCB":
                size = len((tok.operand or "").split(","))
            elif tok.op == "FDB":
                size = 2 * len((tok.operand or "").split(","))
            elif tok.op == "RMB":
                size = self._eval(tok.operand, tok.line_no)
            else:
                _mode, _expr = self._operand_mode(tok.op, tok.operand, tok.line_no)
                _opcode, length = _BY_NAME[tok.op][_mode]
                size = length
            sizes.append(size)
            pc += size

        # Pass 2: emit bytes, now that every label is known.
        out = bytearray()
        pc = origin
        for tok, size in zip(tokens, sizes, strict=False):
            if tok.op == "END":
                break
            if tok.op in ("ORG", "EQU"):
                if tok.op == "ORG":
                    pc = self._eval(tok.operand, tok.line_no)
                    gap = pc - (origin + len(out))
                    if gap < 0:
                        raise AssemblerError(
                            f"ORG ${pc:04X} goes backward past already-emitted "
                            f"${origin + len(out):04X}",
                            tok.line_no,
                        )
                    out.extend(b"\xff" * gap)  # unprogrammed-EPROM filler for the gap
                continue
            if tok.op is None:
                continue
            if tok.op == "FCB":
                for term in (tok.operand or "").split(","):
                    value = self._eval(term, tok.line_no)
                    if not 0 <= value <= 0xFF:
                        raise AssemblerError(f"FCB value out of range: {value}", tok.line_no)
                    out.append(value)
            elif tok.op == "FDB":
                for term in (tok.operand or "").split(","):
                    value = self._eval(term, tok.line_no)
                    if not 0 <= value <= 0xFFFF:
                        raise AssemblerError(f"FDB value out of range: {value}", tok.line_no)
                    out.append((value >> 8) & 0xFF)
                    out.append(value & 0xFF)
            elif tok.op == "RMB":
                out.extend(bytes(size))
            else:
                mode, expr = self._operand_mode(tok.op, tok.operand, tok.line_no)
                opcode, length = _BY_NAME[tok.op][mode]
                value = self._eval(expr, tok.line_no) if expr else None
                out.append(opcode)
                if mode == "inherent":
                    pass
                elif mode == "relative":
                    offset = value - (pc + length)
                    if not -128 <= offset <= 127:
                        raise AssemblerError(
                            f"branch out of range: offset {offset} to {tok.operand}", tok.line_no
                        )
                    out.append(offset & 0xFF)
                elif mode == "indexed":
                    if not 0 <= value <= 0xFF:
                        raise AssemblerError(f"indexed offset out of range: {value}", tok.line_no)
                    out.append(value)
                elif mode == "direct":
                    out.append(value & 0xFF)
                elif mode == "extended":
                    out.append((value >> 8) & 0xFF)
                    out.append(value & 0xFF)
                elif mode == "immediate":
                    if length == 2:
                        out.append(value & 0xFF)
                    else:
                        out.append((value >> 8) & 0xFF)
                        out.append(value & 0xFF)
            pc += size
        return origin, bytes(out), dict(self.symbols)


def to_s19(origin: int, data: bytes, *, record_size: int = 32) -> str:
    """Motorola S-record (S19), as sim68xx's ``load_file``/real EPROM burners expect."""

    def record(kind: str, address: int, payload: bytes) -> str:
        addr_bytes = address.to_bytes(2, "big")
        body = addr_bytes + payload
        count = len(body) + 1  # + the checksum byte
        checksum = ~(count + sum(body)) & 0xFF
        return f"S{kind}{count:02X}{body.hex().upper()}{checksum:02X}"

    lines = []
    for offset in range(0, len(data), record_size):
        chunk = data[offset : offset + record_size]
        lines.append(record("1", origin + offset, chunk))
    lines.append(record("9", 0, b""))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="raw binary output path")
    parser.add_argument("-s", "--s19", type=Path, help="Motorola S19 output path")
    parser.add_argument("--symbols", action="store_true", help="print the symbol table")
    args = parser.parse_args(argv)
    source = args.source.read_text()
    origin, data, symbols = Assembler().assemble(source)
    if args.output:
        args.output.write_bytes(data)
    if args.s19:
        args.s19.write_text(to_s19(origin, data))
    if args.symbols:
        for name, value in sorted(symbols.items(), key=lambda kv: kv[1]):
            print(f"{value:04X} {name}")
    if not args.output and not args.s19:
        print(f"origin=${origin:04X} length={len(data)}")


if __name__ == "__main__":
    main()
