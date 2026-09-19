"""Traces: JSON Lines round trips and divergence finding."""

from __future__ import annotations

import io
import json

import pytest
from conftest import make

from m6800_python import (
    DebugSession,
    first_trace_divergence,
    iter_session_steps,
    read_trace,
    write_trace,
)

PROGRAM = [0x86, 0x05, 0x8B, 0x03, 0xB7, 0x20, 0x00, 0x20, 0xF7]  # a small loop


def records(part: str = "6800", *, a: int = 0, track: bool = True, program=PROGRAM, n=12):
    cpu, bus = make(part, program, undocumented="mame")
    cpu.A = a
    session = DebugSession(cpu, peek_byte=bus.memory.__getitem__, track_accesses=track)
    return list(iter_session_steps(session, max_steps=n))


def test_round_trip(part: str) -> None:
    original = records(part)
    stream = io.StringIO()
    assert write_trace(original, stream) == len(original)
    stream.seek(0)
    back = list(read_trace(stream, part=part))
    assert back == original


def test_lines_are_sorted_compact_json() -> None:
    stream = io.StringIO()
    write_trace(records()[:1], stream)
    line = stream.getvalue().splitlines()[0]
    data = json.loads(line)
    assert line == json.dumps(data, sort_keys=True, separators=(",", ":"))
    assert data["version"] == 1 and data["instruction"]["data"] == "8605"


def test_first_divergence_names_the_field() -> None:
    left = records(program=[0x86, 0x05, 0x01])
    right = records(program=[0x86, 0x06, 0x01])
    divergence = first_trace_divergence(left, right)
    assert divergence.position == 0
    paths = {d.path for d in divergence.differences}
    assert {"instruction.data", "after.a"} <= paths
    assert first_trace_divergence(records(), records()) is None


def test_length_mismatch() -> None:
    divergence = first_trace_divergence(records(n=3), records(n=4))
    assert divergence.position == 3 and divergence.differences[0].path == "record"


def test_undocumented_bytes_decode_under_any_policy() -> None:
    # A strict-mode FCB record is one byte, MAME's reading of $61 is two:
    # the reader accepts whichever policy decodes exactly the recorded bytes.
    line = records(program=[0x01], n=1)
    stream = io.StringIO()
    write_trace(line, stream)
    data = json.loads(stream.getvalue())
    data["instruction"] = {"address": 0x1000, "data": "02"}
    back = list(read_trace(io.StringIO(json.dumps(data) + "\n")))
    assert back[0].instruction.text == "FCB $02"


def test_malformed_records_are_rejected() -> None:
    with pytest.raises(ValueError, match="line 1"):
        list(read_trace(io.StringIO('{"version": 2}\n')))
