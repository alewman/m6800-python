"""An MC6803 board whose on-chip timer raises ``irq2`` itself, against MAME.

    python scripts/m6803_board.py [--trace mame-work/esclwrld/error.log]

Escape from the Lost World's Bally pinball MPU (pinball/by6803.cpp), an
MC6803 at $8000-$FFFF (``scripts/replay_trace.py``'s ``MACHINES["esclwrld"]``
has the ROM layout). Its sound/lamp driver leans on the on-chip timer hard:
over the captured trace it reads TCSR ($08) 7,710 times and writes the
output-compare register ($0B/$0C) 6,243 times, taking 6,241 output-compare
interrupts. ``replay_trace.py`` passes this trace today by reading every
interrupt entry out of the log; this script instead gives the CPU a real
timer and lets *it* decide when to assert ``irq2``, which is the point of
calling something a "board" rather than a tape player.

**Why esclwrld, not Knuckle Joe.** The handoff brief named ``kncljoe``, whose
MC6803 sound ROM does contain one instruction that reads the counter
(``$7C4D LDAB $09``) -- but it never runs in the captured trace, and the ROM
never writes TCSR, OCRH or OCRL anywhere in its 8 KiB, so no capture length
would ever show an armed timer interrupt there; it was the wrong target.
esclwrld's trace already shows the timer doing real work, so it is used here
instead; both facts were checked against the ROM and the trace before writing
this file, not assumed from the brief.

**What is modelled, and what is not.** TCSR, the free-running counter and
the output-compare register ($08-$0C) -- entirely software-driven, so this
board computes them. Input capture ($0D/$0E, 783 reads, 390 taken interrupts)
depends on a signal external to the chip that nothing here has a model of
(most likely an AC zero-crossing detector, common on pinball MPUs, but no
driver source for this board is pinned to confirm it); those reads and its
interrupt entries are still read from the trace, exactly as
``replay_trace.py`` already does for the external IRQ1 line and for every
other game. Overflow (TOF) is modelled for TCSR's read value -- the register
is wrong without it -- but this ROM never arms ETOI, so it is never taken as
an interrupt, matching the trace's 0 TOF entries.

Register addresses, the pending-flag "read TCSR, then read the paired
register" clear sequence, and the counter-high-byte-write-sets-$FFF8 quirk
are M6801RM's (bit layout, Appendix: Timer); the exact mechanics are pinned
from MAME 0.285's reference/mame0285/m6801.cpp (``tcsr_r/w``, ``ch_r/w``,
``cl_r/w``, ``ocrh_r/w``, ``ocrl_r/w``, ``check_timer_event``,
``check_irq2``), cited line by line in ``Timer``'s docstring.

**Tier: emulator-derived**, same as every other rung-3 replay -- agreement
here is agreement with MAME on real code, not with silicon.
"""

from __future__ import annotations

import sys
from collections import Counter, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from replay_trace import (  # noqa: E402
    MACHINES,
    VECTORS,
    Divergence,
    documented,
    fmt,
    parse,
    pushed_frames,
    report,
    rom_image,
)

from m6800_python import M6803  # noqa: E402

GAME = "esclwrld"
MACHINE = MACHINES[GAME]

#: TCSR bits (M6801RM; mirrored in MAME 0.285's m6801.cpp lines 104-111).
TCSR_OLVL = 0x01
TCSR_IEDG = 0x02
TCSR_ETOI = 0x04
TCSR_EOCI = 0x08
TCSR_EICI = 0x10
TCSR_TOF = 0x20
TCSR_OCF = 0x40
TCSR_ICF = 0x80
#: The flag bits; TCSR writes may only change the four below them.
_FLAGS = TCSR_TOF | TCSR_OCF | TCSR_ICF
_CONTROL_MASK = 0x1F

#: Vectors, matching replay_trace.py's VECTORS and MAME's check_irq2 priority
#: (ICI > OCI > TOI > SCI; m6801.cpp lines 584-601). Only OCI and TOI are
#: this board's to decide; ICI stays read from the trace (see module docstring).
VECTOR_OCF = VECTORS["OCF"]
VECTOR_TOF = VECTORS["TOF"]


