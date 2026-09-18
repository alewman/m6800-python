"""SWI, WAI, RTI, interrupt entry, the CLI/TAP delay and reset.

Sources: M68PRM pp. A-56 (RTI), A-67/A-68 (SWI and its worked example), A-76
(WAI); MCSDD Figure 13 and M6801RM section 5.3 (12-cycle entry); M6801RM
section 5.4.1 (CLI, SEI, TAP and RTI interrupt timing), 5.4.2 (WAI).
"""

from __future__ import annotations

from conftest import make

from m6800_python import M6800

H, I, N, Z, V, C = 0x20, 0x10, 0x08, 0x04, 0x02, 0x01


def frame(bus, sp_after: int) -> list[int]:
    """The seven stacked bytes, lowest address first: CC B A XH XL PCH PCL."""
    return list(bus.memory[sp_after + 1 : sp_after + 8])


def test_swi_matches_the_manual_example(part: str) -> None:
    # M68PRM p. A-68: CC=HINZVC, B=12, A=34, X=5678, PC=$5566, SP=$EFFF,
    # vector $FFFA = $D055 -> PC $D055, SP $EFF8, stack 11HINZVC 12 34 56 78 55 67.
    cpu, bus = make(part, [0x3F], at=0x5566)
    cpu.A, cpu.B, cpu.X, cpu.SP, cpu.CC = 0x34, 0x12, 0x5678, 0xEFFF, 0xC0 | 0x2B
    bus.set_word(0xFFFA, 0xD055)
    assert cpu.step() == 12
    assert cpu.PC == 0xD055 and cpu.SP == 0xEFF8
    assert frame(bus, 0xEFF8) == [0xEB, 0x12, 0x34, 0x56, 0x78, 0x55, 0x67]
    assert cpu.CC & I


def test_rti_matches_the_manual_example(part: str) -> None:
    # M68PRM p. A-56: SP $EFF8 with the frame above -> all registers restored.
    cpu, bus = make(part, [0x3B], at=0xD066)
    cpu.SP = 0xEFF8
    bus.load(0xEFF9, [0xC0 | 0x25, 0x12, 0x34, 0x56, 0x78, 0x55, 0x67])
    assert cpu.step() == 10
    assert (cpu.CC, cpu.B, cpu.A, cpu.X, cpu.PC, cpu.SP) == (
        0xE5,
        0x12,
        0x34,
        0x5678,
        0x5567,
        0xEFFF,
    )


def test_rti_forces_cc_bits_7_and_6(part: str) -> None:
    cpu, bus = make(part, [0x3B])
    cpu.SP = 0x01F8
    bus.load(0x01F9, [0x00, 0, 0, 0, 0, 0x20, 0x00])
    cpu.step()
    assert cpu.CC == 0xC0


def test_irq_entry_pushes_the_frame_and_costs_12(part: str) -> None:
    cpu, bus = make(part, [0x01])
    cpu.A, cpu.B, cpu.X, cpu.SP, cpu.CC = 0xAA, 0xBB, 0x1234, 0x0200, 0xC0 | N
    bus.set_word(0xFFF8, 0x4000)
    cpu.irq = True
    assert cpu.step() == 12
    assert cpu.PC == 0x4000 and cpu.SP == 0x01F9
    assert frame(bus, 0x01F9) == [0xC8, 0xBB, 0xAA, 0x12, 0x34, 0x10, 0x00]
    assert cpu.CC == 0xC0 | N | I
    # I is now set, so the still-asserted line is not taken again.
    bus.memory[0x4000] = 0x01
    assert cpu.step() == 2 and cpu.PC == 0x4001


def test_irq_masked_by_i(part: str) -> None:
    cpu, _ = make(part, [0x01])
    cpu.CC = 0xC0 | I
    cpu.irq = True
    assert cpu.step() == 2 and cpu.PC == 0x1001


def test_nmi_is_edge_triggered_and_ignores_i(part: str) -> None:
    cpu, bus = make(part, [0x01, 0x01, 0x01])
    bus.set_word(0xFFFC, 0x5000)
    bus.load(0x5000, [0x01, 0x01])
    cpu.CC = 0xC0 | I
    cpu.nmi = True
    assert cpu.step() == 12 and cpu.PC == 0x5000
    # Held asserted: no second NMI.
    assert cpu.step() == 2 and cpu.PC == 0x5001
    cpu.nmi = False
    cpu.step()
    cpu.nmi = True
    assert cpu.step() == 12


