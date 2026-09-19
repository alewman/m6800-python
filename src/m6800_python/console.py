"""Portable command debugger: a thin text frontend over :class:`DebugSession`.

``CommandDebugger.execute(line)`` runs one command and returns printable lines;
``interact(input, output)`` is a line-oriented loop with no terminal
dependencies.  ``python -m m6800_python`` starts one on a ROM or binary
(docs/debug-session.md).
"""

import shlex
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import ClassVar, TextIO

from m6800_python._undocumented import UndocumentedOpcode
from m6800_python.debug import DebugSession, RunResult, StepRecord, StopReason
from m6800_python.disasm import ByteReader, Instruction, disassemble
from m6800_python.state import CPUState


class CommandError(ValueError):
    """A malformed or unsupported debugger command."""


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Rendered lines and whether the loop should end."""

    lines: tuple[str, ...] = ()
    quit: bool = False


_HELP = (
    "help                          Show this summary",
    "registers | regs | r          Show the registers, flags and interrupt state",
    "step [COUNT] | s              Execute one or more boundaries (ignores breakpoints)",
    "over | o                      Step, running a JSR/BSR through to its return",
    "run STEPS [CYCLES] | continue Run until a stop condition (continue = 1,000,000 steps)",
    "break ADDRESS | b             Add an execute breakpoint",
    "delete ADDRESS                Remove an execute breakpoint",
    "breakpoints                   List breakpoints and watchpoints",
    "watch ADDRESS [r|w|rw]        Stop after a step that touches ADDRESS",
    "unwatch ADDRESS               Remove a watchpoint",
    "disassemble [ADDRESS] [COUNT] | d   List instructions (default: from PC, 8)",
    "memory ADDRESS [LENGTH] | m   Show up to 256 bytes",
    "history [COUNT]               Show retained step records",
    "set REGISTER VALUE            Set A, B, D, X, SP, PC or CC",
    "irq on|off | nmi | reset      Drive the IRQ line, pulse NMI, or reset the CPU",
    "quit | exit | q               Leave",
    "Addresses and values are hex (1234, $1234, 0x1234; #123 is decimal);",
    "counts (step, run, history, lengths) are decimal ($ or 0x makes them hex).",
)

_REGISTERS = {
    "A": 0xFF,
    "B": 0xFF,
    "D": 0xFFFF,
    "X": 0xFFFF,
    "SP": 0xFFFF,
    "PC": 0xFFFF,
    "CC": 0xFF,
}


def parse_number(
    text: str, name: str = "value", *, maximum: int | None = None, decimal: bool = False
) -> int:
    """Parse an address or value (hex by default: ``1234``, ``$1234``, ``0x1234``;
    ``#123`` is decimal) or, with ``decimal=True``, a count (decimal by default;
    ``$`` or ``0x`` makes it hex)."""
    try:
        if text.startswith("#"):
            value = int(text[1:], 10)
        elif text.startswith(("$", "0x", "0X")):
            value = int(text.removeprefix("$").removeprefix("0x").removeprefix("0X"), 16)
        else:
            value = int(text, 10 if decimal else 16)
    except ValueError as exc:
        raise CommandError(f"{name} must be a number, not {text!r}") from exc
    if value < 0 or (maximum is not None and value > maximum):
        raise CommandError(f"{name} must be in range 0..{maximum}")
    return value


def _positive(text: str, name: str, *, maximum: int | None = None) -> int:
    """A count: decimal unless written with $ or 0x."""
    value = parse_number(text, name, maximum=maximum, decimal=True)
    if value == 0:
        raise CommandError(f"{name} must be positive")
    return value


def format_flags(cc: int) -> str:
    """CC as Motorola's H I N Z V C, a letter for each bit set."""
    return "".join(letter if cc & (0x20 >> n) else "-" for n, letter in enumerate("HINZVC"))


