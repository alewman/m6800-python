# Documents

| Page | What it is for |
| --- | --- |
| [start-here.md](start-here.md) | The 6800 primer: sources, the family and what is out of scope, registers and CC, the six addressing modes, the complete instruction table with 6800 *and* 6801/6803 cycle counts and flags, the 6801/6803 additions, DAA and the half-carry, the vector table, the stack frame, interrupt entry rules, `WAI`, and the embedding contract |
| [timing.md](timing.md) | The cycle model; the 72 shared opcodes the 6801 runs faster and the three it runs slower; interrupt and reset costs measured from a real trace; where MAME's interrupt sampling is untrustworthy; and the host contract, worked out in full for the Williams arcade sound board (MC6808 at 894,886 Hz, one PIA), with a table of arcade clocks taken from MAME's drivers |
| [undocumented-behavior.md](undocumented-behavior.md) | HCF (`$9D`, `$DD`) with Wheeler 1977 and the 2019 hardware measurement; `BRN` and `JSR`-direct, the 6801 instructions MAME allows on a 6800; the store-immediate family; the 53/31 illegal opcodes MAME merely logs; the undefined flags; `WAI`'s corner. Every claim tiered, `[unverified]` and `[MAME only]` marked |
| [validation.md](validation.md) | The oracle inventory with tier, licence, URL, revision and limits: the SingleStepTests non-existence check, the absence of any corpus, exerciser, diagnostic or bus decoder for this family, the pinned manual and MAME-source hashes, the independent emulators worth building, and the seven-rung plan in tier order |
| [disassembly.md](disassembly.md) | The disassembler: Motorola syntax, parts, undocumented policies, and its checks against the core and MAME |
| [debug-session.md](debug-session.md) | `python -m m6800_python`, the command debugger, `DebugSession`, watchpoints |
| [cpu-state.md](cpu-state.md) | `capture_state()` / `restore_state()` and what the state holds |
| [trace-schema.md](trace-schema.md) | The JSON Lines trace format for comparing this core with a port |
| [mame-oracle.md](mame-oracle.md) | MAME 0.285 headless tracing: the working command line, the Lua script, the register names, the gotchas confirmed and corrected, and three verified runs — Drag Race's MC6800, Robotron's MC6808 sound board (and how it was driven out of its self-loop), Knuckle Joe's MC6803 |
| [conformance.md](conformance.md) | Manifests, the shared host, the reference traces and the differ: how another core proves it is this one |
| [api-stability.md](api-stability.md) | What the public API promises, what may still change (the `[unverified]` cycle counts), and the versioning policy |
| [handoff-brief.md](handoff-brief.md) | The brief a build session starts from: context, task, seven milestones each with an acceptance test in oracle-tier order, constraints, open questions, what done looks like |

Scripts these pages refer to:

| Script | What it does |
| --- | --- |
| `scripts/mame_trace.sh`, `scripts/mame_trace.lua` | Trace a 6800-family CPU headlessly under MAME 0.285 (`mame-oracle.md`) |
| `scripts/fetch_mame_source.py` | Fetch the six files of MAME 0.285's 6800 core, SHA-256 verified, into `reference/mame0285/` — the version every citation refers to |
| `scripts/fetch_reference_docs.py` | Fetch the four Motorola bitsavers scans, SHA-256 verified, into `reference/` |
| `scripts/extract_manual_tables.py` | Read Appendix A of M68PRM and M6801RM; regenerate `start-here.md`'s instruction table (`--markdown`) and diff the manuals against MAME (`--report`) |
| `scripts/dump_mame_tables.py` | Print MAME's view of the instruction table from the pinned MAME sources, as a detector (its flag column is MAME's comments, not to be trusted) |
| `scripts/mame_corpus.py`, `scripts/compare_mame_corpus.py` | Rung 2: build MAME 0.285's own 6800 handlers into a single-step corpus generator, and replay the corpus through the core |
| `scripts/replay_trace.py` | Rung 3: replay watchpoint-logged MAME traces of real arcade code (Drag Race, Knuckle Joe, Kid Niki) |
| `scripts/williams_capture.lua`, `scripts/williams_sound.py` | Rung 4: capture Robotron's sound commands and PIA writes from MAME, and run a Williams sound board on the core against them |
| `scripts/williams_board.py`, `scripts/williams_debug.py` | The Williams sound board (memory map, PIA, command schedule) shared by rung 4 and the debugger; step through it with its PIA working |
| `scripts/crosscheck/sim68xx.py`, `scripts/crosscheck/n6800.py` | Rung 5: three-way diffs against sim68xx and the n6800 RTL model (cloned into the gitignored `third_party/`) |

Nothing they fetch is committed: `reference/`, `tests/vectors/`, `*.trace`,
`error.log`, `mame-work/` and `mame-home/` are all gitignored.