class Timer:
    """The MC6801/6803's free-running counter, output compare, and TCSR.

    One field per visible register plus the bookkeeping MAME keeps to decide
    when the next match or overflow falls: ``cycles`` is the cycle count
    since reset, never wrapped (MAME's ``CTD``, a plain 32-bit extension of
    the visible 16-bit counter, m6801.cpp line 53); ``oc`` is the visible
    output-compare register; ``_oc_target``/``_tof_target`` are the next
    absolute cycle counts at which a match/overflow occurs (MAME's
    ``OCD``/``TOD``, lines 54-64), recomputed whenever the counter or the
    compare register changes (``modified_counters``, lines 701-706).
    """

    def __init__(self) -> None:
        self.cycles = 0
        self.oc = 0xFFFF  # the reset value (m6801.cpp line 1476, OCD = 0xffff)
        self.tcsr = 0
        self._pending = 0  # MAME's m_pending_tcsr: flags set since the last TCSR read
        self._latched_high = 0  # the byte written to $09, held until $0A completes it
        self._oc_target = self._next(self.oc)
        self._tof_target = self._next(0xFFFF)

    @property
    def counter(self) -> int:
        return self.cycles & 0xFFFF

    def _next(self, low16: int) -> int:
        """The smallest cycle count >= ``self.cycles`` whose low 16 bits are ``low16``."""
        candidate = (self.cycles & ~0xFFFF) | low16
        return candidate if candidate >= self.cycles else candidate + 0x10000

    def _retarget(self) -> None:
        self._oc_target = self._next(self.oc)
        self._tof_target = self._next(0xFFFF)

    # -- $08: Timer Control and Status Register (m6801.cpp lines 2121-2134) --

    def tcsr_r(self) -> int:
        self._pending = 0
        return self.tcsr

    def tcsr_w(self, value: int) -> None:
        self.tcsr = (value & _CONTROL_MASK) | (self.tcsr & _FLAGS)
        self._pending &= self.tcsr

    # -- $09/$0A: the counter (m6801.cpp lines 2141-2160) ---------------------

    def ch_r(self) -> int:
        if not self._pending & TCSR_TOF:
            self.tcsr &= ~TCSR_TOF
        return (self.counter >> 8) & 0xFF

    def cl_r(self) -> int:
        return self.counter & 0xFF

    def ch_w(self, value: int) -> None:
        # M6801RM: writing the high byte sets the counter to $FFF8 as a side
        # effect; the byte is only latched, taking effect when the low byte
        # completes the write (m6801.cpp lines 2153-2159). Not exercised by
        # this board's trace -- esclwrld only reads the counter, never sets
        # it -- so this is the manual/MAME citation alone, unit-tested directly.
        self._latched_high = value & 0xFF
        self.cycles = 0xFFF8
        self._retarget()

    def cl_w(self, value: int) -> None:
        self.cycles = (self._latched_high << 8) | (value & 0xFF)
        self._retarget()

    # -- $0B/$0C: output compare (m6801.cpp lines 2163-2211) ------------------

    def ocrh_r(self) -> int:
        return (self.oc >> 8) & 0xFF

    def ocrl_r(self) -> int:
        return self.oc & 0xFF

    def ocrh_w(self, value: int) -> None:
        if not self._pending & TCSR_OCF:
            self.tcsr &= ~TCSR_OCF
        self.oc = ((value & 0xFF) << 8) | (self.oc & 0xFF)
        self._retarget()

    def ocrl_w(self, value: int) -> None:
        if not self._pending & TCSR_OCF:
            self.tcsr &= ~TCSR_OCF
        self.oc = (self.oc & 0xFF00) | (value & 0xFF)
        self._retarget()

    # -- advancing, and the interrupt decision --------------------------------

    def advance(self, cycles: int) -> None:
        """Add ``cycles`` (the board calls this with what ``cpu.step()`` returned)
        and set OCF/TOF if either's target has now been reached or passed
        (``check_timer_event``, m6801.cpp lines 724-752)."""
        self.cycles += cycles
        if self.cycles >= self._oc_target:
            self.tcsr |= TCSR_OCF
            self._pending |= TCSR_OCF
            self._oc_target = self._next(self.oc)
        if self.cycles >= self._tof_target:
            self.tcsr |= TCSR_TOF
            self._pending |= TCSR_TOF
            self._tof_target = self._next(0xFFFF)

    def pending_vector(self) -> int | None:
        """The on-chip interrupt ``check_irq2`` would take right now: OCI
        outranks TOI (m6801.cpp lines 584-601, with ICI/SCI left to the
        trace, see the module docstring). ``None`` leaves ``cpu.irq2``
        exactly as the external IRQ1 line is left when it is not asserted."""
        if self.tcsr & TCSR_EOCI and self.tcsr & TCSR_OCF:
            return VECTOR_OCF
        if self.tcsr & TCSR_ETOI and self.tcsr & TCSR_TOF:
            return VECTOR_TOF
        return None


