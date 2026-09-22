#!/usr/bin/env bash
# One night of work, in the order that a partial run is still worth having.
#
# Waits for whatever is already playing to finish, so nothing contends for the
# cores and no measurement is taken on a busy machine. Each stage writes its
# own log and its own result file; a stage that fails does not stop the ones
# after it, because eight unattended hours that produce two answers beat eight
# that produce none.
set -uo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"

engine="$here/out/windows-x86_64/release/bin/machete.exe"
net="$here/net/machete.nnue"
log="$here/data/overnight.log"

say() { printf '\n=== %s  %s ===\n' "$(date '+%H:%M')" "$1" | tee -a "$log"; }

say "waiting for running matches to clear"
for _ in $(seq 1 240); do
    # matches an A/B run's renamed binaries too, not only machete.exe
    running=$(tasklist 2>/dev/null | grep -ci "machete" || echo 0)
    # 1 is the known unkillable zombie; anything above it is a live match
    if [[ "${running:-0}" -le 1 ]]; then break; fi
    sleep 30
done
say "machine is quiet, starting"

# 1. The experiment with the largest blast radius. If machete's score falls as
#    the budget rises, the 2769 rating is inflated on the CCRL scale it is
#    quoted on, and the next several decisions change.
say "SCALE-01: time-control scaling"
py -3.7 -u harness/scaling.py "$engine" --net "$net" \
    --games 60 --movetimes 200,800,3200 --concurrency 6 \
    --out data/scaling.json >> "$log" 2>&1

# 2. Settles a prediction on record: with the corpus contamination down from
#    7.3% to 2.9%, the game-result term should regain some value and the
#    optimum should fall back below 1.0. If it does not, the explanation for
#    the earlier -129 was wrong.
say "BLEND-01: re-sweep the result blend on the clean corpus"
for blend in 0.9 0.8; do
    py -3.13 -u harness/nnue/train.py data/train2_even.bin \
        --epochs 14 --scale 150 --blend "$blend" \
        --out "data/machete_b${blend/./}.nnue" >> "$log" 2>&1
    py -3.7 -u harness/match.py "$engine" "$engine" \
        --option-a "EvalFile=$here/data/machete_b${blend/./}.nnue" \
        --option-b "EvalFile=$net" \
        --games 400 --movetime 300 --concurrency 5 --seed 2020 --watch 0 \
        --pgn "" > "data/match_b${blend/./}.txt" 2>&1
    printf 'blend %s: %s\n' "$blend" \
        "$(grep -E '^elo' "data/match_b${blend/./}.txt" || echo 'no result')" | tee -a "$log"
done

# 3. Whatever time is left goes to positions. Shards are written per worker and
#    joined at the end, so stopping this at any point loses nothing.
say "GEN-02: more positions into a fresh file"
py -3.7 -u harness/nnue/gen.py data/train3.bin \
    --positions 60000000 --workers 13 --nodes 1500 --seed 77 >> "$log" 2>&1

say "done"
