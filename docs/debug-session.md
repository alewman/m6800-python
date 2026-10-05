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
it is for reading and stepping through code. To debug a real board, give a board
to `DebugSession` ([below](#debugging-a-board)).

## Step through the Williams sound board

```sh
python scripts/williams_debug.py                # MAME's 176 captured commands, on schedule
python scripts/williams_debug.py --no-capture   # nothing arrives until you send it
python scripts/williams_debug.py -c "nextsound" -c "step 12" --batch
```

The whole Robotron sound board runs under the debugger: MC6808, RAM, ROM, and the
PIA whose port B receives commands and whose port A drives the DAC. It is the
same `WilliamsSoundBoard.step()` that `scripts/williams_sound.py` runs against
MAME for rung 4. A slow test also checks that the debugger path, with tracking
on, makes MAME's PIA writes. On top of the commands below it adds:

| Command | Does |
| --- | --- |
| `pia` | both ports' control, direction, output and input registers; the CB1 level, the flag, the enable, and the IRQ output |
| `sound VALUE` | send a command now, as the main board does: port B, then CB1. If CB1 is already high it drops it first, so there is always an edge |
| `nextsound` | run until the next scheduled command has arrived (breakpoints and watchpoints still stop it) |
| `schedule [COUNT]` | the commands still to come, with their cycles and times |
| `time` | the board clock, commands delivered, and DAC and PIA write counts |
| `dac [COUNT]` | the latest DAC bytes |
| `wav FILE [SECONDS]` | the DAC output so far, or its last SECONDS, as 44.1 kHz 8-bit WAV |

A command is the byte written to port B. Robotron sends `$C0|n`, with `$FF`
(silence, CB1 low) between sounds. After reset the code waits at `$F044 BRA *`
and after a sound at `$FB83`. The IRQ handler is at `$FB11` and reads the command
from `$0402`, so `break FB11` or `watch 0402 r` catches each command. `memory`
and `disassemble` peek the PIA, which never acknowledges an interrupt;
watchpoints see the real traffic. Under the debugger it runs about 75,000 steps
a second on CPython, roughly a third of real time; PyPy is much faster.

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
session = DebugSession(cpu, peek_byte=memory.__getitem__, history_limit=256, track_accesses=True)
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

## Debugging a board

A target can be a whole board rather than a bare CPU: an object with `step()`
and `capture_state()` whose `cpu` attribute is the processor. The session
tracks accesses on `target.cpu`'s bus callables, and the command debugger sets
registers and interrupt lines on it. It exposes that processor as
`session.cpu`. The board's `step()` must bring its devices up to date *after*
the CPU step: deliver inputs that have fallen due, and set the CPU's interrupt
lines. That way the state captured before the next step already shows what that
step will do, so `next_boundary` and the records' boundary kinds stay exact.
`scripts/williams_board.py` is the worked example:

```python
def step(self):
    cycles = self.cpu.step()
    self.cycle += cycles
    self.settle()  # deliver due commands; cpu.irq = pia.irq()
    return cycles
```

Give the session a side-effect-free `peek_byte` that covers devices too (the
board's `peek` reads the PIA without acknowledging it). Board-specific commands
go to `CommandDebugger(session, commands={name: (handler, help line)})`. Each
handler takes the argument words and returns printable lines, and host commands
may not replace built-in ones.

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
