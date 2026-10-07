"""The MC6801/6803 on-chip timer (scripts/m6803_board.py's ``Timer``).

Fast, no trace needed: every rule here is M6801RM's documented register
behaviour, pinned to the exact mechanics of MAME 0.285's
reference/mame0285/m6801.cpp (cited in ``Timer``'s own docstrings). The full
replay against esclwrld's real sound ROM (2,271,980 instructions, 6,241
output-compare interrupts the board takes on its own) is
``test_replays.py::test_m6803_board_matches_mame``, marked slow.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from m6803_board import (  # noqa: E402
    TCSR_EOCI,
    TCSR_ETOI,
    TCSR_OCF,
    TCSR_TOF,
    VECTOR_OCF,
    VECTOR_TOF,
    Timer,
)


def test_reset_state() -> None:
    # OCD = TOD = 0xffff at reset (m6801.cpp line 1476); the counter and TCSR
    # both start at zero (line 1338; `m_tcsr = 0` in device_reset).
    timer = Timer()
    assert timer.counter == 0
    assert timer.tcsr == 0
    assert timer.ocrh_r() == 0xFF and timer.ocrl_r() == 0xFF
    assert timer.pending_vector() is None


def test_ocf_sets_on_an_exact_match() -> None:
    timer = Timer()
    timer.ocrh_w(0x12)
    timer.ocrl_w(0x34)
    timer.advance(0x1234)
    assert timer.tcsr & TCSR_OCF
    assert timer.counter == 0x1234


def test_ocf_sets_even_when_a_multi_cycle_jump_skips_past_the_match() -> None:
    # check_timer_event compares CTD >= OCD, an absolute (non-wrapping) test,
    # precisely so a multi-cycle instruction that lands past the exact match
    # point still catches it (m6801.cpp line 727).
    timer = Timer()
    timer.ocrh_w(0x10)
    timer.ocrl_w(0x00)
    timer.advance(0x1005)  # jumps clean over $1000 in one hop
    assert timer.tcsr & TCSR_OCF
    assert timer.counter == 0x1005


def test_tof_sets_when_the_counter_wraps() -> None:
    timer = Timer()
    timer.advance(0xFFFF)
    assert timer.tcsr & TCSR_TOF
    assert timer.counter == 0xFFFF
    # And again after wrapping all the way round once more.
    timer2 = Timer()
    timer2.advance(0x10000 + 7)
    assert timer2.tcsr & TCSR_TOF
    assert timer2.counter == 7


def test_a_set_flag_persists_until_acknowledged_and_does_not_refire() -> None:
    timer = Timer()
    timer.ocrh_w(0x00)
    timer.ocrl_w(0x10)
    timer.advance(0x10)
    assert timer.tcsr & TCSR_OCF
    timer.advance(5)  # well short of the next match (at 0x10 + 0x10000)
    assert timer.tcsr & TCSR_OCF  # still set; advance() does not clear it


def test_tcsr_write_only_changes_the_four_control_bits() -> None:
    # data &= 0x1f; m_tcsr = data | (m_tcsr & 0xe0) -- m6801.cpp lines
    # 2130-2134. The three flag bits are read-only through this register.
    timer = Timer()
    timer.ocrh_w(0x00)
    timer.ocrl_w(0x01)
    timer.advance(1)
    assert timer.tcsr & TCSR_OCF
    timer.tcsr_w(0xFF)  # every bit, including the flags, asserted
    assert timer.tcsr & TCSR_OCF  # the write could not set it, but did not clear it either
    assert timer.tcsr & TCSR_EOCI and timer.tcsr & TCSR_ETOI  # the control bits did take


def test_reading_tcsr_then_the_paired_register_clears_the_flag() -> None:
    # tcsr_r() clears m_pending_tcsr (line 2123); ch_r()/ocrh_w()/ocrl_w() then
    # clear the actual flag bit because it is no longer pending (lines
    # 2144-2146, 2188-2190, 2203-2205).
    timer = Timer()
    timer.advance(0xFFFF)
    assert timer.tcsr & TCSR_TOF
    timer.tcsr_r()
    timer.ch_r()
    assert not timer.tcsr & TCSR_TOF


def test_reading_the_paired_register_without_tcsr_first_leaves_the_flag_set() -> None:
    # The same sequence, but skipping tcsr_r: ch_r() sees TOF still pending
    # (freshly set by this same advance(), never acknowledged) and leaves it.
    timer = Timer()
    timer.advance(0xFFFF)
    assert timer.tcsr & TCSR_TOF
    timer.ch_r()
    assert timer.tcsr & TCSR_TOF


def test_writing_the_output_compare_register_also_acknowledges_ocf() -> None:
    # ocrh_w()/ocrl_w() clear OCF unless it is still pending (m6801.cpp lines
    # 2188-2190, 2203-2205) -- the usual way real code re-arms the timer: read
    # TCSR, then write the next compare value, acknowledging OCF in the act.
    timer = Timer()
    timer.ocrh_w(0x00)
    timer.ocrl_w(0x08)
    timer.advance(8)
    assert timer.tcsr & TCSR_OCF
    timer.tcsr_r()
    timer.ocrh_w(0x00)
    timer.ocrl_w(0x10)
    assert not timer.tcsr & TCSR_OCF


def test_writing_the_counter_high_byte_forces_it_to_fff8() -> None:
    # M6801RM; ch_w(): CT = 0xfff8 as a side effect, the written byte only
    # latched until cl_w() completes it (m6801.cpp lines 2153-2159). Not
    # exercised by esclwrld's trace (it only reads the counter), so this is
    # the manual/MAME citation alone -- see the module docstring.
    timer = Timer()
    timer.advance(0x1234)
    timer.ch_w(0x56)
    assert timer.counter == 0xFFF8
    timer.cl_w(0x78)
    assert timer.counter == 0x5678


def test_pending_vector_priority_and_enable_gating() -> None:
    timer = Timer()
    timer.ocrh_w(0x00)
    timer.ocrl_w(0x01)
    timer.advance(0x10000)  # crosses both the OC match and the TOF wrap
    assert timer.tcsr & TCSR_OCF and timer.tcsr & TCSR_TOF
    assert timer.pending_vector() is None  # neither EOCI nor ETOI armed yet
    timer.tcsr_w(TCSR_ETOI)
    assert timer.pending_vector() == VECTOR_TOF
    timer.tcsr_w(TCSR_ETOI | TCSR_EOCI)
    assert timer.pending_vector() == VECTOR_OCF  # OCI outranks TOI (m6801.cpp line 608)


@pytest.mark.parametrize("delta", [1, 0x10000, 3 * 0x10000 + 42])
def test_counter_wraps_correctly_across_several_full_periods(delta: int) -> None:
    timer = Timer()
    timer.advance(delta)
    assert timer.counter == delta & 0xFFFF
