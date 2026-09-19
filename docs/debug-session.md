# Debugging: DebugSession, the command debugger, and `python -m m6800_python`

## Step through a ROM from the command line

```sh
python -m m6800_python --zip "ROMPATH/robotron.zip:video_sound_rom_3_std_767.ic12@F000" --reset
python -m m6800_python --part 6803 --load program.bin@E000 --pc E000
python -m m6800_python --load a.bin@1000 --pc 1000 -c "break 1040" -c "run 1000" --batch
```

It loads any number of files (`--load FILE@ADDRESS`) or members of MAME ROM zips
(`--zip ZIP:MEMBER@ADDRESS`) into a flat 64K RAM host, starts at `--pc` or from
the reset vector (`--reset`), shows the registers and a listing, runs any `-c`
commands, and then prompts (`m6800> `) unless `--batch`. The host has no devices:
it is for reading and stepping through code. To debug a real board, wrap your own
host in a `DebugSession` (below) — `scripts/williams_sound.py` is such a host.

## Commands

| Command | Does |
| --- | --- |
| `registers`, `regs`, `r` | A, B (D on a 6803), X, SP, PC, CC with `HINZVC` flags; IRQ/NMI inputs, WAI, HCF, the IRQ hold-off |
| `step [COUNT]`, `s` | execute boundaries, one line each; ignores breakpoints |
| `over`, `o` | step, but run a `JSR`/`BSR` through until it returns to the next instruction |
| `run STEPS [CYCLES]`, `continue`, `c` | run until a stop condition (`continue`: a million steps) |
| `break ADDR`, `b`; `delete ADDR`; `breakpoints` | execute breakpoints (stop *before* the instruction) |
| `watch ADDR [r\|w\|rw]`; `unwatch ADDR` | memory watchpoints (stop *after* the step that touched it) |
| `disassemble [ADDR] [COUNT]`, `d` | listing; `>` marks PC, `*` a breakpoint, undocumented opcodes are flagged |
| `memory ADDR [LENGTH]`, `m` | hex and ASCII, up to 256 bytes |
| `history [COUNT]` | the retained step records |
| `set REG VALUE` | set A, B, D, X, SP, PC or CC |
| `irq on\|off`, `nmi`, `reset` | drive the IRQ line, latch an NMI edge, reset the CPU |
| `help`, `quit` | |

Addresses and values are hex (`1234`, `$1234`, `0x1234`; `#123` is decimal).
Counts are decimal (`step 10`, `run 5000`), with `$`/`0x` for hex.

A run starting on a breakpoint leaves it rather than stopping at once, so `run`
after a breakpoint hit continues.

## DebugSession

```python
session = DebugSession(cpu, peek_byte=memory.__getitem__, history_limit=256,
                       track_accesses=True)
session.add_breakpoint(0xFB11)
result = session.run(max_steps=1_000_000, max_cycles=900_000)
print(result.reason, result.state.pc)
```

`DebugSession` drives any object with `step()` and `capture_state()` — an `M6800`
or `M6803` — and never changes what the core does.

- **`step()`** advances exactly one boundary and returns a `StepRecord`: the
  `BoundaryKind`, the before and after `CPUState`, the cycles, the
  `Instruction` (when a peek is given), and, when tracking, every bus access in
  order.
- **`run(max_steps=, max_cycles=None, stop_on_wait=True, stop_on_halt=True)`**
  requires a finite step budget and returns a `RunResult` whose `StopReason` is
  one of: `BREAKPOINT` (before the instruction), `WATCHPOINT` (after the step;
  `result.hits` lists the accesses), `WAITING` (in `WAI` with nothing able to
  end it), `HALTED` (HCF), `UNDOCUMENTED` (an unassigned opcode under
  `undocumented="strict"`; `result.error` says which, and the CPU is unchanged),
  `STEP_LIMIT` or `CYCLE_LIMIT` (checked after each atomic step, so it can be
  exceeded by one step's cost).
- **Boundary kinds**: `INSTRUCTION`, `IRQ`, `IRQ2` (a 6803 on-chip request),
  `NMI`, `WAIT_IDLE`, `HCF_IDLE`. `next_boundary(state)` predicts the kind from a
  state exactly as `step()` decides it, including the `TAP` and `CLI` hold-offs;
  a test runs 2,000 random interrupt situations through both.
- **History** is a bounded ring (`history_limit`, 0 to disable). It holds CPU
  states, not memory, and is not rewind.

## Access tracking and watchpoints

z80-python leaves watchpoints out because its hosts read memory through subclass
methods it cannot observe. This core takes `read_byte`/`write_byte` as plain
callables, so with `track_accesses=True` the session wraps them — recording
every read and write each step makes, in the order the core makes them — and
`close()` puts the originals back. Watchpoints need tracking. The recorded
accesses are the core's, which leaves out the MC6800's dummy bus cycles
([timing.md](timing.md)).

## Embedding the command debugger

`CommandDebugger(session).execute("d 1000 8")` returns a `CommandResult` of
printable lines; `interact(input, output)` is a line loop over any text
streams. Neither depends on a terminal library, so both embed in a GUI or a
test.