#: $08-$0C: this board's; $0D/$0E (input capture) and everything else outside
#: this range go to the trace, unmodelled (module docstring).
_TIMER_READS = {
    0x08: "tcsr_r",
    0x09: "ch_r",
    0x0A: "cl_r",
    0x0B: "ocrh_r",
    0x0C: "ocrl_r",
}
_TIMER_WRITES = {
    0x08: "tcsr_w",
    0x09: "ch_w",
    0x0A: "cl_w",
    0x0B: "ocrh_w",
    0x0C: "ocrl_w",
}


class EsclwrldBoard:
    """esclwrld's MC6803 with a real timer; everything else trusts the trace.

    Built the way ``scripts/replay_trace.py``'s ``ReplayBus`` is, so the two
    can be compared line for line: ROM is read from the image in place, and
    while ``queue`` holds a trace line's accesses (set by :func:`replay`
    before every step) every other address is checked against it -- except
    that $08-$0C are *served* by :class:`Timer` rather than played back, and
    the value is still checked against what MAME logged, which is what
    proves the model right.

    With no trace -- ``queue`` left ``None``, as it is outside a replay --
    every address but the timer and ROM falls back to a plain 64 KiB
    bytearray instead of raising. That is a convenience for
    ``scripts/m6803_debug.py`` to step through real code interactively; it
    does not claim to be the real $0020/$0040 PIAs or the $1000-$17FF battery
    RAM, which this item was not asked to model.
    """

    def __init__(self, rom: bytearray) -> None:
        self.rom = rom
        self.is_rom = bytearray(0x10000)
        for first, last in MACHINE.rom_ranges:
            self.is_rom[first : last + 1] = b"\x01" * (last - first + 1)
        self.timer = Timer()
        self.ram = bytearray(0x10000)  # the no-trace fallback; see the class docstring
        self.queue: deque | None = None
        self.cpu = M6803(self.read, self.write, undocumented="mame")

    def read(self, address: int) -> int:
        if self.is_rom[address]:
            return self.rom[address]
        if address == 0x08:
            return self._tcsr_read()
        method = _TIMER_READS.get(address)
        if method is not None:
            value = getattr(self.timer, method)()
            self._expect("R", address, value)
            return value
        if self.queue is None:
            return self.ram[address]
        if not self.queue:
            raise Divergence(f"core read ${address:04X}; MAME logged no further access")
        kind, logged, value = self.queue.popleft()
        if kind != "R" or logged & MACHINE.address_mask != address & MACHINE.address_mask:
            raise Divergence(
                f"core read ${address:04X}; MAME's next access was {kind} ${logged:04X}"
            )
        return value

    def _tcsr_read(self) -> int:
        """TCSR's byte is OCF/TOF/the control bits (this board's) OR'd with
        ICF (not modelled -- see the module docstring), so a $08 read takes
        the real ICF bit from the trace and merges it with the board's own
        bits, then checks that merge against what MAME logged: any
        disagreement left, after giving the model the one bit it does not
        claim, is a disagreement in a bit it does. With no trace (``queue``
        is ``None``), there is nothing to merge or check: ICF reads back 0."""
        if self.queue is None:
            return self.timer.tcsr_r()
        if not self.queue:
            raise Divergence("core read $0008; MAME logged no further access")
        kind, logged_address, logged_value = self.queue.popleft()
        if kind != "R" or logged_address & MACHINE.address_mask != 0x08:
            raise Divergence(
                f"core read $0008; MAME's next access was {kind} ${logged_address:04X}"
            )
        computed = self.timer.tcsr_r()
        merged = (computed & ~TCSR_ICF) | (logged_value & TCSR_ICF)
        if merged != logged_value:
            raise Divergence(
                f"TCSR read: board computed ${computed:02X} (ICF taken from the trace, "
                f"giving ${merged:02X}); MAME logged ${logged_value:02X}"
            )
        return merged

    def write(self, address: int, value: int) -> None:
        method = _TIMER_WRITES.get(address)
        if method is not None:
            self._expect("W", address, value)
            getattr(self.timer, method)(value)
            self.cpu.irq2 = self.timer.pending_vector()
            return
        if self.queue is None:
            self.ram[address] = value & 0xFF
            return
        if not self.queue:
            raise Divergence(f"core wrote ${value:02X} to ${address:04X}; MAME logged nothing")
        kind, logged, logged_value = self.queue.popleft()
        if (
            kind != "W"
            or logged & MACHINE.address_mask != address & MACHINE.address_mask
            or logged_value != value
        ):
            raise Divergence(
                f"core wrote ${value:02X} to ${address:04X}; MAME's next access was "
                f"{kind} ${logged:04X} ${logged_value:02X}"
            )

    def _expect(self, kind: str, address: int, value: int) -> None:
        """Consume the logged entry for a timer register and check the board's
        own value against it -- the board computes these; MAME's log is the
        judge of whether it computed the right thing. With no trace, there is
        no judge, and the board's own value stands."""
        if self.queue is None:
            return
        if not self.queue:
            raise Divergence(f"core {kind} ${address:04X}=${value:02X}; MAME logged nothing")
        logged_kind, logged_address, logged_value = self.queue.popleft()
        if logged_kind != kind or logged_address & MACHINE.address_mask != address:
            raise Divergence(
                f"core {kind} ${address:04X}; MAME's next access was "
                f"{logged_kind} ${logged_address:04X}"
            )
        if kind == "R" and logged_value != value:
            raise Divergence(
                f"timer read ${address:04X}=${value:02X} of its own; MAME logged "
                f"${logged_value:02X} -- the board's model disagrees with the real chip"
            )

    def step(self) -> int:
        """One CPU boundary, then the timer catches up and re-decides irq2."""
        cycles = self.cpu.step()
        self.timer.advance(cycles)
        self.cpu.irq2 = self.timer.pending_vector()
        return cycles

    def capture_state(self):
        return self.cpu.capture_state()


