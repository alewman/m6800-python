# CPU State

`cpu.capture_state()` returns an immutable `CPUState` holding everything the
processor owns at an instruction boundary; `cpu.restore_state(state)` puts it
back without calling the host's memory functions. Capturing reads nothing from
the bus.

| Field | Meaning |
| --- | --- |
| `a`, `b`, `x`, `sp`, `pc`, `cc` | the registers; `cc` bits 7-6 are always 1. `state.d` is `a:b` |
| `irq`, `nmi` | the input levels as the host last set them |
| `irq2` | the MC6801/6803 on-chip request vector (`$FFF0`-`$FFF6`) or `None`; always `None` on a 6800 |
| `nmi_previous`, `nmi_pending` | NMI edge detection: the level at the last boundary, and a latched edge not yet taken |
| `irq_inhibit` | the one-step IRQ hold-off after `TAP`, or after a `CLI` that holds it off |
| `waiting` | inside `WAI`, the frame already stacked |
| `halted` | halted by HCF; only reset leaves it |
| `opcode`, `previous_opcode` | the last two opcodes executed — the MC6800's `CLI` decides its hold-off from the one before it (APPS p. A-13) |

Construction validates widths, the `irq2` vectors, and CC bits 7-6. The value
compares by field and converts with `dataclasses.asdict()`; that dictionary is
the trace format's state object ([trace-schema.md](trace-schema.md)) but not a
promised save-file format.

## The machine boundary

`CPUState` excludes everything the host owns: memory, PIAs and other devices,
timers and the 6801's on-chip timer/SCI/ports, clocks and scheduling. Restoring
it restores the processor, which is exactly right when the host's state is
unchanged or restored alongside it, and is not a whole-machine save state.

```python
before = cpu.capture_state()
saved = bytes(memory)       # the host's part

cpu.step()

memory[:] = saved
cpu.restore_state(before)
assert cpu.capture_state() == before
```

`tests/test_state.py` checks that capture, step, restore, step reproduces the
same state and the same bus traffic, over random programs and interrupt
situations on both parts.
