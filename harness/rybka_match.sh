#!/usr/bin/env bash
# machete against Rybka 2.3.2a, done properly.
#
# Everything machete had played before this was at a fixed time per move, and
# every opening was four random plies - which twice produced 1. f3 e5 2. g4
# Qh4#, scored as a win for an engine that never moved. This is the opposite on
# every count:
#
#   a real clock      5 minutes + 3 seconds a move, kept by the harness the way
#                     a GUI keeps it; a flag is a loss (100 ms of pipe margin)
#   real openings     200 positions from real games, each one Stockfish rates
#                     within 0.5 of level, one per pawn structure, every one
#                     played twice with the colours reversed
#   equal resources   one search thread each, 128 MB of hash each (machete's
#                     is fixed at 128, so Rybka's is set to match), no pondering
#   played to the end no adjudication and no move cap: mate, or a draw by the
#                     rules
#   a quiet machine   six games at a time, so each engine has roughly a
#                     physical core of this 12-core machine to itself
#
# Every game is saved with its clock times. Waits for anything already running.
set -uo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"

engines() { tasklist 2>/dev/null | grep -ci "machete\|cont\.exe\|ybka" || true; }
for _ in $(seq 1 480); do
    [[ "$(engines)" -le 0 ]] && break
    sleep 30
done

rybka="$(py -3.7 -c "import sys; sys.path.insert(0, 'harness'); import arena; print(arena.engine('Rybka', 'Rybkav2.3.2a.mp.x64.exe'))")"

py -3.7 -u harness/match.py "$here/out/windows-x86_64/release/bin/machete.exe" "$rybka" \
    --option-a "EvalFile=$here/net/machete.nnue" --option-a "Threads=1" \
    --option-b "Max CPUs=1" --option-b "Hash=128" \
    --tc 300+3 --margin 100 \
    --book harness/books/balanced_200.epd --max-plies 0 \
    --games 400 --concurrency 6 --seed 2008 \
    --name-a machete --name-b "Rybka 2.3.2a" \
    --watch 8765 --pgn data/games_rybka_match.pgn