def replay(trace: Path, limit: int | None = None) -> int:
    """Replay ``trace`` through :class:`EsclwrldBoard`; return 0 on full agreement."""
    lines = parse(trace)
    if limit:
        from itertools import islice

        lines = islice(lines, limit)
    line, nxt = next(lines, None), next(lines, None)
    if line is None or nxt is None:
        sys.exit(f"{trace}: no instruction lines")

    board = EsclwrldBoard(rom_image(MACHINE, GAME))
    cpu = board.cpu
    targets = {name: (board.rom[v] << 8) | board.rom[v + 1] for name, v in VECTORS.items()}
    cpu.PC, cpu.A, cpu.B, cpu.X, cpu.SP, cpu.CC = line.pc, line.a, line.b, line.x, line.s, line.cc
    total = line.cycles
    open_inlines: list[int] = []
    opcodes: Counter = Counter()
    interrupts: Counter = Counter()
    board_entries = 0
    history: deque = deque(maxlen=3)
    i = 0

    while nxt is not None:
        got = (cpu.PC, cpu.A, cpu.B, cpu.X, cpu.SP, cpu.CC)
        want = (line.pc, line.a, line.b, line.x, line.s, line.cc)
        if got[:5] != want[:5] or (got[5] & 0x3F) != (want[5] & 0x3F):
            report(
                GAME,
                i,
                [*history, line, nxt],
                f"registers differ: core {fmt(got)} MAME {fmt(want)}",
            )
            return 1
        if total - sum(open_inlines) != line.cycles:
            report(
                GAME,
                i,
                [*history, line, nxt],
                f"totalcycles: core {total - sum(open_inlines)} MAME {line.cycles}",
            )
            return 1

        opcode = board.rom[cpu.PC] if board.is_rom[cpu.PC] else None
        inlines = opcode == 0x06 or (opcode == 0x0E and cpu.CC & 0x10)
        board.queue = deque(line.accesses)
        try:
            cycles = board.step()
            opcodes[opcode] += 1
            if inlines:
                open_inlines.append(cycles)
            else:
                open_inlines.clear()
            total += cycles

            frames = pushed_frames(board.queue)
            chain = [*frames, nxt.pc]
            entries = len(frames) + (1 if cpu.waiting else 0)
            if not entries and cpu.PC != nxt.pc:
                raise Divergence(f"core went to ${cpu.PC:04X}, MAME to ${nxt.pc:04X}")
            for k in range(entries):
                target = chain[k] if cpu.waiting else chain[k + 1]
                taken = [name for name, v in targets.items() if v == target]
                if not taken:
                    raise Divergence(f"MAME entered ${target:04X}, which no vector points at")
                name = taken[0]
                was_waiting = cpu.waiting
                if name in ("OCF", "TOF"):
                    # The board's own timer must already have armed this --
                    # nothing here injects it. If it did not, that is the
                    # divergence: the model's timing disagrees with MAME's.
                    # cpu.irq2 holds a *vector table* address (VECTORS[name]),
                    # the same thing Timer.pending_vector() returns; target
                    # is the dereferenced handler address the chain is built
                    # from, a different number, not what to compare against.
                    if cpu.irq2 != VECTORS[name]:
                        got = "None" if cpu.irq2 is None else f"${cpu.irq2:04X}"
                        raise Divergence(
                            f"MAME took {name} (vector ${VECTORS[name]:04X}) at ${target:04X}; "
                            f"the board's timer had irq2={got}, not asserted by itself"
                        )
                    board_entries += 1
                elif name == "NMI":
                    cpu.pulse_nmi()
                elif name == "IRQ":
                    cpu.irq = True
                else:  # ICF, SCI: external signals this board does not model
                    cpu.irq2 = VECTORS[name]
                total += board.step()
                if name == "IRQ":
                    cpu.irq = False
                if name not in ("OCF", "TOF"):
                    cpu.irq2 = board.timer.pending_vector()
                interrupts[name + (" out of WAI" if was_waiting else "")] += 1
                if entries > 1:
                    interrupts["back-to-back entries"] += 1
                if was_waiting:
                    total = nxt.cycles
            if board.queue:
                raise Divergence(f"MAME logged {list(board.queue)} that the core did not do")
        except Divergence as problem:
            report(GAME, i, [*history, line, nxt], str(problem))
            return 1
        history.append(line)
        line, nxt = nxt, next(lines, None)
        i += 1

    print(
        f"{GAME}: {i} instructions replayed, all registers, bus accesses and cycle "
        f"totals agree with MAME 0.285"
    )
    print(f"  interrupts: {dict(interrupts)}")
    print(
        f"  {board_entries} of those (OCF/TOF) were the board's own timer deciding, "
        "not read from the trace"
    )
    undocumented = {
        f"${op:02X}": n
        for op, n in opcodes.items()
        if op is not None and not documented("6803", op)
    }
    print(f"  distinct opcodes executed: {len(opcodes)}; undocumented: {undocumented or 'none'}")
    return 0


def main() -> None:
    trace = ROOT / "mame-work" / GAME / "error.log"
    if not trace.exists():
        sys.exit(
            f"{trace} missing; make it with scripts/replay_trace.py {GAME} first "
            "(it prints the exact MAME command)"
        )
    sys.exit(replay(trace))


if __name__ == "__main__":
    main()
