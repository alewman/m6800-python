"""Tests for the reproducible MC6800 benchmark harness."""

import json

from benchmarks.m6800_core_benchmark import (
    INITIAL_SP,
    WORKLOADS,
    BenchmarkCPU,
    _write_json,
    run_benchmark,
)


def test_all_workloads_execute_fixed_instruction_counts() -> None:
    for workload in WORKLOADS:
        result = run_benchmark(
            workload,
            instruction_count=2_000,
            repeats=2,
            warmup_instructions=200,
        )

        assert result.name == workload.name
        assert result.instruction_count == 2_000
        assert len(result.samples) == 2
        assert all(sample.cycles > 0 for sample in result.samples)
        assert result.median_seconds > 0
        assert result.instructions_per_second > 0
        assert result.cycles_per_second > 0


def test_every_workload_is_deterministic_across_repeats() -> None:
    # Same host-driven sequence every time, so repeats must land on the same
    # cycle total -- the point of calling these "deterministic workloads".
    for workload in WORKLOADS:
        result = run_benchmark(workload, instruction_count=3_000, repeats=4, warmup_instructions=0)
        assert len({sample.cycles for sample in result.samples}) == 1


def test_stack_calls_returns_the_stack_pointer_to_where_it_started() -> None:
    workload = next(w for w in WORKLOADS if w.name == "stack_calls")
    cpu = workload.host()
    for _ in range(4_000):
        cpu.step()
    assert cpu.SP == INITIAL_SP


def test_interrupts_workload_actually_waits_and_takes_the_irq() -> None:
    workload = next(w for w in WORKLOADS if w.name == "interrupts")
    cpu = workload.host()
    driver = workload.make_driver()
    waited = False
    entered = False
    for _ in range(40):
        driver(cpu)
        before_waiting = cpu.waiting
        cpu.step()
        if before_waiting and cpu.waiting:
            waited = True
        if before_waiting and not cpu.waiting:
            entered = True
    assert waited, "the workload never produced a WAIT_IDLE boundary"
    assert entered, "the workload never left WAI by taking the IRQ"


def test_indexed_memory_leaves_cpx_unused_so_every_sample_runs_the_same_path() -> None:
    workload = next(w for w in WORKLOADS if w.name == "indexed_memory")
    first = run_benchmark(workload, instruction_count=5_000, repeats=1, warmup_instructions=0)
    second = run_benchmark(workload, instruction_count=5_000, repeats=1, warmup_instructions=0)
    assert first.samples[0].cycles == second.samples[0].cycles


def test_json_output_contains_interpreter_platform_and_samples(tmp_path) -> None:
    result = run_benchmark(
        WORKLOADS[0],
        instruction_count=100,
        repeats=1,
        warmup_instructions=0,
    )
    output = tmp_path / "benchmark.json"

    _write_json(output, [result])

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["python_implementation"]
    assert payload["python_version"]
    assert payload["platform"]
    assert payload["results"][0]["instruction_count"] == 100
    assert len(payload["results"][0]["samples"]) == 1
    assert "cycles" in payload["results"][0]["samples"][0]


def test_run_benchmark_rejects_bad_arguments() -> None:
    import pytest

    workload = WORKLOADS[0]
    with pytest.raises(ValueError):
        run_benchmark(workload, instruction_count=0, repeats=1, warmup_instructions=0)
    with pytest.raises(ValueError):
        run_benchmark(workload, instruction_count=10, repeats=0, warmup_instructions=0)
    with pytest.raises(ValueError):
        run_benchmark(workload, instruction_count=10, repeats=1, warmup_instructions=-1)


def test_benchmark_cpu_has_no_port_space_surprises() -> None:
    # Just a flat bus, matching the host every other test in this repository
    # uses; nothing exotic for a benchmark to accidentally measure.
    cpu = BenchmarkCPU(bytes((0x01,)))  # NOP
    assert cpu.SP == INITIAL_SP
    assert cpu.step() == 2