def format_state(state: CPUState, part: int = 6800) -> tuple[str, ...]:
    d = f" D={state.d:04X}" if part != 6800 else ""
    irq2 = f" IRQ2={state.irq2:04X}" if state.irq2 is not None else ""
    return (
        f"A={state.a:02X} B={state.b:02X}{d} X={state.x:04X} SP={state.sp:04X} "
        f"PC={state.pc:04X} CC={state.cc:02X} {format_flags(state.cc)}",
        f"IRQ={int(state.irq)} NMI={int(state.nmi)}{irq2} WAI={int(state.waiting)} "
        f"HCF={int(state.halted)} INHIBIT={int(state.irq_inhibit)}",
    )


def format_instruction(instruction: Instruction) -> str:
    encoded = " ".join(f"{value:02X}" for value in instruction.data)
    note = "" if instruction.documented else "   ; undocumented"
    return f"{instruction.address:04X}  {encoded:<11} {instruction.text}{note}"


def format_record(record: StepRecord) -> str:
    if record.instruction is not None:
        work = format_instruction(record.instruction)
    else:
        work = f"{record.before.pc:04X}  <{record.kind.value}>"
    return f"#{record.sequence} {work:<40} -> PC={record.after.pc:04X} +{record.cycles}"


def format_run(result: RunResult) -> tuple[str, ...]:
    lines = [
        f"stopped: {result.reason.value}, {result.steps} steps, {result.instructions} "
        f"instructions, {result.cycles} cycles, PC={result.state.pc:04X}"
    ]
    if result.reason is StopReason.WATCHPOINT:
        lines += [f"  {kind} ${address:04X} = ${value:02X}" for kind, address, value in result.hits]
    if result.error is not None:
        lines.append(f"  {result.error}")
    return tuple(lines)


