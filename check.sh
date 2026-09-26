#!/usr/bin/env bash
# Acceptance gates for machete. Every gate is a claim that can fail.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
source "$here/scripts/gates.sh"

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

# The output reconstruction multiplies a dot product by the centipawn scale,
# and at the quantization limits that product exceeds int32 by 16%: it is safe
# only because the sum is widened to 64 bits first. Nothing else here would
# notice if that widening were removed, so this gate exists to notice.
if [[ -n "$python" ]]; then
    for sign in 1 -1; do
        "$python" "$here/harness/nnue/reference.py" extreme "$work/extreme.nnue" --sign $sign >/dev/null
        gate "worst-case output arithmetic does not overflow (sign $sign)" 0 \
            "$python" "$here/harness/nnue/agree.py" "$release" "$work/extreme.nnue" --positions 12
    done
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
    # the machine's one queue: a throwaway queue, two runners at once, two jobs
    gate "job queue runs jobs one at a time and records each in the ledger" 0 \
        "$python" "$here/harness/test_jobqueue.py"
fi

# A GUI starts the engine with no options: it must find machete.nnue in its own
# folder, or an installed engine plays on the hand-written evaluation unless
# its user finds EvalFile. Both ways round: beside the network it must load
# it, and alone it must say so rather than claim one.
mkdir -p "$work/installed"
cp "$release" "$work/installed/machete.exe"
cp "$here/net/machete.nnue" "$work/installed/machete.nnue"
gate "loads the network beside the executable, as a GUI starts it" 0 bash -c '
    printf "uci\nquit\n" | "$1" | grep -q "option name EvalFile type string default .*machete.nnue"' _ \
    "$work/installed/machete.exe"
rm "$work/installed/machete.nnue"
gate "reports no network when there is none beside it" 0 bash -c '
    printf "uci\nquit\n" | "$1" | grep -q "option name EvalFile type string default <empty>"' _ \
    "$work/installed/machete.exe"

# The binpack decoder (src/binpack.mach) against its Python reference. The
# fixture is the first chunk of linrock's test80-2023-11-nov-2tb7p.min-v2
# (Leela Chess Zero training data, Open Database License): 451,559 positions.
# leela_chunk.sha256 is the hash of harness/nnue/leela.py's records for it -
#   python harness/nnue/leela.py fixtures/leela_chunk.binpack --out X --positions 100000000 --workers 1
# - identical under Python 3.7 and 3.13; running leela.py here would add two
# minutes, so the hash stands in for it the way bench.expected does.
binpack="$here/out/windows-x86_64/release/bin/binpack.exe"
gate "binpack decoder writes leela.py's records byte for byte" 0 bash -c '
    "$1" convert "$2" "$3" "$4" 100000000 1 >/dev/null &&
    [[ "$(sha256sum "$3" | cut -d" " -f1)" == "$(tr -d "\r\n" <"$5")" ]]' _ \
    "$binpack" "$here/fixtures/leela_chunk.binpack" "$work/leela_chunk.bin" \
    "$here/harness/nnue/leela_scale.json" "$here/fixtures/leela_chunk.sha256"
# one flipped bit in the move text puts every later index out of step, and the
# decoder must say so rather than write plausible nonsense
gate "binpack decoder refuses a corrupted chunk" 2 bash -c '
    head -c 5000 "$2" >"$3"; printf "\x5a" >>"$3"; tail -c +5002 "$2" >>"$3"
    "$1" check "$3" 100000000' _ \
    "$binpack" "$here/fixtures/leela_chunk.binpack" "$work/corrupt.binpack"

gates_done
