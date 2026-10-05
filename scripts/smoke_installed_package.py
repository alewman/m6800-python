"""Smoke-test the installed m6800-python package, from outside the source tree.

    python scripts/smoke_installed_package.py

CI runs this against the freshly built wheel. It must pass with only the
installed package importable, which is why it checks where it was imported
from before anything else.
"""

from pathlib import Path

import m6800_python
from m6800_python import M6800, CPUState, DebugSession, disassemble_bytes

source_tree = Path(__file__).resolve().parents[1] / "src"
assert source_tree not in Path(m6800_python.__file__).resolve().parents, m6800_python.__file__

memory = bytearray(0x10000)
memory[0xFFFE:0x10000] = b"\x10\x00"  # the reset vector
memory[0x1000:0x1002] = bytes((0x86, 0x2A))  # LDAA #$2A
cpu = M6800(memory.__getitem__, memory.__setitem__)
cpu.reset()
# CPUState's defaults already carry CC = $D0 and the odd-opcode history that
# reset() restores, so the post-reset state is a default state with PC set.
assert cpu.capture_state() == CPUState(pc=0x1000), cpu.capture_state()
assert disassemble_bytes(memory[0x1000:0x1002]).text == "LDAA #$2A"
record = DebugSession(cpu, peek_byte=memory.__getitem__, track_accesses=True).step()
assert (record.after.a, record.cycles) == (0x2A, 2), record
assert record.accesses == (("r", 0x1000, 0x86), ("r", 0x1001, 0x2A)), record.accesses
print(f"m6800-python {m6800_python.__file__}: installed package OK")
