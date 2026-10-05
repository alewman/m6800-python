"""The conformance kit: manifests, the shared host, reference traces, and the differ."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from m6800_python import BoundaryKind, CPUState, read_trace, write_trace
from m6800_python.conformance import (
    Event,
    Manifest,
    MemorySegment,
    StopRule,
    diff_manifest,
    load_manifest,
    main,
    manifest_from_dict,
    manifest_to_dict,
    trace_manifest,
    write_checkpoints,
)

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "conformance"
#: Every fixture, found rather than listed, so a new one is covered by writing it.
FIXTURES = sorted(path.relative_to(EXAMPLES).as_posix() for path in EXAMPLES.rglob("*.json"))
START = 0x1000


def manifest(program: bytes, **overrides: object) -> Manifest:
    values: dict[str, object] = {
        "name": "unit",
        "part": "6800",
        "undocumented": "strict",
        "memory": (MemorySegment(START, program), MemorySegment(0xFFF8, bytes(8))),
        "initial": CPUState(pc=START, sp=0x01FF),
        "stop": StopRule(max_steps=50),
    }
    values.update(overrides)
    return Manifest(**values)  # type: ignore[arg-type]


# -- the fixtures -------------------------------------------------------------


def test_there_are_fixtures_for_every_group_the_brief_names() -> None:
    assert len(FIXTURES) >= 19, FIXTURES
    for name in (
        "flags-and-branches.json",
        "daa.json",
        "cpx-6800.json",
        "cpx-6803.json",
        "stack-frames.json",
        "undocumented-measured.json",
        "hcf-halts.json",
        "interrupts/cli-after-odd-opcode.json",
        "interrupts/irq2-priority.json",
    ):
        assert name in FIXTURES


@pytest.mark.parametrize("name", FIXTURES, ids=lambda name: name[:-5])
def test_reference_trace_regenerates_byte_identically(name: str) -> None:
    path = EXAMPLES / name
    loaded = load_manifest(path)
    stream = io.StringIO()
    write_trace(trace_manifest(loaded), stream)
    assert stream.getvalue() == path.with_suffix(".jsonl").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", FIXTURES, ids=lambda name: name[:-5])
def test_each_fixture_diffs_clean_against_its_own_trace(name: str) -> None:
    loaded = load_manifest(EXAMPLES / name)
    with (EXAMPLES / name).with_suffix(".jsonl").open(encoding="utf-8") as handle:
        assert diff_manifest(loaded, read_trace(handle, part=loaded.part)) is None


def test_the_two_cpx_fixtures_run_the_same_program_and_disagree() -> None:
    # The MC6800's CPX sets N and V from the high byte alone and leaves C; the
    # MC6803 does a true 16-bit compare. Same bytes, different trace.
    first, second = (load_manifest(EXAMPLES / f"cpx-{part}.json") for part in ("6800", "6803"))
    assert first.memory == second.memory
    traces = [
        (EXAMPLES / f"cpx-{part}.jsonl").read_text(encoding="utf-8") for part in ("6800", "6803")
    ]
    assert traces[0] != traces[1]


def test_a_perturbed_trace_is_caught_at_its_position_and_field() -> None:
    name = "flags-and-branches"
    loaded = load_manifest(EXAMPLES / f"{name}.json")
    lines = (EXAMPLES / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
    position = 7
    record = json.loads(lines[position])
    record["after"]["cc"] ^= 0x01  # flip C in one record's after state
    lines[position] = json.dumps(record, separators=(",", ":"), sort_keys=True)
    divergence = diff_manifest(loaded, read_trace(io.StringIO("\n".join(lines)), part=loaded.part))
    assert divergence is not None
    assert divergence.position == position
    assert [difference.path for difference in divergence.differences] == ["after.cc"]


# -- the host, the stop rules and the events ----------------------------------


def test_a_run_is_recorded_boundary_by_boundary() -> None:
    # LDAA #$2A; ADDA #$01; WAI
    result: list = []
    records = list(trace_manifest(manifest(bytes((0x86, 0x2A, 0x8B, 0x01, 0x3E))), result=result))
    assert [record.instruction.text for record in records] == ["LDAA #$2A", "ADDA #$01", "WAI"]
    assert [record.cycles for record in records] == [2, 2, 9]
    assert result[0].reason == "waiting"
    assert result[0].cycles == 13


def test_stop_rules() -> None:
    nops = bytes((0x01,)) * 10
    assert len(list(trace_manifest(manifest(nops, stop=StopRule(max_steps=4))))) == 4
    at_pc = StopRule(max_steps=50, at_pc=(START + 3,))
    assert len(list(trace_manifest(manifest(nops, stop=at_pc)))) == 3
    # on_hcf=False keeps recording the idle boundaries after an HCF.
    halting = bytes((0x9D,))
    assert len(list(trace_manifest(manifest(halting, stop=StopRule(max_steps=5))))) == 1
    idling = list(trace_manifest(manifest(halting, stop=StopRule(max_steps=5, on_hcf=False))))
    assert [record.kind for record in idling[1:]] == [BoundaryKind.HCF_IDLE] * 4


def test_events_reach_the_core_through_its_public_inputs() -> None:
    # CLI; NOP; NOP, with the IRQ asserted before the third boundary.
    program = bytes((0x0E, 0x01, 0x01, 0x01))
    records = list(
        trace_manifest(
            manifest(
                program,
                initial=CPUState(pc=START, sp=0x01FF, cc=0xC0),
                events=(Event(2, "irq"), Event(3, "irq_clear")),
                stop=StopRule(max_steps=6),
            )
        )
    )
    assert records[2].kind is BoundaryKind.IRQ
    assert records[2].before.irq is True


def test_an_irq2_event_is_refused_on_a_6800_manifest() -> None:
    with pytest.raises(ValueError, match=r"irq2 event is 6803-only.*at_step 1"):
        manifest(bytes((0x01,)), events=(Event(1, "irq2", 0xFFF4),))
    # And the same manifest is fine on the 6803.
    assert manifest(bytes((0x01,)), part="6803", events=(Event(1, "irq2", 0xFFF4),)).events


def test_an_irq2_event_needs_a_vector_and_the_others_refuse_one() -> None:
    with pytest.raises(ValueError, match="needs vector"):
        Event(0, "irq2")
    with pytest.raises(ValueError, match="takes no vector"):
        Event(0, "irq", 0xFFF4)


def test_strict_refusal_ends_the_run_with_its_own_reason() -> None:
    result: list = []
    records = list(trace_manifest(manifest(bytes((0x01, 0x14, 0x01))), result=result))
    assert len(records) == 1  # the NOP ran; $14 is unassigned under strict
    assert result[0].reason == "undocumented_opcode"
    assert "$14" in result[0].detail
    # Under measured it runs, and this program then reaches its WAI.
    result = []
    records = list(
        trace_manifest(manifest(bytes((0x01, 0x14, 0x3E)), undocumented="measured"), result=result)
    )
    assert [record.instruction.mnemonic for record in records] == ["NOP", "NBA", "WAI"]
    assert result[0].reason == "waiting"


# -- manifests ----------------------------------------------------------------


def test_manifest_round_trips_through_its_json_form() -> None:
    original = manifest(
        bytes((0x01, 0x3E)),
        part="6803",
        undocumented="mame",
        events=(Event(1, "pulse_nmi"), Event(2, "irq2", 0xFFF0)),
        stop=StopRule(max_steps=9, at_pc=(0x2000,), on_wait=False, on_hcf=False),
    )
    assert manifest_from_dict(manifest_to_dict(original)) == original


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("part", "6809", "part must be one of"),
        ("undocumented", "guess", "undocumented must be one of"),
        ("host", "cpm-minimal", "host must be one of"),
        ("name", "", "name must be a non-empty string"),
    ],
)
def test_manifest_validation(field: str, value: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        manifest(bytes((0x01,)), **{field: value})


def test_manifest_rejects_unknown_and_missing_fields() -> None:
    document = manifest_to_dict(manifest(bytes((0x01,))))
    with pytest.raises(ValueError, match="unknown"):
        manifest_from_dict(document | {"surprise": 1})
    del document["part"]
    with pytest.raises(ValueError, match="missing"):
        manifest_from_dict(document)


def test_events_must_be_ordered_by_step() -> None:
    with pytest.raises(ValueError, match="ordered by at_step"):
        manifest(bytes((0x01,)), events=(Event(3, "irq"), Event(1, "irq_clear")))


def test_initial_irq2_is_refused_on_a_6800_manifest() -> None:
    with pytest.raises(ValueError, match=r"initial\.irq2 must be null"):
        manifest(bytes((0x01,)), initial=CPUState(pc=START, irq2=0xFFF4))


# -- checkpoints --------------------------------------------------------------


def test_checkpoints_resume_the_same_run(tmp_path: Path) -> None:
    whole = manifest(bytes((0x01,)) * 12, stop=StopRule(max_steps=12))
    reference = list(trace_manifest(whole))
    result: list = []
    paths = write_checkpoints(whole, 4, tmp_path, result=result)
    assert len(paths) == 3
    assert result[0].steps == 12
    rejoined = []
    for path in paths:
        rejoined += list(trace_manifest(load_manifest(path)))
    assert [record.before.pc for record in rejoined] == [record.before.pc for record in reference]
    assert [record.cycles for record in rejoined] == [record.cycles for record in reference]


def test_checkpoints_refuse_manifests_with_events(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not supported for manifests with events"):
        write_checkpoints(manifest(bytes((0x01,)), events=(Event(0, "irq"),)), 2, tmp_path)


# -- the command line ---------------------------------------------------------


def test_cli_trace_then_diff_round_trips(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    source = EXAMPLES / "daa.json"
    trace = tmp_path / "daa.jsonl"
    assert main(["trace", str(source), "--out", str(trace)]) == 0
    assert trace.read_text(encoding="utf-8") == (EXAMPLES / "daa.jsonl").read_text(encoding="utf-8")
    assert main(["diff", str(source), str(trace)]) == 0
    assert "traces are identical" in capsys.readouterr().out


def test_cli_diff_reports_a_divergence_and_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    source = EXAMPLES / "cpx-6800.json"
    lines = (EXAMPLES / "cpx-6803.jsonl").read_text(encoding="utf-8")
    trace = tmp_path / "wrong.jsonl"
    trace.write_text(lines, encoding="utf-8")
    assert main(["diff", str(source), str(trace)]) == 1
    out = capsys.readouterr().out
    # CPX immediate costs 3 cycles on the 6800 and 4 on the 6803, so the cycle
    # count is the first field that differs, before any flag does.
    assert "divergence at position 1" in out
    assert "cycles: reference=3 external=4" in out


def test_cli_rejects_a_bad_manifest(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert main(["trace", str(broken)]) == 2
    assert "error:" in capsys.readouterr().out


def test_cli_checkpoints(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    source = tmp_path / "nops.json"
    source.write_text(
        json.dumps(manifest_to_dict(manifest(bytes((0x01,)) * 6, stop=StopRule(max_steps=6)))),
        encoding="utf-8",
    )
    assert main(["checkpoints", str(source), "--every", "3", "--dir", str(tmp_path / "cp")]) == 0
    assert "2 checkpoints" in capsys.readouterr().out
