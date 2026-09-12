# MAME 0.285 as an emulator-derived 6800 oracle

MAME's `m6800`/`m6801` core is the most exercised 6800-family model that
exists: every Williams, Atari, Irem, Zaccaria, Taito and pinball 6800 board in
MAME runs on it. It is also **emulator-derived**, so under this project's
oracle-tier rule ([validation.md](validation.md)) it is a **detector, never a
judge**. A disagreement between `m6800-python` and MAME is a lead, resolved by
the Motorola manuals or by a second independent emulator — never by MAME's
say-so. MAME's own source agrees: `- verify invalid opcodes for the different
CPU types` is an open TODO at the top of `m6800.cpp`.

Everything on this page was run on 2026-09-12 with the commands as committed.

## What is installed

- MAME **0.285** at `/usr/games/mame` (`mame -version` → `0.285 (unknown)`).
- ROM sets under `/data/emu/source/myrient.erista.me/files/MAME/ROMs (non-merged)/`,
  used in place with `-rompath`. Nothing is copied, and no ROM, trace or
  `error.log` is committed (`.gitignore` covers `*.trace`, `error.log`,
  `mame-work/`, `mame-home/`, `reference/`).
- **A MAME source tree also exists on this machine, at
  `/home/aubrey/mame-master`, and it is version 0.261, not 0.285.** Its 6800
  core differs from the installed binary's in the `CLI`/`SEI`/`TAP`
  interrupt-delay handling and in the illegal-opcode cycle sentinel. Do not
  quote it. `scripts/fetch_mame_source.py` fetches the six files of the 0.285
  core, SHA-256 verified, into `reference/mame0285/`, and that is what every
  citation in these documents refers to.

## Games confirmed to run a 6800-family CPU

From `mame -listxml` on the installed binary, not from the source tree:

| Game | Tag | Part | MAME clock | Bus rate |
| --- | --- | --- | --- | --- |
| `dragrace` (Atari Drag Race, 1977) | `:maincpu` | Motorola **MC6800** | 1,008,000 | 1,008,000 Hz |
| `firetrk`, `orbit`, `skydiver`, `toratora`, `fgoal` | `:maincpu` | MC6800 | see [timing.md](timing.md) | |
| `robotron` (Williams, 1982) | `:soundcpu` | Motorola **MC6808** | 3,579,545 | 894,886 Hz (÷4 on-chip) |
| `qix` | `:audiocpu` | Motorola MC6802 | 3,686,400 | 921,600 Hz |
| `kncljoe` (Knuckle Joe, 1985) | `:soundcpu` | Motorola **MC6803** | 3,579,545 | 894,886 Hz |
| `kungfum` | `:iremsound` | MC6803 | 3,579,545 | 894,886 Hz |

`robotron`'s `:maincpu` is a **6809E** and belongs to the other repository;
only its sound CPU is in scope here.

## The working command line

`scripts/mame_trace.sh [game] [seconds] [tag] [workdir]` wraps exactly this:

```sh
M6800_TRACE_TAG=":maincpu" M6800_TRACE_FILE="dragrace.trace" \
/usr/games/mame dragrace \
  -rompath "/data/emu/source/myrient.erista.me/files/MAME/ROMs (non-merged)" \
  -homepath "$PWD/mame-home" \
  -video none -sound none -nothrottle -noreadconfig -skip_gameinfo \
  -debug -debugger none -log \
  -seconds_to_run 2 \
  -autoboot_script scripts/mame_trace.lua
```

and `scripts/mame_trace.lua` does:

```lua
local cpu = manager.machine.devices[tag]
local dbg = manager.machine.debugger
dbg.visible_cpu = cpu
dbg:command('trace ' .. file .. ',,noloop,{logerror "%X %X %X %X %X %X %X %d\n",'
            .. 'curpc,a,b,x,s,cc,wai,totalcycles}')
