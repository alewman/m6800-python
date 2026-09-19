"""The smallest useful host: flat RAM, a program, and a look at it running."""

from m6800_python import M6800, DebugSession, disassemble_range


def main() -> None:
    memory = bytearray(0x10000)
    memory[0xFFFE:0x10000] = b"\x10\x00"  # reset vector -> $1000
    memory[0x1000:0x1008] = bytes([0x86, 0x2A, 0x4C, 0xB7, 0x20, 0x00, 0x20, 0xFE])
    # LDAA #$2A; INCA; STAA $2000; BRA *

    for instruction in disassemble_range(memory.__getitem__, 0x1000, 4):
        print(f"{instruction.address:04X}  {instruction.text}")

    cpu = M6800(memory.__getitem__, memory.__setitem__)
    cpu.reset()
    session = DebugSession(cpu, peek_byte=memory.__getitem__)
    for _ in range(3):
        record = session.step()
        print(f"{record.instruction.text:<12} A={record.after.a:02X} +{record.cycles} cycles")
    print(f"$2000 = ${memory[0x2000]:02X}")


if __name__ == "__main__":
    main()