def test_pulse_nmi_latches_an_edge(part: str) -> None:
    cpu, bus = make(part, [0x01])
    bus.set_word(0xFFFC, 0x5000)
    cpu.pulse_nmi()
    assert cpu.step() == 12 and cpu.PC == 0x5000


def test_nmi_outranks_irq(part: str) -> None:
    cpu, bus = make(part, [0x01])
    bus.set_word(0xFFFC, 0x5000)
    bus.set_word(0xFFF8, 0x4000)
    cpu.irq = cpu.nmi = True
    cpu.step()
    assert cpu.PC == 0x5000


def test_wai_stacks_then_waits_then_enters_without_pushing(part: str) -> None:
    cpu, bus = make(part, [0x3E])
    cpu.A, cpu.SP = 0x42, 0x0200
    bus.set_word(0xFFF8, 0x4000)
    assert cpu.step() == 9
    assert cpu.waiting and cpu.SP == 0x01F9
    assert frame(bus, 0x01F9)[2] == 0x42 and bus.word(0x01FF) == 0x1001
    writes = len(bus.writes())
    assert cpu.step() == 1 and cpu.waiting  # idles one cycle per step
    cpu.irq = True
    assert cpu.step() == M6800.WAI_EXIT_CYCLES == 4
    assert not cpu.waiting and cpu.PC == 0x4000 and cpu.CC & I
    assert len(bus.writes()) == writes and cpu.SP == 0x01F9  # no second frame


def test_wai_with_i_set_ignores_irq_but_not_nmi(part: str) -> None:
    cpu, bus = make(part, [0x3E])
    cpu.CC = 0xC0 | I
    bus.set_word(0xFFFC, 0x5000)
    cpu.step()
    cpu.irq = True
    for _ in range(5):
        assert cpu.step() == 1 and cpu.waiting
    cpu.nmi = True
    assert cpu.step() == 4 and cpu.PC == 0x5000


def test_cli_delays_a_pending_irq_by_one_instruction(part: str) -> None:
    cpu, bus = make(part, [0x0E, 0x86, 0x55, 0x01])  # CLI; LDAA #$55; NOP
    cpu.CC = 0xC0 | I
    bus.set_word(0xFFF8, 0x4000)
    cpu.irq = True
    cpu.step()  # CLI
    cpu.step()  # LDAA runs before the IRQ is recognised (M6801RM 5.4.1.1)
    assert cpu.A == 0x55 and cpu.PC == 0x1003
    assert cpu.step() == 12 and cpu.PC == 0x4000
    assert bus.word(cpu.SP + 6) == 0x1003  # returns to the NOP


def test_cli_with_i_already_clear_does_not_delay(part: str) -> None:
    cpu, bus = make(part, [0x0E, 0x86, 0x55])
    bus.set_word(0xFFF8, 0x4000)
    cpu.step()
    cpu.irq = True
    assert cpu.step() == 12 and cpu.A == 0


def test_cli_sei_loop_never_services_irq_on_the_6803() -> None:
    # M6801RM section 5.4.1.1: LOOP CLI / SEI / BRA LOOP never takes the IRQ.
    cpu, bus = make("6803", [0x0E, 0x0F, 0x20, 0xFC])
    cpu.CC = 0xC0 | I
    bus.set_word(0xFFF8, 0x4000)
    cpu.irq = True
    for _ in range(30):
        cpu.step()
        assert 0x1000 <= cpu.PC <= 0x1003


def test_mc6800_cli_after_an_even_opcode_does_not_delay() -> None:
    # APPS p. A-13, Q15: with a zero in the low bit of the opcode before CLI,
    # "a pending interrupt will be recognized as soon as execution of CLI is
    # complete".  CLRA is $4F (odd), TSTA $4D (odd), CLRB $5F ... use INCA $4C.
    cpu, bus = make("6800", [0x4C, 0x0E, 0x86, 0x55])  # INCA; CLI; LDAA #$55
    cpu.CC = 0xC0 | I
    bus.set_word(0xFFF8, 0x4000)
    cpu.irq = True
    cpu.step()  # INCA, masked
    cpu.step()  # CLI
    assert cpu.step() == 12 and cpu.PC == 0x4000 and cpu.A == 1  # LDAA never ran


