#!/usr/bin/env bash
# Check that the engine finds the one right move in every position of an EPD
# fixture, searching to a fixed depth.
#
#   harness/solve.sh <engine> <fixture.epd> <depth>
#
# Fixture lines are `FEN;bm=<uci>;mate=<n>` as written by make_tactics.py.
# Exits non-zero on the first position the engine gets wrong, naming it.
set -uo pipefail

engine="$1"
fixture="$2"
depth="$3"
solved=0
total=0

while IFS=';' read -r fen bm rest; do
    [[ -z "${fen// }" ]] && continue
    want="${bm#bm=}"
    total=$((total + 1))
    got="$("$engine" go "$depth" $fen 2>/dev/null | sed -n 's/^bestmove //p' | tr -d '\r')"
    if [[ "$got" == "$want" ]]; then
        solved=$((solved + 1))
    else
        echo "wrong move in: $fen"
        echo "  expected $want, played ${got:-<none>}"
        exit 1
    fi
done <"$fixture"

echo "solved $solved/$total at depth $depth"
[[ "$solved" == "$total" ]]
