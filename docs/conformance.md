# Conformance: proving another core is this one

A **manifest** is a small JSON document that fully determines a run: the part,
the undocumented-opcode policy, what is in memory, the initial processor state,
when the host's interrupt inputs change, and when to stop. Two cores given the
same manifest see the same machine, so any difference between their traces is a
difference between the CPUs, not between their hosts.

That is what this kit is for. A port — in Rust, C, anything — produces a trace
in the format of [trace-schema.md](trace-schema.md) for a manifest, and

```text
python -m m6800_python.conformance diff MANIFEST TRACE
```

either says the traces are identical or names the first boundary and field
where they differ. Exit status 0 means identical, 1 a divergence, 2 bad input.

`src/m6800_python/conformance.py` implements everything here; where the two
disagree the code is the specification and this page has a bug.

## The three commands

```text
python -m m6800_python.conformance trace MANIFEST [--out FILE]
python -m m6800_python.conformance diff MANIFEST TRACE        # TRACE may be '-'
python -m m6800_python.conformance checkpoints MANIFEST --every N --dir DIR
```

`trace` writes the reference trace. `diff` compares one. `checkpoints` runs the
manifest without recording and writes a manifest that *resumes* it every N
boundaries, each with the full 64 KiB beside it, so a run of millions of
records can be diffed as independent segments in parallel: each segment starts
in the state the previous one ended in, so a divergence anywhere is reported by
the segment that holds it. Manifests with events are refused, because their
`at_step` values would have to be shifted into each segment.

From Python the same three are `trace_manifest`, `diff_manifest` and
`write_checkpoints`, with `load_manifest`, `manifest_to_dict` and
`manifest_from_dict` for the documents themselves.

## The manifest

```json
{
  "version": 1,
  "name": "cli-after-odd-opcode",
  "part": "6800",
  "undocumented": "strict",
  "host": "flat",
  "memory": [{ "address": 4096, "data": "110e0101 3e" }],
  "initial": { "pc": 4096, "sp": 511 },
  "events": [{ "at_step": 0, "kind": "irq" }],
  "stop": { "max_steps": 400, "at_pc": [], "on_wait": true, "on_hcf": true }
}
```

| Field | Meaning |
| --- | --- |
| `version` | Always `1`; a reader rejects anything else. |
| `name` | For messages. |
| `part` | `"6800"` (also the MC6802 and MC6808) or `"6803"` (also the MC6801). **Mandatory**: the parts differ in instruction set, cycle counts and CPX. |
| `undocumented` | `"strict"`, `"measured"` or `"mame"`. **Mandatory**: the policy decides what unassigned opcodes do, so a trace means nothing without it. |
| `host` | Only `"flat"`: 64 KiB RAM and nothing else. |
| `memory` | Segments, each with `address` and either `data` (hex) or `file` (a path beside the manifest, with optional `offset` and `length`). Later segments overwrite earlier ones. |
| `initial` | Any subset of the fifteen `CPUState` fields; the rest take their defaults, which are `cc` = 0xD0, the opcode history odd, and everything else zero or false. |
| `events` | Host requests, ordered by `at_step`. |
| `stop` | `max_steps` is **mandatory**, so every run is finite. |

There is no `cpm-minimal` profile and no port space: this family has no I/O
instructions — a peripheral is memory to this CPU — and there is no CP/M here.

### Events

Applied immediately before the boundary they name, through the public API, so
the boundary at `at_step` is the first that can observe the change.

| Kind | What the host does |
| --- | --- |
| `irq`, `irq_clear` | Sets or clears the IRQ level (IRQ1 on the 6801). |
| `nmi`, `nmi_clear` | Sets or clears the NMI level; the core detects the edge itself. |
| `pulse_nmi` | Latches an NMI edge directly. |
| `irq2` with `vector` | **6803 only**: the address of the highest-priority pending on-chip vector. A manifest naming `part` `"6800"` with an `irq2` or `irq2_clear` event is rejected, and so is one whose `initial.irq2` is not null. |
| `irq2_clear` | Withdraws it. |
| `reset` | Calls `reset()`. There is no reset line to hold on this family, so there is no `reset_clear`. |

### Stopping

The run stops **before** a boundary when the step budget is spent, when PC is
one of `at_pc`, when the next boundary would be `WAIT_IDLE` with no event left
(`on_wait`), or when it would be `HCF_IDLE` (`on_hcf`). Set `on_wait` or
`on_hcf` false to record the idle boundaries instead — `hcf-halts` does, to
show the halt ending at a `reset` event. The boundary that would have followed
a stop is not recorded.