def test_mc6800_cli_after_an_odd_opcode_delays() -> None:
    # APPS p. A-13, Q15: Motorola's NOP; CLI; WAI idiom -- NOP is $01, odd, so
    # the instruction after CLI (here WAI) runs before the pending IRQ.
    cpu, bus = make("6800", [0x01, 0x0E, 0x3E])
    cpu.CC = 0xC0 | I
    bus.set_word(0xFFF8, 0x4000)
    cpu.irq = True
    cpu.step()  # NOP
    cpu.step()  # CLI
    assert cpu.step() == 9 and cpu.waiting  # WAI stacked and waits ...
    assert cpu.step() == 4 and cpu.PC == 0x4000  # ... then the IRQ ends the wait


def test_mc6800_cli_loop_after_bra_takes_the_irq() -> None:
    # The M6801RM loop is not safe on an MC6800: BRA ($20) is even, so the IRQ
    # is recognised right after CLI (APPS p. A-13, Q15).
    cpu, bus = make("6800", [0x0E, 0x0F, 0x20, 0xFC])
    cpu.CC = 0xC0 | I
    bus.set_word(0xFFF8, 0x4000)
    cpu.irq = True
    for _ in range(6):
        cpu.step()
        if cpu.PC == 0x4000:
            break
    assert cpu.PC == 0x4000


def test_tap_delays_even_when_repeated(part: str) -> None:
    # M6801RM section 5.4.1.2: CLRA / TAP / TAP / TAP / SEI never takes the IRQ.
    cpu, bus = make(part, [0x4F, 0x06, 0x06, 0x06, 0x0F, 0x20, 0xF9])
    cpu.CC = 0xC0 | I
    bus.set_word(0xFFF8, 0x4000)
    cpu.irq = True
    for _ in range(40):
        cpu.step()
        assert 0x1000 <= cpu.PC <= 0x1006


def test_rti_takes_a_pending_irq_immediately(part: str) -> None:
    cpu, bus = make(part, [0x3B])
    cpu.SP = 0x01F8
    bus.load(0x01F9, [0xC0, 0, 0, 0, 0, 0x20, 0x00])
    bus.set_word(0xFFF8, 0x4000)
    cpu.CC = 0xC0 | I
    cpu.irq = True
    cpu.step()  # RTI restores I = 0
    assert cpu.step() == 12 and cpu.PC == 0x4000


def test_sei_is_not_delayed(part: str) -> None:
    cpu, bus = make(part, [0x0F, 0x01])
    bus.set_word(0xFFF8, 0x4000)
    cpu.step()
    cpu.irq = True
    assert cpu.step() == 2 and cpu.PC == 0x1002


def test_tap_and_tpa_keep_bits_7_and_6(part: str) -> None:
    cpu, _ = make(part, [0x06, 0x07])
    cpu.A = 0x15
    cpu.step()
    assert cpu.CC == 0xD5
    cpu.A = 0
    cpu.step()
    assert cpu.A == 0xD5


def test_reset(part: str) -> None:
    cpu, bus = make(part, [0x3E])
    bus.set_word(0xFFFE, 0xE000)
    cpu.A, cpu.CC = 0x99, 0xC0 | H | N | Z | V | C
    cpu.step()  # into WAI
    cpu.reset()
    assert cpu.PC == 0xE000 and cpu.CC == 0xD0 and not cpu.waiting
    assert cpu.A == 0x99  # undefined on silicon; left alone


def test_6803_irq2_vectors_and_priority() -> None:
    cpu, bus = make("6803", [0x01])
    bus.set_word(0xFFF4, 0x4400)
    bus.set_word(0xFFF8, 0x4800)
    cpu.irq2 = 0xFFF4
    assert cpu.step() == 12 and cpu.PC == 0x4400
    cpu, bus = make("6803", [0x01])
    bus.set_word(0xFFF4, 0x4400)
    bus.set_word(0xFFF8, 0x4800)
    cpu.irq2 = 0xFFF4
    cpu.irq = True  # IRQ1 outranks the on-chip sources
    cpu.step()
    assert cpu.PC == 0x4800
