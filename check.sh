#!/usr/bin/env bash
# Acceptance gates for machete. Every gate is a claim that can fail.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
source "$here/../../scripts/gates.sh"

echo "machete"
build_gates "$here"

# The toolchain claims cross-compilation; this is that claim as a gate.
# Only windows-x86_64 is ever run, so this says "it builds", not "it works".
gate "cross-compiles for linux-x86_64 and linux-aarch64" 0 "$mach" build "$here" --all-targets --quiet

release="$here/out/windows-x86_64/release/bin/machete.exe"

# The harness needs python-chess; a missing reference is a failure, not a skip.
python=""
for candidate in "${PYTHON:-}" python python3; do
    if [[ -n "$candidate" ]] && "$candidate" -c 'import chess' 2>/dev/null; then
        python="$candidate"
        break
    fi
done
gate "python-chess reference available (set PYTHON to override)" 0 test -n "$python"

# Move generation: published node counts, exact.
while IFS=';' read -r fen depth want; do
    [[ -z "$fen" ]] && continue
    gate "perft $depth = $want  ${fen%% *}" 0 "$release" perft "$depth" $fen
    if [[ "$(tr -d '\r\n' <"$gate_out")" != "$want" ]]; then
        printf '  FAIL  counted %s, published %s\n' "$(cat "$gate_out")" "$want"
        fails=$((fails + 1))
    fi
done <"$here/fixtures/perft.epd"

# Move generation: agreement with an independent implementation on positions nobody chose.
if [[ -n "$python" ]]; then
    gate "divide matches python-chess on 300 random positions (depth 2)" 0 \
        "$python" "$here/harness/perft_diff.py" "$release" --random 300 --depth 2 --seed 11
    gate "divide matches python-chess on 30 random positions (depth 3)" 0 \
        "$python" "$here/harness/perft_diff.py" "$release" --random 30 --depth 3 --seed 12
fi

# Search: every mate in the fixtures is found, and only the proved move counts.
# The fixtures were generated and verified by python-chess (harness/make_tactics.py).
gate "finds every mate in one (depth 2)"   0 bash "$here/harness/solve.sh" "$release" "$here/fixtures/mate1.epd" 2
gate "finds every mate in two (depth 4)"   0 bash "$here/harness/solve.sh" "$release" "$here/fixtures/mate2.epd" 4
gate "finds every mate in three (depth 6)" 0 bash "$here/harness/solve.sh" "$release" "$here/fixtures/mate3.epd" 6

# The node count is a signature of the search: ordering, pruning and evaluation
# changes all move it, so it must be updated deliberately.
"$release" bench 2>/dev/null >"$work/bench.txt"
same "bench matches the recorded node count" "$here/fixtures/bench.expected" "$work/bench.txt"

# NNUE: the engine and an independent numpy implementation of the same integer
# arithmetic must agree to the centipawn. The network is generated from a seed
# rather than committed, so this gate covers the code that writes the file as
# well as the code that reads it, and no 400 KB blob lives in git.
# The incremental accumulator is checked by the Mach test suite above, which
# compares it against a from-scratch recompute after every move of a game.
if [[ -n "$python" ]]; then
    "$python" "$here/harness/nnue/reference.py" random "$work/random.nnue" --seed 1 >/dev/null
    gate "network evaluation matches the numpy reference exactly" 0 \
        "$python" "$here/harness/nnue/agree.py" "$release" "$work/random.nnue" --positions 150
fi

# Parallel search: it must find the same move as one thread, and it must
# actually use the cores it was given.
gate "8 threads finds the mate in one" 0 bash -c '
    out=$("$1" smp 8 1000 8/8/5K1k/8/R7/8/8/8 w - - 7 84)
    echo "$out"
    [[ "$out" == *"bestmove a4h4"* ]]' _ "$release"

kiwipete="r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
nps_with() { "$release" smp "$1" 1500 $kiwipete | awk '{for (i = 1; i < NF; i++) if ($i == "nps") print $(i + 1)}'; }
one_thread="$(nps_with 1)"
eight_threads="$(nps_with 8)"
printf '        1 thread: %s nps, 8 threads: %s nps
' "${one_thread:-?}" "${eight_threads:-?}"
# a deliberately loose floor: 8 threads must beat 2x, or the pool is not working
gate "parallel search scales past one thread" 0 \
    test "${eight_threads:-0}" -gt "$(( ${one_thread:-0} * 2 ))"

# UCI: the protocol behaviour a game never exercises, then a self-play soak
# through python-chess, where any illegal move or crash fails the run.
if [[ -n "$python" ]]; then
    gate "speaks UCI, including stop and malformed input" 0 \
        "$python" "$here/harness/protocol.py" "$release"
    gate "plays 6 self-play games with no illegal move or crash" 0 \
        "$python" "$here/harness/match.py" "$release" --games 6 --movetime 30 --max-plies 160
fi

gates_done