class CommandDebugger:
    """Parse and execute debugger commands against a :class:`DebugSession`."""

    def __init__(
        self,
        session: DebugSession,
        *,
        commands: Mapping[str, tuple[Callable[[list[str]], Iterable[str]], str]] | None = None,
    ) -> None:
        """``commands`` adds host commands: ``name -> (handler, help line)``.
        A handler takes the argument words, returns printable lines, and
        raises :class:`CommandError` for bad input.  Host commands may not
        replace built-in ones."""
        if type(session) is not DebugSession:
            raise TypeError("session must be a DebugSession")
        self.session = session
        self.host_commands = dict(commands or {})
        clashes = sorted(set(self.host_commands) & set(self._COMMANDS))
        if clashes:
            raise ValueError(f"host commands clash with built-ins: {', '.join(clashes)}")

    def execute(self, command: str) -> CommandResult:
        """Execute one command and return deterministic printable lines."""
        try:
            words = shlex.split(command)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        if not words:
            return CommandResult()
        name, *arguments = words
        name = name.lower()
        handler = self._COMMANDS.get(name)
        if handler is not None:
            return handler(self, name, arguments)
        if name in self.host_commands:
            return CommandResult(tuple(self.host_commands[name][0](arguments)))
        raise CommandError(f"unknown command: {name} (try help)")

    def interact(self, input_stream: TextIO, output_stream: TextIO, *, prompt: str = "") -> None:
        """Run a line-oriented loop over the given streams until quit or end of input."""
        prompt = prompt or f"m{self.session.part}> "
        while True:
            output_stream.write(prompt)
            output_stream.flush()
            line = input_stream.readline()
            if line == "":
                return
            try:
                result = self.execute(line)
            except (CommandError, ValueError, UndocumentedOpcode) as exc:
                output_stream.write(f"error: {exc}\n")
                continue
            for rendered in result.lines:
                output_stream.write(f"{rendered}\n")
            if result.quit:
                return

    # -- commands ----------------------------------------------------------

    def _quit(self, name, arguments):
        _arity(name, arguments, 0)
        return CommandResult(quit=True)

    def _help(self, name, arguments):
        _arity(name, arguments, 0)
        extra = tuple(line for _, line in self.host_commands.values())
        return CommandResult(_HELP + (("Host commands:", *extra) if extra else ()))

    def _registers(self, name, arguments):
        _arity(name, arguments, 0)
        return CommandResult(format_state(self.session.target.capture_state(), self.session.part))

    def _step(self, name, arguments):
        _arity(name, arguments, 0, 1)
        count = _positive(arguments[0], "count", maximum=0x10000) if arguments else 1
        lines = []
        for _ in range(count):
            try:
                lines.append(format_record(self.session.step()))
            except UndocumentedOpcode as exc:
                lines.append(f"stopped: {exc}")
                break
        return CommandResult(tuple(lines))

    def _over(self, name, arguments):
        _arity(name, arguments, 0)
        state = self.session.target.capture_state()
        peek = self._peek()
        instruction = disassemble(
            peek, state.pc, part=self.session.part, undocumented=self.session.undocumented
        )
        if instruction.mnemonic not in ("JSR", "BSR"):
            return self._step("step", [])
        # Run the call through: stop when control is back at the instruction
        # after it with the stack where it was.
        record = self.session.step()
        lines = [format_record(record)]
        target = instruction.next_address
        for _ in range(1_000_000):
            now = self.session.target.capture_state()
            if now.pc == target and now.sp == state.sp:
                break
            if now.pc in self.session.breakpoints:
                lines.append(f"breakpoint at {now.pc:04X}")
                break
            result = self.session.run(max_steps=1)
            if result.reason is not StopReason.STEP_LIMIT:
                lines += format_run(result)
                break
        else:
            lines.append("gave up after 1,000,000 steps")
        return CommandResult(
            (*lines, *format_state(self.session.target.capture_state(), self.session.part))
        )

    def _run(self, name, arguments):
        if name in ("continue", "c"):
            _arity(name, arguments, 0)
            steps, cycles = 1_000_000, None
        else:
            _arity(name, arguments, 1, 2)
            steps = _positive(arguments[0], "steps")
            cycles = _positive(arguments[1], "cycles") if len(arguments) == 2 else None
        return CommandResult(format_run(self.session.run(max_steps=steps, max_cycles=cycles)))

    def _break(self, name, arguments):
        _arity(name, arguments, 1)
        address = parse_number(arguments[0], "address", maximum=0xFFFF)
        self.session.add_breakpoint(address)
        return CommandResult((f"breakpoint at {address:04X}",))

    def _delete(self, name, arguments):
        _arity(name, arguments, 1)
        address = parse_number(arguments[0], "address", maximum=0xFFFF)
        self.session.remove_breakpoint(address)
        return CommandResult((f"breakpoint at {address:04X} removed",))

    def _breakpoints(self, name, arguments):
        _arity(name, arguments, 0)
        lines = [f"break {address:04X}" for address in sorted(self.session.breakpoints)]
        lines += [
            f"watch {address:04X} {kind}"
            for address, kind in sorted(self.session.watchpoints.items())
        ]
        return CommandResult(tuple(lines) or ("no breakpoints or watchpoints",))

    def _watch(self, name, arguments):
        _arity(name, arguments, 1, 2)
        address = parse_number(arguments[0], "address", maximum=0xFFFF)
        kind = arguments[1].lower() if len(arguments) == 2 else "rw"
        self.session.add_watchpoint(address, kind)
        return CommandResult((f"watch {address:04X} {kind}",))

    def _unwatch(self, name, arguments):
        _arity(name, arguments, 1)
        address = parse_number(arguments[0], "address", maximum=0xFFFF)
        self.session.remove_watchpoint(address)
        return CommandResult((f"watch {address:04X} removed",))

    def _disassemble(self, name, arguments):
        _arity(name, arguments, 0, 2)
        peek = self._peek()
        state = self.session.target.capture_state()
        address = parse_number(arguments[0], "address", maximum=0xFFFF) if arguments else state.pc
        count = _positive(arguments[1], "count", maximum=256) if len(arguments) == 2 else 8
        lines = []
        for _ in range(count):
            instruction = disassemble(
                peek, address, part=self.session.part, undocumented=self.session.undocumented
            )
            marker = (
                ">" if address == state.pc else "*" if address in self.session.breakpoints else " "
            )
            lines.append(f"{marker} {format_instruction(instruction)}")
            address = instruction.next_address
        return CommandResult(tuple(lines))

    def _memory(self, name, arguments):
        _arity(name, arguments, 1, 2)
        peek = self._peek()
        address = parse_number(arguments[0], "address", maximum=0xFFFF)
        length = _positive(arguments[1], "length", maximum=256) if len(arguments) == 2 else 64
        lines = []
        for offset in range(0, length, 16):
            row = (address + offset) & 0xFFFF
            values = [peek((row + n) & 0xFFFF) for n in range(min(16, length - offset))]
            text = "".join(chr(v) if 0x20 <= v < 0x7F else "." for v in values)
            lines.append(f"{row:04X}  {' '.join(f'{v:02X}' for v in values):<47}  {text}")
        return CommandResult(tuple(lines))

    def _history(self, name, arguments):
        _arity(name, arguments, 0, 1)
        count = _positive(arguments[0], "count", maximum=0x10000) if arguments else 16
        records = self.session.history[-count:]
        return CommandResult(tuple(format_record(r) for r in records) or ("history empty",))

    def _set(self, name, arguments):
        _arity(name, arguments, 2)
        register = arguments[0].upper()
        if register not in _REGISTERS or (register == "D" and self.session.part == 6800):
            raise CommandError(f"no register {register} on the MC{self.session.part}")
        value = parse_number(arguments[1], register, maximum=_REGISTERS[register])
        cpu = self.session.cpu
        if register == "D":
            cpu.A, cpu.B = value >> 8, value & 0xFF
        elif register == "CC":
            cpu.CC = value | 0xC0
        else:
            setattr(cpu, register, value)
        return CommandResult(format_state(cpu.capture_state(), self.session.part))

    def _irq(self, name, arguments):
        _arity(name, arguments, 1)
        level = arguments[0].lower()
        if level not in ("on", "off"):
            raise CommandError("irq takes on or off")
        self.session.cpu.irq = level == "on"
        return CommandResult((f"IRQ line {'asserted' if level == 'on' else 'released'}",))

    def _nmi(self, name, arguments):
        _arity(name, arguments, 0)
        self.session.cpu.pulse_nmi()
        return CommandResult(("NMI edge latched; taken at the next step",))

    def _reset(self, name, arguments):
        _arity(name, arguments, 0)
        self.session.cpu.reset()
        return CommandResult(format_state(self.session.target.capture_state(), self.session.part))

    def _peek(self) -> ByteReader:
        if self.session.peek_byte is None:
            raise CommandError("this session has no side-effect-free peek")
        return self.session.peek_byte

    _COMMANDS: ClassVar[dict] = {
        "quit": _quit,
        "exit": _quit,
        "q": _quit,
        "help": _help,
        "?": _help,
        "registers": _registers,
        "regs": _registers,
        "r": _registers,
        "step": _step,
        "s": _step,
        "over": _over,
        "o": _over,
        "run": _run,
        "continue": _run,
        "c": _run,
        "break": _break,
        "b": _break,
        "delete": _delete,
        "breakpoints": _breakpoints,
        "watch": _watch,
        "unwatch": _unwatch,
        "disassemble": _disassemble,
        "disasm": _disassemble,
        "d": _disassemble,
        "memory": _memory,
        "m": _memory,
        "history": _history,
        "set": _set,
        "irq": _irq,
        "nmi": _nmi,
        "reset": _reset,
    }


def _arity(name: str, arguments: list[str], minimum: int, maximum: int | None = None) -> None:
    maximum = minimum if maximum is None else maximum
    if not minimum <= len(arguments) <= maximum:
        expected = str(minimum) if minimum == maximum else f"{minimum}..{maximum}"
        raise CommandError(f"{name} takes {expected} argument(s)")


__all__ = [
    "CommandDebugger",
    "CommandError",
    "CommandResult",
    "format_flags",
    "format_instruction",
    "format_record",
    "format_state",
    "parse_number",
]