dbg:command("go")
```

The script also prints the device's state names and the vector table, and can
hold an input for a while (`M6800_PRESS`, below).

## Gotchas, confirmed or corrected here

| Claim carried in from earlier sessions | Status here |
| --- | --- |
| `-log` writes `error.log` into the **current working directory**, not beside `-homepath` | **Confirmed.** `-homepath "$PWD/mame-home"` and `error.log` still appeared in the cwd; the wrapper `cd`s into a work directory first for exactly this reason |
| `tracelog` is silent | **Confirmed.** A run with `dbg:command('tracelog "%X %X\n",curpc,a')` produced a 223-byte `error.log` containing only MAME's own warnings and no register lines, and left a stray `trace_<script>.lua` file behind. Use `trace FILE,,noloop,{logerror ...}` |
| `focus` breaks actions | **Not retested.** The Lua `dbg.visible_cpu = cpu` assignment does the same job and works |
| The Lua `device.debug:bpset` API segfaults | **Not retested**, and not needed: the `trace`-with-action pattern covers every case so far |
| Use `curpc`, not `pc` | **Corrected for this family.** The 6800 core does `state_add(STATE_GENPCBASE, "CURPC", m_pc.w.l)` (`m6800.cpp:553`) — CURPC is aliased to `m_pc`, **not** to `m_ppc` as it is in some other cores. So `curpc` and `pc` are the same value here, and both are read *before* the instruction executes. The scripts use `curpc` for consistency with the 6809 repository; nothing is gained or lost |
| MAME also creates `cfg/`, `nvram/` and `snap/` | **Confirmed**, in the work directory; `.gitignore` and the wrapper keep them out of the repository |

Two more, found here:

- **`logerror` prints the register values *before* the instruction at `curpc`
  executes**, one line per instruction, hex without leading zeros. The first
  line of `error.log` is MAME's `Soft reset`, and PIA warnings and the
  illegal-opcode messages are interleaved: filter to the register-field
  pattern before comparing (the wrapper's counting `grep` shows the pattern).
- **`totalcycles` goes momentarily "behind" at `CLI` and `TAP`.** Those
  handlers execute the *next* instruction inline (`execute_one()`), and MAME
  charges the `CLI`'s own cycles only after the handler returns. So the trace
  shows the inlined instruction with the `CLI`'s cycles not yet added, and the
  arithmetic catches up on the line after. Seen directly in the Drag Race run
  below. A cycle-delta comparator must special-case `$06`, `$0E`.

## Register names the core exposes

From Lua, `manager.machine.devices[tag].state` on `:maincpu` of `dragrace`
(MC6800), on `:soundcpu` of `robotron` (MC6808) and on `:soundcpu` of
`kncljoe` (MC6803) — **the same set in all three**:

```text
A B CC CURFLAGS CURPC GENPC PC S WAI X
```

There is **no `D`**: the 6801's 16-bit accumulator is not exposed, so a 6803
trace must reconstruct it as `A<<8 | B`. There is no separate `H`/`I`/`N`/`Z`/
`V`/`C`; read them out of `CC`. `WAI` is MAME's wait latch
(`m6800.cpp:550`), not a hardware register, and is logged so that a
`WAI`-halted instruction boundary is visible. In debugger expressions the same
names work in lower case, plus `totalcycles`, `frame`, `beamx`, `beamy`.

## Verified run 1: Drag Race, MC6800 as the main CPU

```sh
scripts/mame_trace.sh dragrace 2 :maincpu
```

This is the recipe's simplest case: a 6800 is the whole machine, it runs from
reset with nothing to press, and Atari's scanline timer gives interrupts
immediately.

```text
DEVICE: :maincpu = Motorola MC6800
STATE NAMES: A B CC CURFLAGS CURPC GENPC PC S WAI X
VECTORS: SCI:FFF0=0000 TOF:FFF2=0000 OCF:FFF4=0000 ICF:FFF6=0000
         IRQ:FFF8=15C7 SWI:FFFA=1200 NMI:FFFC=1200 RESET:FFFE=1200