Under `"strict"`, an unassigned opcode ends the run with the reason
`undocumented_opcode` and the opcode in `TraceRun.detail`. That is a result,
not an error: the trace simply has no record for the boundary that did not
happen, and a port should end its trace at the same place.

## What must match

At every boundary, in both the `before` and `after` states:

- the `BoundaryKind` — `instruction`, `irq`, `irq2`, `nmi`, `wait_idle`, `hcf_idle`;
- the cycle count;
- the instruction's address and bytes, when the boundary is one;
- and **all fifteen `CPUState` fields**, not just the registers.

That last point is the one that catches ports. `opcode` and `previous_opcode`
are part of the processor's state because the MC6800's `CLI` consults the
previous opcode's bit 0; `irq_inhibit` is the one-instruction interrupt delay
that `CLI` and `TAP` arm; `nmi_previous` is how the NMI edge is detected;
`waiting` and `halted` say whether `WAI` or `HCF` is in effect. A port that
matches every register but not `irq_inhibit` is **not** equivalent — it will
take an interrupt one instruction early somewhere, and the only question is
when. z80-python says the same of its `wz`.

A port omits `mnemonic` and `operands` from its records; the reader fills them
in from `disasm.py`, so a port never has to reproduce this project's
formatting.

## The fixtures

`examples/conformance/` has a manifest and its reference trace for each
decision this core made where a port is likeliest to differ. Every one is
small, and `tests/test_conformance.py` regenerates each trace from its manifest
and fails if a byte changed.

| Fixture | What it pins |
| --- | --- |
| `flags-and-branches` | Every conditional branch both ways (each over an `INCB`, so `B` counts which fell through), `CBA`/`SBA`, `NEG` of $80 and $00, `COM`, and the shifts through C |
| `daa` | The nine rows of the manual's `DAA` table, and `$99 + $99` where C stays set |
| `cpx-6800`, `cpx-6803` | The same bytes on both parts: N and V from the high byte with C untouched, against a true 16-bit compare |
| `interrupts/cli-after-odd-opcode`, `cli-after-even-opcode` | The MC6800's `CLI` delay depending on the previous opcode's bit 0 (APPS p. A-13, Q15) |
| `interrupts/cli-on-6803-always-delays` | The same even opcode on the 6803, which delays regardless |
| `interrupts/tap-delays-even-when-repeated` | `TAP` arming the delay every time it runs |
| `interrupts/sei-is-not-delayed` | `SEI` taking effect at once, so a later IRQ is never taken |
| `interrupts/wai-then-irq` | `WAI` at 9 cycles, the idle boundaries, then a 4-cycle entry that pushes nothing because the frame is already stacked |
| `interrupts/wai-with-i-set-takes-nmi-only` | `WAI` with I set ignoring the IRQ and waking on the NMI |
| `interrupts/nmi-outranks-irq` | Both asserted at one boundary: the NMI goes first |
| `interrupts/nmi-is-edge-triggered` | A level held high firing once, and again only after it drops |
| `interrupts/rti-takes-pending-irq-at-once` | `RTI` restoring I clear with the IRQ still asserted: the next boundary is the IRQ |
| `interrupts/irq-entry-costs-12-and-pushes-seven` | The entry's 12 cycles and its seven stacked bytes |
| `interrupts/irq2-priority` | The 6803: IRQ1 outranks an on-chip request, and the vector given is the one taken |
| `undocumented-measured` | `$14`, `$15`, `$87` and `$CF` under `measured`, including the "hole" byte the store-immediate forms skip |
| `hcf-halts` | `$9D` halting, the `HCF_IDLE` boundaries, and a `reset` event ending them |
| `stack-frames` | `SWI`, `JSR` in all three modes, `BSR`, `PSHX`/`PULX`, and `TSX`/`TXS` |

## Writing a port against this

1. Implement the trace format and emit one record per boundary.
2. Take one fixture — `flags-and-branches` is the gentlest — and diff.
3. Work through `interrupts/`: that is where the family's real decisions are,
   and where an emulator written from the manuals alone usually differs.
4. For a long run of your own, use `checkpoints` and diff the segments in
   parallel.

The reference core is itself checked against the Motorola manuals and MAME,
never against silicon ([validation.md](validation.md)). Agreeing with it means
agreeing with this core, which is a strong statement about equivalence and no
statement at all about either core being right where the manuals are silent.
