"""Conformance kit: run a manifest on the reference core, or diff a foreign trace against it.

A **manifest** is a small JSON document that fully determines a run: which part
is running and under which undocumented-opcode policy, what is in memory, the
initial processor state, when the host's interrupt inputs change, and when to
stop. Two cores given the same manifest see the same machine, so any difference
between their traces is a difference between the CPUs. The trace format itself
is ``docs/trace-schema.md``; this module is the part that makes traces
comparable, and docs/conformance.md is the contract a port implements.

Three entry points, also exposed as ``python -m m6800_python.conformance``:

* :func:`trace_manifest` runs the manifest on the reference core and yields one
  :class:`StepRecord` per boundary.
* :func:`diff_manifest` runs the same manifest in lockstep against an external
  trace and returns the first :class:`TraceDivergence`, or ``None``.
* :func:`write_checkpoints` runs the manifest without records and writes a
  manifest that resumes it every N boundaries, so a long run can be diffed as
  independent segments in parallel.

The module depends only on the standard library and the rest of this package.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import TextIO

from m6800_python._undocumented import POLICIES, UndocumentedOpcode
from m6800_python.cpu import M6800, M6803
from m6800_python.debug import BoundaryKind, DebugSession, StepRecord, next_boundary
from m6800_python.state import CPUState
from m6800_python.trace import TraceDivergence, first_trace_divergence, read_trace, write_trace

__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "ConformanceHost",
    "Event",
    "Manifest",
    "MemorySegment",
    "StopRule",
    "TraceRun",
    "diff_manifest",
    "load_manifest",
    "main",
    "manifest_from_dict",
    "manifest_to_dict",
    "trace_manifest",
    "write_checkpoints",
]

MANIFEST_SCHEMA_VERSION = 1

#: Host profiles. Only ``flat``: 64 KiB RAM and no ports. The 6800 family has
#: no I/O space -- a port is memory to this CPU -- and there is no CP/M here,
#: so z80-python's ``cpm-minimal`` profile has no counterpart.
HOST_PROFILES = ("flat",)

#: The parts a manifest may name. ``6800`` covers the MC6802 and MC6808, which
#: share its instruction set; ``6803`` covers the MC6801.
PARTS = {"6800": M6800, "6803": M6803}

#: Events, applied immediately before the boundary they name. ``irq`` and
#: ``nmi`` set a level and the core edge-detects NMI itself; ``pulse_nmi``
#: latches an edge directly; ``irq2`` carries the vector address of the
#: highest-priority on-chip request and is a 6803-only event; ``reset`` calls
#: ``reset()``, there being no reset line to hold on this family.
EVENT_KINDS = (
    "irq",
    "irq_clear",
    "nmi",
    "nmi_clear",
    "pulse_nmi",
    "irq2",
    "irq2_clear",
    "reset",
)


@dataclass(frozen=True, slots=True)
class MemorySegment:
    """Bytes to place at ``address`` before the run starts."""

    address: int
    data: bytes

    def __post_init__(self) -> None:
        if type(self.address) is not int or not 0 <= self.address <= 0xFFFF:
            raise ValueError("segment address must be an integer in range 0x0000..0xFFFF")
        if type(self.data) is not bytes or not self.data:
            raise ValueError("segment data must be non-empty bytes")
        if self.address + len(self.data) > 0x10000:
            raise ValueError("segment does not fit below 0x10000")


@dataclass(frozen=True, slots=True)
class Event:
    """A host request applied immediately before boundary ``at_step``.

    Steps count every record, instruction or lifecycle boundary, from 0. The
    request is made through the public API, so the boundary at ``at_step`` is
    the first that can observe it. ``vector`` is required by ``irq2`` and
    ignored by every other kind.
    """

    at_step: int
    kind: str
    vector: int | None = None

    def __post_init__(self) -> None:
        if type(self.at_step) is not int or self.at_step < 0:
            raise ValueError("event at_step must be a non-negative integer")
        if self.kind not in EVENT_KINDS:
            raise ValueError(f"event kind must be one of {EVENT_KINDS}, got {self.kind!r}")
        if self.kind == "irq2":
            if type(self.vector) is not int or not 0 <= self.vector <= 0xFFFF:
                raise ValueError("an irq2 event needs vector, an address in 0x0000..0xFFFF")
        elif self.vector is not None:
            raise ValueError(f"an {self.kind} event takes no vector")


@dataclass(frozen=True, slots=True)
class StopRule:
    """When the run ends. ``max_steps`` is mandatory, so every run is finite.

    The run stops *before* a boundary when the step budget is spent, when PC
    equals one of ``at_pc``, when the next boundary would be ``WAIT_IDLE`` with
    nothing pending and no event left (``on_wait``), or when it would be
    ``HCF_IDLE`` (``on_hcf``). A stopped run's trace ends; the boundary that
    would have followed is not recorded.
    """

    max_steps: int
    at_pc: tuple[int, ...] = ()
    on_wait: bool = True
    on_hcf: bool = True

    def __post_init__(self) -> None:
        if type(self.max_steps) is not int or self.max_steps <= 0:
            raise ValueError("stop.max_steps must be a positive integer")
        for name in ("on_wait", "on_hcf"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"stop.{name} must be a bool")
        if type(self.at_pc) is not tuple or not all(
            type(pc) is int and 0 <= pc <= 0xFFFF for pc in self.at_pc
        ):
            raise ValueError("stop.at_pc must be a tuple of 16-bit addresses")


@dataclass(frozen=True, slots=True)
class Manifest:
    """A complete, deterministic description of one conformance run."""

    name: str
    part: str
    undocumented: str
    memory: tuple[MemorySegment, ...]
    initial: CPUState
    stop: StopRule
    host: str = "flat"
    events: tuple[Event, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if type(self.name) is not str or not self.name:
            raise ValueError("manifest name must be a non-empty string")
        if self.part not in PARTS:
            raise ValueError(f"manifest part must be one of {sorted(PARTS)}, got {self.part!r}")
        if self.undocumented not in POLICIES:
            raise ValueError(
                f"manifest undocumented must be one of {sorted(POLICIES)}, "
                f"got {self.undocumented!r}"
            )
        if type(self.memory) is not tuple or not all(
            type(segment) is MemorySegment for segment in self.memory
        ):
            raise ValueError("manifest memory must be a tuple of MemorySegment values")
        if type(self.initial) is not CPUState:
            raise ValueError("manifest initial must be a CPUState")
        if type(self.stop) is not StopRule:
            raise ValueError("manifest stop must be a StopRule")
        if self.host not in HOST_PROFILES:
            raise ValueError(f"manifest host must be one of {HOST_PROFILES}, got {self.host!r}")
        if type(self.events) is not tuple or not all(type(event) is Event for event in self.events):
            raise ValueError("manifest events must be a tuple of Event values")
        steps = [event.at_step for event in self.events]
        if steps != sorted(steps):
            raise ValueError("manifest events must be ordered by at_step")
        if self.part == "6800":
            for event in self.events:
                if event.kind in ("irq2", "irq2_clear"):
                    raise ValueError(
                        f"a {event.kind} event is 6803-only; the MC6800 has no on-chip "
                        f"interrupt sources (event at_step {event.at_step})"
                    )
            if self.initial.irq2 is not None:
                raise ValueError("initial.irq2 must be null on a 6800 manifest")


class ConformanceHost:
    """The one host every conformance run uses, so hosts cannot differ between cores.

    Flat 64 KiB RAM, nothing else: no ports, and no traps. The CPU is the part
    the manifest names, built with its undocumented-opcode policy, and is
    exposed as :attr:`cpu` so a :class:`DebugSession` tracks its bus. The host
    drives it, which is what makes this a board target rather than a CPU.
    """

    def __init__(self, manifest: Manifest) -> None:
        self.memory = bytearray(0x10000)
        for segment in manifest.memory:
            self.memory[segment.address : segment.address + len(segment.data)] = segment.data
        self.cpu = PARTS[manifest.part](
            self.memory.__getitem__,
            self.memory.__setitem__,
            undocumented=manifest.undocumented,
        )
        self.cpu.restore_state(manifest.initial)

    def step(self) -> int:
        """One boundary on the CPU; no devices to settle, this host having none."""
        return self.cpu.step()

    def capture_state(self) -> CPUState:
        return self.cpu.capture_state()

    def peek_byte(self, addr: int) -> int:
        """Side-effect-free read for disassembly (identical to the bus read here)."""
        return self.memory[addr & 0xFFFF]


@dataclass(frozen=True, slots=True)
class TraceRun:
    """Why a reference run ended, and what it cost."""

    steps: int
    cycles: int
    reason: str
    #: Set when ``reason`` is ``undocumented_opcode``: what the core refused.
    detail: str = ""


class _Stop:
    """Why :func:`_boundaries` stopped; filled in when the generator ends."""

    reason = "max_steps"
    detail = ""


def _boundaries(manifest: Manifest, host: ConformanceHost, stopped: _Stop) -> Iterator[int]:
    """Yield the index of every boundary the run executes, in order.

    Before each index the events due at it are applied, then the stop checks
    run in this order: ``at_pc``, ``on_wait``, ``on_hcf``, the step budget. The
    caller performs the boundary itself, so a traced run and a checkpoint run
    cannot drift apart.
    """
    events = list(manifest.events)
    stop = manifest.stop
    steps = 0
    while steps < stop.max_steps:
        while events and events[0].at_step == steps:
            _apply_event(host, events.pop(0))
        state = host.capture_state()
        if state.pc in stop.at_pc:
            stopped.reason = "at_pc"
            return
        kind = next_boundary(state)
        if stop.on_wait and kind is BoundaryKind.WAIT_IDLE and not events:
            stopped.reason = "waiting"
            return
        if stop.on_hcf and kind is BoundaryKind.HCF_IDLE:
            stopped.reason = "halted"
            return
        yield steps
        steps += 1
    stopped.reason = "max_steps"


def trace_manifest(
    manifest: Manifest, *, result: list[TraceRun] | None = None
) -> Iterator[StepRecord]:
    """Run ``manifest`` on the reference core, yielding one record per boundary.

    Records are produced lazily, so a long run can be written or compared
    without buffering. When the iterator is exhausted a :class:`TraceRun` is
    appended to ``result`` if one is supplied.

    Under ``undocumented="strict"`` an unassigned opcode ends the run with
    reason ``undocumented_opcode`` and the opcode in ``TraceRun.detail``; it is
    a result here, not an error, and the trace simply has no record for the
    boundary that did not happen.
    """
    host = ConformanceHost(manifest)
    session = DebugSession(host, peek_byte=host.peek_byte, history_limit=0)
    stopped = _Stop()
    steps = 0
    for index in _boundaries(manifest, host, stopped):
        try:
            record = session.step()
        except UndocumentedOpcode as refused:
            stopped.reason = "undocumented_opcode"
            stopped.detail = str(refused)
            break
        yield record
        steps = index + 1
    if result is not None:
        result.append(TraceRun(steps, session.total_cycles, stopped.reason, stopped.detail))


def write_checkpoints(
    manifest: Manifest,
    every: int,
    directory: str | Path,
    *,
    result: list[TraceRun] | None = None,
) -> list[Path]:
    """Run ``manifest`` without records, writing a resuming manifest every ``every`` boundaries.

    Each checkpoint carries the full 64 KiB as a ``file`` segment beside it,
    every ``CPUState`` field as ``initial``, and ``max_steps`` of ``every``, so
    diffing the checkpoints in parallel proves what one lockstep run proves:
    each segment starts in the state the previous one ended in.

    Manifests with ``events`` are refused, because their ``at_step`` values
    would have to be shifted into each segment.
    """
    if type(every) is not int or every <= 0:
        raise ValueError("every must be a positive integer")
    if manifest.events:
        raise ValueError("checkpoints are not supported for manifests with events")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    host = ConformanceHost(manifest)
    stopped = _Stop()
    paths: list[Path] = []
    steps = 0
    cycles = 0
    for index in _boundaries(manifest, host, stopped):
        if index % every == 0:
            paths.append(_write_checkpoint(manifest, host, index, every, directory))
        try:
            cycles += host.step()
        except UndocumentedOpcode as refused:
            stopped.reason = "undocumented_opcode"
            stopped.detail = str(refused)
            break
        steps = index + 1
    if result is not None:
        result.append(TraceRun(steps, cycles, stopped.reason, stopped.detail))
    return paths


def _write_checkpoint(
    manifest: Manifest, host: ConformanceHost, at_step: int, every: int, directory: Path
) -> Path:
    stem = f"{manifest.name}-{at_step:012d}"
    (directory / f"{stem}.mem").write_bytes(bytes(host.memory))
    state = host.capture_state()
    document = {
        "version": MANIFEST_SCHEMA_VERSION,
        "name": stem,
        "part": manifest.part,
        "undocumented": manifest.undocumented,
        "host": manifest.host,
        "memory": [{"address": 0, "file": f"{stem}.mem"}],
        "initial": {name: getattr(state, name) for name in _STATE_FIELD_NAMES},
        "events": [],
        "stop": {
            "max_steps": every,
            "at_pc": list(manifest.stop.at_pc),
            "on_wait": manifest.stop.on_wait,
            "on_hcf": manifest.stop.on_hcf,
        },
    }
    path = directory / f"{stem}.json"
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


def diff_manifest(manifest: Manifest, external: Iterable[StepRecord]) -> TraceDivergence | None:
    """Run the reference in lockstep against ``external`` and return the first divergence."""
    return first_trace_divergence(trace_manifest(manifest), external)


def _apply_event(host: ConformanceHost, event: Event) -> None:
    cpu = host.cpu
    if event.kind == "irq":
        cpu.irq = True
    elif event.kind == "irq_clear":
        cpu.irq = False
    elif event.kind == "nmi":
        cpu.nmi = True
    elif event.kind == "nmi_clear":
        cpu.nmi = False
    elif event.kind == "pulse_nmi":
        cpu.pulse_nmi()
    elif event.kind == "irq2":
        cpu.irq2 = event.vector
    elif event.kind == "irq2_clear":
        cpu.irq2 = None
    else:
        cpu.reset()


# --- manifest serialization --------------------------------------------------


def manifest_to_dict(manifest: Manifest) -> dict[str, object]:
    """Return the versioned JSON-compatible form of a manifest."""
    if type(manifest) is not Manifest:
        raise TypeError("manifest must be a Manifest")
    return {
        "version": MANIFEST_SCHEMA_VERSION,
        "name": manifest.name,
        "part": manifest.part,
        "undocumented": manifest.undocumented,
        "host": manifest.host,
        "memory": [
            {"address": segment.address, "data": segment.data.hex()} for segment in manifest.memory
        ],
        "initial": {name: getattr(manifest.initial, name) for name in _STATE_FIELD_NAMES},
        "events": [
            {"at_step": event.at_step, "kind": event.kind}
            | ({} if event.vector is None else {"vector": event.vector})
            for event in manifest.events
        ],
        "stop": {
            "max_steps": manifest.stop.max_steps,
            "at_pc": list(manifest.stop.at_pc),
            "on_wait": manifest.stop.on_wait,
            "on_hcf": manifest.stop.on_hcf,
        },
    }


def manifest_from_dict(value: object, *, base_dir: Path | None = None) -> Manifest:
    """Build a validated manifest from its JSON form.

    ``initial`` may list any subset of CPUState fields; the rest take their
    defaults (CC = 0xD0, the opcode history odd, everything else zero or
    false). A memory segment carries either ``data`` (hex) or ``file`` (a path
    relative to ``base_dir``, with optional ``offset`` and ``length``).
    """
    root = _object(value, "manifest")
    _allowed(
        root,
        "manifest",
        {"version", "name", "part", "undocumented", "host", "memory", "initial", "events", "stop"},
        required={"version", "name", "part", "undocumented", "memory", "stop"},
    )
    if root["version"] != MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"unsupported manifest version: {root['version']!r}")
    memory = tuple(
        _segment(_object(item, f"memory[{index}]"), index, base_dir)
        for index, item in enumerate(_list(root["memory"], "memory"))
    )
    initial_dict = _object(root.get("initial", {}), "initial")
    _allowed(initial_dict, "initial", set(_STATE_FIELD_NAMES), required=set())
    try:
        initial = CPUState(**initial_dict)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid initial state: {exc}") from exc
    stop_dict = _object(root["stop"], "stop")
    _allowed(stop_dict, "stop", {"max_steps", "at_pc", "on_wait", "on_hcf"}, required={"max_steps"})
    at_pc = _list(stop_dict.get("at_pc", []), "stop.at_pc")
    events = tuple(
        _event(_object(item, f"events[{index}]"), index)
        for index, item in enumerate(_list(root.get("events", []), "events"))
    )
    try:
        return Manifest(
            name=root["name"],
            part=root["part"],
            undocumented=root["undocumented"],
            memory=memory,
            initial=initial,
            stop=StopRule(
                max_steps=stop_dict["max_steps"],
                at_pc=tuple(at_pc),
                on_wait=stop_dict.get("on_wait", True),
                on_hcf=stop_dict.get("on_hcf", True),
            ),
            host=root.get("host", "flat"),
            events=events,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid manifest: {exc}") from exc


def load_manifest(path: str | Path) -> Manifest:
    """Read and validate a manifest file; ``file`` segments resolve beside it."""
    path = Path(path)
    with path.open(encoding="utf-8") as handle:
        try:
            value = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: not valid JSON: {exc}") from exc
    return manifest_from_dict(value, base_dir=path.parent)


_STATE_FIELD_NAMES = tuple(item.name for item in fields(CPUState))


def _segment(item: dict[str, object], index: int, base_dir: Path | None) -> MemorySegment:
    name = f"memory[{index}]"
    _allowed(item, name, {"address", "data", "file", "offset", "length"}, required={"address"})
    if ("data" in item) == ("file" in item):
        raise ValueError(f"{name} must have exactly one of 'data' or 'file'")
    if "data" in item:
        if type(item["data"]) is not str:
            raise ValueError(f"{name}.data must be a hexadecimal string")
        try:
            data = bytes.fromhex(item["data"])
        except ValueError as exc:
            raise ValueError(f"{name}.data must be a hexadecimal string") from exc
    else:
        if type(item["file"]) is not str:
            raise ValueError(f"{name}.file must be a path string")
        file_path = Path(item["file"])
        if not file_path.is_absolute():
            file_path = (base_dir or Path.cwd()) / file_path
        data = file_path.read_bytes()
        offset = item.get("offset", 0)
        length = item.get("length", len(data) - offset)
        if type(offset) is not int or type(length) is not int or offset < 0 or length <= 0:
            raise ValueError(f"{name}.offset/length must be non-negative/positive integers")
        data = data[offset : offset + length]
    try:
        return MemorySegment(item["address"], data)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}: {exc}") from exc


def _event(item: dict[str, object], index: int) -> Event:
    name = f"events[{index}]"
    _allowed(item, name, {"at_step", "kind", "vector"}, required={"at_step", "kind"})
    try:
        return Event(item["at_step"], item["kind"], item.get("vector"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}: {exc}") from exc


def _object(value: object, name: str) -> dict[str, object]:
    if type(value) is not dict or not all(type(key) is str for key in value):
        raise ValueError(f"{name} must be an object with string keys")
    return value


def _list(value: object, name: str) -> list[object]:
    if type(value) is not list:
        raise ValueError(f"{name} must be a list")
    return value


def _allowed(value: dict[str, object], name: str, keys: set[str], *, required: set[str]) -> None:
    unknown = sorted(set(value) - keys)
    missing = sorted(required - set(value))
    if unknown or missing:
        details = []
        if missing:
            details.append(f"missing={missing}")
        if unknown:
            details.append(f"unknown={unknown}")
        raise ValueError(f"{name} fields do not match schema ({', '.join(details)})")


# --- command line ------------------------------------------------------------


def main(argv: list[str] | None = None, *, stdout: TextIO | None = None) -> int:
    """``trace`` writes the reference trace; ``diff`` reports the first divergence;
    ``checkpoints`` writes resuming manifests for a long run.

    Exit status: 0 on success or equal traces, 1 on divergence, 2 on bad input.
    """
    out = stdout or sys.stdout
    parser = argparse.ArgumentParser(
        prog="python -m m6800_python.conformance",
        description="Run a conformance manifest on the reference core or diff a trace against it.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    trace_cmd = commands.add_parser("trace", help="write the reference trace for a manifest")
    trace_cmd.add_argument("manifest")
    trace_cmd.add_argument("--out", help="JSON Lines output path (default: stdout)")
    diff_cmd = commands.add_parser("diff", help="compare an external trace against the reference")
    diff_cmd.add_argument("manifest")
    diff_cmd.add_argument("trace", help="JSON Lines trace path, or '-' for stdin")
    checkpoints_cmd = commands.add_parser(
        "checkpoints",
        help="run without records and write a resuming manifest every N boundaries",
    )
    checkpoints_cmd.add_argument("manifest")
    checkpoints_cmd.add_argument("--every", type=int, required=True, help="boundaries per segment")
    checkpoints_cmd.add_argument("--dir", required=True, help="directory for the checkpoints")
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(args.manifest)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=out)
        return 2

    if args.command == "trace":
        result: list[TraceRun] = []
        records = trace_manifest(manifest, result=result)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as handle:
                count = write_trace(records, handle)
        else:
            count = write_trace(records, out)
        run = result[0]
        report = out if args.out else sys.stderr
        print(
            f"{manifest.name}: {count} records, {run.cycles} cycles, stopped on {run.reason}",
            file=report,
        )
        if run.detail:
            print(f"  {run.detail}", file=report)
        return 0

    if args.command == "checkpoints":
        result = []
        try:
            paths = write_checkpoints(manifest, args.every, args.dir, result=result)
        except (OSError, ValueError) as exc:
            print(f"error: {exc}", file=out)
            return 2
        run = result[0]
        print(
            f"{manifest.name}: {len(paths)} checkpoints every {args.every} boundaries "
            f"in {args.dir}; {run.steps} records, {run.cycles} cycles, "
            f"stopped on {run.reason}",
            file=out,
        )
        return 0

    try:
        if args.trace == "-":
            divergence = diff_manifest(manifest, read_trace(sys.stdin, part=manifest.part))
        else:
            with open(args.trace, encoding="utf-8") as handle:
                divergence = diff_manifest(manifest, read_trace(handle, part=manifest.part))
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=out)
        return 2
    if divergence is None:
        print(f"{manifest.name}: traces are identical", file=out)
        return 0
    record = divergence.left or divergence.right
    where = "(end of trace)"
    if record is not None:
        if record.instruction is not None:
            where = f"{record.instruction.address:04X}: {record.instruction.text}"
        else:
            where = record.kind.value
    print(f"{manifest.name}: divergence at position {divergence.position}, {where}", file=out)
    for difference in divergence.differences:
        print(
            f"  {difference.path}: reference={difference.left!r} external={difference.right!r}",
            file=out,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
