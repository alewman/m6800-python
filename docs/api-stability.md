# Public API stability

`m6800-python` uses semantic versioning for the public names exported from the
package root and listed in each public module's `__all__`. The same policy as
[z80-python](https://github.com/alewman/z80-python)'s, with this family's
surface.

## Public contracts

The supported surface is exactly `__all__` in `src/m6800_python/__init__.py`:

- **the CPU classes and flag constants**: `M6800`, `M6802`, `M6808` (one
  instruction set) and `M6803`, `M6801` (the superset), their constructor
  `M6800(read_byte, write_byte, *, undocumented="strict")` (the embedding
  contract in [start-here](start-here.md#the-embedding-contract)), the register
  and `CC` attributes, the lifecycle inputs `irq`, `nmi`, `pulse_nmi()`,
  `M6803.irq2`, `reset()`, `step()`, and the flag masks `H I N Z V C`;
- **`UndocumentedOpcode`** and the `undocumented=` policies `"strict"`,
  `"measured"` and `"mame"`;
- **`CPUState`** with `capture_state()` and `restore_state()`;
- **disassembly**: `Instruction`, `disassemble`, `disassemble_bytes`,
  `disassemble_range`, `ByteReader`;
- **`DebugSession`** and its values: `DebugTarget`, `BoundaryKind`,
  `StopReason`, `StepRecord`, `RunResult`, `next_boundary`, access tracking
  (`track_accesses=`, `StepRecord.accesses`) and watchpoints
  (`add_watchpoint`, `StopReason.WATCHPOINT`, `RunResult.hits`);
- **`CommandDebugger`** with `CommandResult` and `CommandError`, the
  `python -m m6800_python` command line, and `console.parse_number`;
- **traces**: `TRACE_SCHEMA_VERSION`, `read_trace`, `write_trace`,
  `step_record_to_dict`, `step_record_from_dict`, `iter_session_steps`,
  `compare_step_records`, `iter_trace_divergences`, `first_trace_divergence`,
  `TraceDifference`, `TraceDivergence`, and the schema in
  [trace-schema.md](trace-schema.md).

The package ships a `py.typed` marker, so these annotations are available to
static type checkers. Public dataclass field names, enum values, function
signatures and documented behaviour follow semantic-versioning compatibility
rules.

## Not public

Underscore-prefixed modules, methods and attributes are implementation details,
including the opcode tables, the mixins the CPU classes are built from, and the
opcode history the `CLI` rule reads. `tests/datasheet.py` is generated and is
not an API. Scripts under `scripts/` are tools for this repository, not a
supported interface.

## What may change inside a minor release

**Cycle counts marked `[unverified]` may change.** Under
`undocumented="measured"`, the behaviour of an opcode comes from Wheeler's 1977
article or Doc TB's 2019 measurement, but neither gives a cycle count for every
opcode it describes; where none exists the count is a reading of what the
sequence must cost, marked `[unverified]` in
[undocumented-behavior.md](undocumented-behavior.md). A later measurement
outranks it, and correcting one of those counts is a patch release, not a
breaking change. The documented instruction set's cycle counts, which come from
the manuals, are covered by the compatibility rules above.

The same goes for any `[unverified]` claim in the documents: it is the best
reading available, not a promise.

## Compatibility policy

- Patch releases fix defects without intentional public incompatibilities.
- Minor releases add API surface and keep existing contracts working.
- Major releases may remove or change public contracts, and say so in
  [CHANGELOG.md](../CHANGELOG.md).

A semantic change to the core — instruction behaviour, flags, cycle counts or
the interrupt lifecycle — reruns the oracle rungs in
[validation.md](validation.md) before release, whatever its version number.