instruction lines: 368676
```

Two emulated seconds at 1.008 MHz cost 3.2 s of wall time and produce a
10,662,224-byte `error.log` and a 5,529,213-byte disassembly `.trace`.
`$FFF0-$FFF6` read as `$0000` — ordinary ROM content, as they must on a part
with no on-chip timer — which is the cheapest way to tell a 6800 board from a
6801/6803 one.

First lines, columns `curpc a b x s cc wai totalcycles`:

```text
1200 0 0 0 0 D0 0 0
1203 0 0 0 FF D0 0 3
1206 0 0 0 FF D4 0 8
```

against the disassembly `1200: lds #$00FF` (3 cycles), `1203: ldx $3000`
(5 cycles). **Reset state confirmed**: `CC = $D0`, everything else zero.

**483 interrupts** were accepted at the IRQ vector `$15C7`. Around the first:

```text
1258 E0 33 A4E FD C8 0 5499      ; 2-cycle instruction
1259 E0 32 A4E FD C0 0 5501      ; 1259: bne $1253   (4 cycles)
15C7 E0 32 A4E F6 D0 0 5517      ; 15C7: tsx        -- handler entry
```

Reading it: S fell from `$FD` to `$F6`, **seven bytes**, the documented frame;
CC went `$C8 → $D0`, I set and the rest preserved; `totalcycles` rose by 16 =
the `BNE`'s 4 plus a **12-cycle entry**. A second entry, after `1283: inx`
(4 cycles), also costs 16. That is the measurement quoted in
[timing.md](timing.md).

**Real 1977 arcade code executes an undocumented opcode.** At `$1230` the ROM
runs opcode `$02`, and MAME logs
`m6800: illegal 1-byte opcode: address 1230, op 02`:

```text
122D FF 0 0 FF D8 0 85     ; 122D: sta $0E00
1230 FF 0 0 FF D8 0 90     ; 1230: illegal      -- MAME: 1-byte NOP, 4 cycles
1231 FF 0 0 FF D8 0 94     ; 1231: cli
1232 FF 0 0 FF C8 0 94     ; 1232: bsr $1238    -- inlined by cli, cycles not yet charged
1238 FF 0 0 FD C8 0 104    ; 94 + 8 (bsr) + 2 (cli) = 104
```

Both gotchas above are visible in those five lines: MAME's invented 4-cycle
illegal opcode, and the `CLI` cycle-accounting artefact. It is also a concrete
reason this project cannot simply "trust the trace": **a real ROM's behaviour
at `$1230` depends on what an MC6800 actually does with `$02`, which nobody
has published** ([undocumented-behavior.md](undocumented-behavior.md)).

## Verified run 2: Robotron's sound board, MC6808, and how it was driven

```sh
M6800_PRESS="IN2:Advance:680:20" scripts/mame_trace.sh robotron 20 :soundcpu
```

The Williams sound 6808 is exactly the awkward case: **it does nothing until
the main board talks to it**, and the main board will not talk until it is out
of its own power-on wait.

- Traced cold for 6 emulated seconds, the 6808 produced 1,424,903 instruction
  lines and **one** interrupt — the one at power-on. 752,963 of those lines
  are a single address.
- The address is `$FB83`, and the disassembly says `FB83: beq $FB83`: a
  one-instruction self-loop. The IRQ handler at `$FB11` starts with
  `lds #$007F`, so it never returns to the loop — it resets the stack and
  re-enters the top of the sound engine.
- Robotron comes up with unwritten CMOS and its **6809** main CPU spins
  waiting for the **Advance** service switch (`IN2` bit 1,
  `midway/williams.cpp:958` in `INPUT_PORTS_START( robotron )`,
  `PORT_NAME("Advance")`) with IRQs masked, so it
  never writes a sound command.

**How it was driven:** the Lua script holds `:IN2:Advance` from frame 680 to
frame 700 (`M6800_PRESS="PORT:FIELD:FRAME:HOLD"`, and the field can be
repeated, separated by `;`). Frame 680 is about 11.3 s at Robotron's 60.1 Hz,
just after the RAM test ends. With that press the 20-second run gave:

```text
DEVICE: :soundcpu = Motorola MC6808
VECTORS: IRQ:FFF8=FB11 SWI:FFFA=F01D NMI:FFFC=FBA0 RESET:FFFE=F01D
PRESS: IN2:Advance down at frame 680 / up at frame 700
instruction lines: 4,555,721
```

with a **second** interrupt appearing at line 2,628,248 — about 11.5 s in,
immediately after the press. That one interrupt is the whole proof that the
path works end to end: main 6809 → its PIA → sound PIA CB1 → merged IRQ line →
6808. Its entry:

```text
FB83 0 0 0 7F E5 0 10188921   ; the self-loop, 4 cycles
FB11 0 0 0 78 F5 0 10188937   ; handler; S 7F→78 (7 bytes), CC E5→F5, +16 cycles
```

Same seven-byte frame and same 12-cycle entry as Drag Race, on a different
part.

**Limit of this run.** Two interrupts in twenty seconds is not a sound-board
workout; Robotron's attract mode is nearly silent. To get a real command
stream a future session should also drive a coin and a start button
(`M6800_PRESS` takes a `;`-separated list) and trace during play. That was not
done here.

## Verified run 3: Knuckle Joe's sound board, MC6803

```sh
scripts/mame_trace.sh kncljoe 10 :soundcpu
```

```text
DEVICE: :soundcpu = Motorola MC6803
STATE NAMES: A B CC CURFLAGS CURPC GENPC PC S WAI X
VECTORS: SCI:FFF0=FA80 TOF:FFF2=FA80 OCF:FFF4=FA80 ICF:FFF6=FA80
         IRQ:FFF8=FC6D SWI:FFFA=FA80 NMI:FFFC=FB59 RESET:FFFE=FA80
instruction lines: 2,616,011
```

This is the 6801/6803 superset running, and it needs no coaxing: the on-chip
timer interrupts it continuously, so the CPU is busy from reset. The four
peripheral vectors below `$FFF8` are populated (all pointing at `$FA80`, the
same address as RESET and SWI — the board only uses one of them and sends the
rest to the reset entry). Its busiest addresses are inside the timer handler.

Use this game, not Robotron, when the build session needs 6803-specific
evidence: `MUL`, `LDD`/`STD`, `ADDD`/`SUBD` and `PSHX`/`PULX` all appear in
Irem-era sound code, and none of them exist on a 6800.

## Using MAME as an oracle, concretely

The intended comparison is **not** a lockstep of a whole arcade machine. It is:

1. **Boot-segment replay.** Load the ROM from the zip in place at the
   addresses the driver maps, reset, run the same number of instructions, and
   compare `curpc a b x s cc` per line. Drag Race diverges at its first I/O
   read (`1203: ldx $3000`, an unmapped read MAME logs), so the comparator
   must know the memory map and either stop or feed the value MAME saw. The
   Robotron sound ROM's first divergence is its first PIA read.
2. **Cycle totals.** `totalcycles` deltas give MAME's cost for every
   instruction executed, over millions of instructions of real arcade code —
   a cheap cross-check of the whole cycle table, subject to the `CLI`/`TAP`
   artefact above.
3. **Interrupt entry.** The 483 Drag Race entries verify the seven-byte frame,
   the I-bit effect and the 12-cycle charge; the Robotron entry verifies the
   same on a 6808 driven through a PIA.

## Limits

- MAME checks interrupt lines once per scheduler timeslice, not at every
  instruction boundary ([timing.md](timing.md)). **Interrupt latency is the
  one thing a MAME trace should not be used to validate.**
- MAME models no bus detail in the trace: which addresses the internal cycles
  touch is not in it. The 6809 project could fall back on a bus-level corpus
  for this; **for the 6800 there is none** ([validation.md](validation.md)).
- The illegal-opcode cycle count, the store-immediate opcodes, `$9D` as `JSR`,
  and `DAA`'s V are MAME's choices, not measurements
  ([undocumented-behavior.md](undocumented-behavior.md)).
- Traces are roughly 5 MB per emulated second per CPU and are derived from
  copyrighted ROMs. They stay out of the repository.
