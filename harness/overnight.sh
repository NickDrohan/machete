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

# How many engine processes are up. Matches an A/B run's renamed binaries too,
# not only machete.exe.
engines() { tasklist 2>/dev/null | grep -ci "machete\|cont\.exe" || true; }

# Whatever is already up when this starts is the baseline, and we wait for the
# count to come back to it rather than to zero.
#
# There is at least one engine on this machine that cannot be killed - taskkill
# and Stop-Process both answer "access is denied" on a process this user owns -
# and it sits at 0% CPU holding no ports. An earlier version of this line
# hardcoded a threshold of 1 for it, which would have been wrong the moment it
# was cleared or a second one appeared. A baseline is right either way and
# needs no comment explaining which number is magic.
baseline=$(engines)
say "waiting for running matches to clear (${baseline} engine process(es) already up)"
for _ in $(seq 1 240); do
    if [[ "$(engines)" -le "${baseline:-0}" ]]; then break; fi
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
