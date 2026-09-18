"""Single-step harness around Robert Baruch's n6800 RTL model (rung 5).

Runs under Python 3.9 with amaranth 0.3 (the last release that provides the
``nmigen`` import name n6800 uses) and with n6800 on ``sys.path``; neither is
committed here -- see scripts/crosscheck/n6800.py for the setup.  Reads JSON
lines of initial state ``{"pc", "s", "x", "a", "b", "cc", "ram": [[addr,
value], ...]}`` on stdin and prints, for each, one JSON line with the state at
the next opcode fetch, the cycle count, and every valid bus cycle (VMA high)
as ``["r"|"w", addr, value]``.
"""

import json
import sys

import alu8
import core as n6800
from nmigen import ClockDomain, Module
from nmigen.sim import Settle, Simulator

MAX_CYCLES = 24  # WAI never reaches the next fetch; stop and say so


class RecordingALU(alu8.ALU8):
    """n6800 keeps CC inside its ALU; keep a handle on it to set and read it."""

    last = None

    def __init__(self):
        super().__init__()
        RecordingALU.last = self


n6800.ALU8 = RecordingALU


def main():
    cases = [json.loads(line) for line in sys.stdin if line.strip()]
    m = Module()
    m.submodules.cpu = cpu = n6800.Core(None)
    m.domains.ph1 = ClockDomain("ph1")
    sim = Simulator(m)
    sim.add_clock(1e-6, domain="ph1")
    results = []

    def process():
        alu = RecordingALU.last
        for case in cases:
            memory = dict(case["ram"])
            yield cpu.reset_state.eq(3)
            yield cpu.interrupt.eq(0)
            yield cpu.cycle.eq(0)
            yield cpu.jsr_cycle.eq(0)
            yield cpu.pc.eq(case["pc"])
            yield cpu.Addr.eq(case["pc"])
            yield cpu.RW.eq(1)
            yield cpu.VMA.eq(1)
            yield cpu.a.eq(case["a"])
            yield cpu.b.eq(case["b"])
            yield cpu.x.eq(case["x"])
            yield cpu.sp.eq(case["s"])
            yield alu.ccs.eq(case["cc"])
            yield cpu.IRQ.eq(0)
            yield cpu.NMI.eq(0)
            yield Settle()  # let the new state reach the design's next-state logic
            bus = []
            cycles = 0
            finished = False
            while cycles < MAX_CYCLES:
                address = yield cpu.Addr
                valid = yield cpu.VMA
                reading = yield cpu.RW
                if valid and reading:
                    value = memory.get(address)
                    bus.append(["r", address, value])
                    yield cpu.Din.eq(0 if value is None else value)
                    yield Settle()
                elif valid:
                    value = yield cpu.Dout
                    memory[address] = value
                    bus.append(["w", address, value])
                yield
                yield Settle()  # read the registers after the edge, not before it
                cycles += 1
                if (yield cpu.cycle) == 0 and not (yield cpu.interrupt):
                    finished = True
                    break
            results.append(
                {
                    "pc": (yield cpu.pc),
                    "s": (yield cpu.sp),
                    "x": (yield cpu.x),
                    "a": (yield cpu.a),
                    "b": (yield cpu.b),
                    "cc": (yield alu.ccs),
                    "cycles": cycles if finished else None,
                    "bus": bus,
                    "ram": sorted(memory.items()),
                }
            )

    sim.add_sync_process(process, domain="ph1")
    sim.run()
    for result in results:
        print(json.dumps(result))


if __name__ == "__main__":
    main()
