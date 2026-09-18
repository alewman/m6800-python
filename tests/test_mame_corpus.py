"""Milestone 2: the generated MAME 0.285 single-step corpus (emulator-derived).

Skipped unless the corpus exists locally (``python scripts/mame_corpus.py
generate``; it is gitignored).  Every case must agree with MAME exactly, or
differ only in a way scripts/compare_mame_corpus.py lists as explained, with
the higher-tier source the core follows instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import compare_mame_corpus  # noqa: E402

pytestmark = pytest.mark.skipif(
    not (compare_mame_corpus.VECTORS / "m6800").exists(),
    reason="MAME corpus not generated (python scripts/mame_corpus.py generate)",
)


@pytest.mark.parametrize("part", ["6800", "6803"])
def test_corpus_has_no_unexplained_disagreement(part: str) -> None:
    total, _agree, unexplained = compare_mame_corpus.compare(part, None, show=5)
    assert total == 256 * 1000
    assert unexplained == 0
