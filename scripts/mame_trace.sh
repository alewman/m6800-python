#!/bin/sh
# m6800-python: produce a MAME 0.285 instruction trace of a 6800-family CPU.
#
#   scripts/mame_trace.sh [game] [seconds] [tag] [workdir]
#
# Defaults: dragrace, 2 emulated seconds, :maincpu, ./mame-work.  Output in the
# work directory: <game>.trace (MAME's own disassembly) and error.log (the
# register log; see docs/mame-oracle.md for the column order).  ROMs are read
# in place with -rompath; nothing is copied and nothing is committed.
set -eu
GAME=${1:-dragrace}
SECONDS_TO_RUN=${2:-2}
TAG=${3:-:maincpu}
WORK=${4:-mame-work}
MAME=${MAME:-/usr/games/mame}
ROMPATH=${ROMPATH:-"/data/emu/source/myrient.erista.me/files/MAME/ROMs (non-merged)"}
SCRIPT=$(cd "$(dirname "$0")" && pwd)/mame_trace.lua

mkdir -p "$WORK"
cd "$WORK"
rm -f error.log "$GAME.trace"
M6800_TRACE_TAG="$TAG" M6800_TRACE_FILE="$GAME.trace" M6800_PRESS="${M6800_PRESS:-}" \
"$MAME" "$GAME" \
  -rompath "$ROMPATH" \
  -homepath "$PWD/mame-home" \
  -video none -sound none -nothrottle -noreadconfig -skip_gameinfo \
  -debug -debugger none -log \
  -seconds_to_run "$SECONDS_TO_RUN" \
  -autoboot_script "$SCRIPT"
echo "instruction lines: $(grep -cE '^[0-9A-F]+( [0-9A-F]+){6} [0-9]+$' error.log || true)"
