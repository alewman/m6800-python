# Trace schema (version 1)

A trace is a CPU's observable behaviour written down one boundary at a time.
Two cores that produce equal traces for the same program and host behave the
same as far as software can tell. This page is the contract for producing one in
any language so that `first_trace_divergence` can compare it with this core;
`src/m6800_python/trace.py` implements it, and where they disagree the code is
the specification and this page has a bug. It follows z80-python's schema with
this family's state.

## File format

JSON Lines: UTF-8, one JSON object per line, `\n`-terminated, blank lines
ignored. This package writes sorted keys and no whitespace; readers must not
depend on either. Records are aligned by line position; `sequence` is for
humans.

## Record

| Key | Type | Meaning |
| --- | --- | --- |
| `version` | integer | `1`. Readers reject any other value |
| `sequence` | integer ≥ 0 | producer-local counter, informational |
| `kind` | string | `instruction`, `irq`, `irq2`, `nmi`, `wait_idle` or `hcf_idle` |
| `cycles` | integer > 0 | what `step()` returned |
| `instruction` | object or `null` | the instruction executed; `null` for every other kind, and allowed to be `null` for `instruction` when the producer cannot peek memory |
| `before`, `after` | state object | the complete `CPUState` at the boundary's start and end |
| `accesses` | array, optional | every bus access in order, `["r"\|"w", address, value]`; compared only when both traces carry it |

No other keys are allowed.

### `instruction`

| Key | Required | Meaning |
| --- | --- | --- |
| `address` | yes | PC at the fetch |
| `data` | yes | lowercase hex of every byte, e.g. `"b62000"` |
| `mnemonic`, `operands` | optional | this package's disassembly; **a producer in another language should omit them** — the reader decodes `data` itself, trying each undocumented-opcode policy until one decodes exactly these bytes |

### State object

Exactly the keys of `CPUState` ([cpu-state.md](cpu-state.md)): `a` `b` `x` `sp`
`pc` `cc` `irq` `nmi` `irq2` `nmi_previous` `nmi_pending` `irq_inhibit`
`waiting` `halted` `opcode` `previous_opcode`. Integers unsigned; `irq2` is an
integer vector or `null`; flags are JSON booleans.

## Comparison

`compare_step_records` reports every differing field by path: `kind`, `cycles`,
`instruction.address`, `instruction.data`, `before.<field>`, `after.<field>`,
`accesses`. When one trace ends first the path is `record` with values
`"present"` and `null`. `first_trace_divergence` stops at the first difference
without reading either trace to the end.

```python
from m6800_python import DebugSession, iter_session_steps, write_trace

session = DebugSession(cpu, peek_byte=memory.__getitem__, track_accesses=True)
with open("run.jsonl", "w") as out:
    write_trace(iter_session_steps(session, max_steps=100_000), out)
```

## Versioning

Any change to the keys, their types or their meaning is a new version, and
readers reject versions they do not know.
