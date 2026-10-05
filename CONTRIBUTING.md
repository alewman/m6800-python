# Contributing

Issues are the right place for bug reports, API discussion, and proposed changes.

For a pull request:

1. Keep the instruction core independent of machine and device policy: the host
   owns memory, I/O, the timer and the SCI, and raises the interrupt inputs.
2. Add or update a focused regression test for a behaviour change. A new or
   changed handler cites the manual page its rule comes from, in its docstring;
   `tests/test_readability.py` enforces that, the mnemonic it is named after,
   and the module that owns it.
3. Run `python -m pytest -q`, `python -m ruff check .` and
   `python -m ruff format --check .` (CI runs all three, on CPython 3.11-3.14
   and PyPy 3.11).
4. **A change to instruction semantics, the interrupt lifecycle or cycle counts
   reruns the oracle rungs**: `python scripts/compare_mame_corpus.py` and
   `ROMPATH=... python -m pytest -m slow`, and says in the commit message that
   it did and what the numbers were. Those rungs need MAME 0.285, its ROM sets
   and a generated corpus, so CI cannot run them; docs/validation.md is their
   record.
5. A documentary claim cites a page of a Motorola manual, or a published
   measurement, or is marked `[unverified]`. Never a guess, and never an
   emulator's behaviour presented as the chip's.

Do not commit ROMs, traces, generated vectors, `reference/`, `third_party/`,
`mame-work/`, caches, build artifacts, or credentials.
