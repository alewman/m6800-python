"""A readable, pure-Python Motorola MC6800 and MC6801/6803 instruction core."""

from m6800_python._core import C, H, I, N, V, Z
from m6800_python._undocumented import UndocumentedOpcode
from m6800_python.console import CommandDebugger, CommandError, CommandResult
from m6800_python.cpu import M6800, M6801, M6802, M6803, M6808
from m6800_python.debug import (
    BoundaryKind,
    DebugSession,
    DebugTarget,
    RunResult,
    StepRecord,
    StopReason,
    next_boundary,
)
from m6800_python.disasm import (
    ByteReader,
    Instruction,
    disassemble,
    disassemble_bytes,
    disassemble_range,
)
from m6800_python.state import CPUState
from m6800_python.trace import (
    TRACE_SCHEMA_VERSION,
    TraceDifference,
    TraceDivergence,
    compare_step_records,
    first_trace_divergence,
    iter_session_steps,
    iter_trace_divergences,
    read_trace,
    step_record_from_dict,
    step_record_to_dict,
    write_trace,
)

__all__ = [
    "M6800",
    "M6801",
    "M6802",
    "M6803",
    "M6808",
    "TRACE_SCHEMA_VERSION",
    "BoundaryKind",
    "ByteReader",
    "C",
    "CPUState",
    "CommandDebugger",
    "CommandError",
    "CommandResult",
    "DebugSession",
    "DebugTarget",
    "H",
    "I",
    "Instruction",
    "N",
    "RunResult",
    "StepRecord",
    "StopReason",
    "TraceDifference",
    "TraceDivergence",
    "UndocumentedOpcode",
    "V",
    "Z",
    "compare_step_records",
    "disassemble",
    "disassemble_bytes",
    "disassemble_range",
    "first_trace_divergence",
    "iter_session_steps",
    "iter_trace_divergences",
    "next_boundary",
    "read_trace",
    "step_record_from_dict",
    "step_record_to_dict",
    "write_trace",
]
