# Provenance

Audited 2026-11-13 (provenance audit, wave 1) at `258e684` on `main`, all branches, tags
and history included. No GPL source was opened for this audit.

## Summary

| Verdict | Count |
| --- | --- |
| clean | 8 |
| cite | 4 |
| rewrite | 0 |
| unclear | 2 |

## The code

| Part | Where its behaviour came from | Licence of the source | Verdict |
| --- | --- | --- | --- |
| Documented instructions, flags, DAA, cycles, interrupts (`_alu.py`, `_loads.py`, `_branches.py`, `_index.py`, `_shifts.py`, `_stack.py`, `_interrupts.py`, `_dispatch.py`, `_core.py`) | Motorola M68PRM and M6801RM (Appendix A tables, via `scripts/extract_manual_tables.py` into `tests/datasheet.py`); undefined-flag choices "as MAME does" | Motorola manuals (facts); MAME m6800 files BSD-3-Clause | clean |
| `_undocumented.py` `"measured"` policy, HCF | Wheeler 1977 article and Doc TB's 2019 hardware measurement | facts from hardware, cited | clean |
| `_undocumented.py` `MAME_AS_INSTRUCTION`, `MAME_ILLEGAL_LENGTH`, `MAME_ILLEGAL_CYCLES`, and their use in `disasm.py` | Read out of MAME 0.285 `m6800_insn[]`, `m6803_insn[]`, `cycles_6800[]`, `cycles_6803[]` (`m6800.cpp`, `m6801.cpp`) | BSD-3-Clause, copyright Aaron Giles | **cite**: a table taken from BSD code must keep the notice; add "MAME, BSD-3-Clause, copyright Aaron Giles" (and the BSD-3 text, or a `LICENSES/BSD-3-Clause.txt`) beside the tables |
| `scripts/m6803_board.py`, `scripts/williams_board.py` (+ `williams_debug.py`, `williams_sound.py`, `m6803_debug.py`) | Timer and PIA behaviour read from MAME 0.285 `m6801.cpp`, `6821pia.cpp`, `midway/williams*.cpp`, `pinball/by6803.cpp`, with line references | all BSD-3-Clause (headers confirmed 2026-11-13: Aaron Giles; Aaron Giles, Nathan Woods; Robbbert) | **cite**: name the licence and copyright holders beside the line references |
| `scripts/crosscheck/sim68xx_harness.c`, `scripts/crosscheck/sim68xx.py` | A C harness written against sim68xx's headers and internals (`defs.h`, `chip.h`, `reg_set*`, `ireg_start`, `instr_exec`, a `board_install` stub) and linked with its objects; the docstring also reports the contents of sim68xx's `optab.c` | sim68xx GPL-2.0 (Arne Riiber, Felix Erckenbrecht) | **unclear** (policy). The core is not derived from it (three-way diff, differences settled by the manuals). But the harness is a tool built on GPL code: under charter rule 6 it is GPL. Settle by relabelling the `.c` as `GPL-2.0-or-later` (and saying so in the README), or moving the harness out of this MIT repository |
| `scripts/crosscheck/n6800_harness.py`, `n6800.py`, `functional_test_n6800.py` | Imports Robert Baruch's n6800 nMigen model, subclasses its `alu8.ALU8` and patches `core` internals | n6800 GPL-3.0 | **unclear** (policy), as above: a tool that imports and subclasses GPL code; relabel `n6800_harness.py` GPL-3.0-or-later or move it out |
| `validation/functional_test*.asm`, `.bin`, `.s19`, `scripts/gen_functional_test.py`, `scripts/asm6800.py` | Own; "in the spirit of" Klaus Dormann's 6502 test (shape only, no code); expected values from the manual formulas | MIT (own) | clean |
| `examples/conformance/*`, `conformance.py` | Own | n/a | clean |
| `scripts/dump_mame_tables.py`, `fetch_mame_source.py`, `mame_corpus.py`, `compare_mame_corpus.py`, `replay_trace.py`, `mame_trace.*`, `williams_capture.lua` | Tools reading MAME's BSD-3 m6800 files (fetched to `reference/`, not committed) or running MAME as a detector | BSD-3-Clause (recorded in `docs/validation.md`) | clean |
| `disasm.py`, `debug.py`, `trace.py`, `console.py`, `state.py`, `cpu.py`, `benchmarks/`, `examples/minimal_host.py` | Own | n/a | clean |
| Docs quoting MAME (`docs/timing.md` line 19 comment, line 155 a code expression; `docs/start-here.md` lines 466-467 a `6800ops.hxx` comment) | MAME 0.285 | BSD-3-Clause, Aaron Giles | **cite**: name licence and holder beside each quote |
| Tests | Own, from the manuals; `tests/vectors/` (MAME-generated corpus) is git-ignored | n/a | clean |

## provenance_check.py run

`provenance_check.py --repo m6800-python --reference m6800-python/reference/mame0285`
(the six BSD-3 MAME files): 5 pairs, all in docs: the quoted MAME comments and one code
expression listed under **cite** above, and one row of a table. No hit in `src/`.
Not run against sim68xx or n6800 (GPL).

## History

No file was ever deleted. The sim68xx and n6800 harnesses arrived in `836f67c` ("Cross-check
the core against sim68xx and the n6800 RTL model") and are in tags `v0.1.0` (`3d89784`, 4
crosscheck files) and `v0.2.0` (`d01b3a5`, 5 files), and in the GitHub release `v0.2.0`'s
source archives (no uploaded assets; not on PyPI). The repository is public. They are
**unclear**, not tainted core code; no rewrite of history is indicated unless Aubrey decides
the harness must not have been in an MIT repository at all.

Not provenance, recorded for a history clean-up: commits `36a488a`, `16d32d0`, `5a0c775`,
`8adae1d`, `d61f339`, `aa2ae4d` (2026-09-12..18) wrote machine paths naming a ROM mirror;
`d7440ca` (2026-10-04) removed them, before either tag. 13 commits carry the author name
"the owner's full name". `docs/handoff-brief.md` still holds machine paths.

## Owed

- SPDX headers: 0 of 70 source files.
- The **cite** items above, and Aubrey's ruling on the two **unclear** harnesses.
