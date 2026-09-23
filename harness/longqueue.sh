#!/usr/bin/env bash
# A night (or two) of unattended work, ordered so a partial run still answers
# something. Each stage writes its own result file and a stage that fails does
# not stop the ones after it.
#
# Written because prompting stopped, not because the work did.
set -uo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"
log=data/longqueue.log
say() { printf '\n=== %s  %s ===\n' "$(date '+%m-%d %H:%M')" "$1" | tee -a "$log"; }

ENG="$here/out/windows-x86_64/release/bin/machete.exe"
NET="$here/net/machete.nnue"
engines() { tasklist 2>/dev/null | grep -ci "machete\|cont\.exe" || true; }
wait_quiet() {
    for _ in $(seq 1 1440); do
        [[ "$(engines)" -le 0 ]] && return
        sleep 30
    done
}

say "waiting for whatever is running now"
wait_quiet

# ---------------------------------------------------------------- EG-00
# The baseline for the defect, before anything is changed. Cheap, and without
# it the later numbers have nothing to be compared against.
say "EG-00: endgame conversion, current network"
py -3.7 -u harness/endgame_suite.py "$ENG" --net "$NET" --movetime 500 \
    > data/endgames_before.txt 2>&1
tail -4 data/endgames_before.txt | tee -a "$log"

# ---------------------------------------------------------------- SIZE-02
# SIZE-01 died at 740 of 2,000 games on a transient engine death and reported
# nothing. The driver now retries a block and reports what it played, so this
# is the same question asked again rather than a new one: does more data still
# buy Elo, or has 8M saturated?
say "SIZE-02: does corpus size still buy Elo (re-run after the crash)"
py -3.7 -u harness/tournament.py "$ENG" \
    --net "2M=E:/machete/sizenets/2000000.nnue" \
    --net "8M=E:/machete/sizenets/8000000.nnue" \
    --net "control=E:/machete/sizenets/8000000.nnue" \
    --net "20M=E:/machete/sizenets/20000000.nnue" \
    --net "42M=E:/machete/sizenets/42237185.nnue" \
    --games 200 --block 5 --movetime 200 --concurrency 11 --seed 5150 \
    --watch 8770 --pgn data/games_sizes.pgn \
    --out data/tournament_sizes.json >> "$log" 2>&1
wait_quiet

# ---------------------------------------------------------------- EG-01
# Arm A: our own conversion data, on our own label scale. The generator starts
# from won endgames and plays them to mate with adjudication off, which is
# exactly what gen.py excludes by construction.
say "EG-01: generating endgame conversion data"
py -3.7 -u harness/nnue/endgames.py data/endgames.bin \
    --positions 3000000 --workers 12 --nodes 20000 --seed 424 >> "$log" 2>&1
ls -l data/endgames.bin 2>/dev/null | tee -a "$log"

say "EG-01: training the baseline corpus plus the endgame supplement"
py -3.13 -u harness/nnue/join.py data/train2_noseer.bin data/endgames.bin \
    E:/machete/egnets/mixed.bin >> "$log" 2>&1
py -3.13 -u harness/nnue/train.py E:/machete/egnets/mixed.bin \
    --epochs 14 --scale 150 --blend 1.0 --seed 7 \
    --out E:/machete/egnets/endgame.nnue >> "$log" 2>&1

say "EG-02: endgame conversion, network trained with the supplement"
py -3.7 -u harness/endgame_suite.py "$ENG" --net E:/machete/egnets/endgame.nnue \
    --movetime 500 > data/endgames_after.txt 2>&1
tail -4 data/endgames_after.txt | tee -a "$log"
wait_quiet

# ---------------------------------------------------------------- EG-03
# Conversion is only worth having if it costs nothing elsewhere. A control
# entry duplicates the baseline so the noise floor is measured in the same run.
say "EG-03: does the endgame supplement cost Elo in ordinary play"
py -3.7 -u harness/tournament.py "$ENG" \
    --net "baseline=$NET" \
    --net "control=$NET" \
    --net "endgame=E:/machete/egnets/endgame.nnue" \
    --games 400 --block 5 --movetime 200 --concurrency 11 --seed 717 \
    --watch 8770 --pgn data/games_endgame.pgn \
    --out data/tournament_endgame.json >> "$log" 2>&1
wait_quiet

# ---------------------------------------------------------------- SPRT-02
# The other unresolved change on record. Continuation history is now settled
# (H0, -6 +/- 16); this is the one still owed.
say "SPRT-02: the corpus rebalance, +23 +/- 34 and never settled"
py -3.7 -u harness/match.py "$ENG" "$ENG" \
    --option-a "EvalFile=$here/data/machete_even.nnue" \
    --option-b "EvalFile=$NET" \
    --sprt 0 10 --games 12000 --movetime 200 --concurrency 11 --seed 3131 \
    --watch 8765 --pgn "" >> "$log" 2>&1
wait_quiet

# ---------------------------------------------------------------- LOAD-01
# The assumption every pooled Elo figure rests on: that a paired match survives
# a busy machine because both sides are slowed equally. Never tested. The same
# A/B is run twice, once alone and once beside a second copy of itself.
say "LOAD-01: is a paired result robust to load (idle run)"
py -3.7 -u harness/match.py "$ENG" "$ENG" \
    --option-a "EvalFile=E:/machete/sizenets/2000000.nnue" \
    --option-b "EvalFile=E:/machete/sizenets/42237185.nnue" \
    --games 600 --movetime 200 --concurrency 6 --seed 2468 \
    --watch 0 --pgn "" > data/load_idle.txt 2>&1
grep -E "^elo|^score" data/load_idle.txt | tee -a "$log"

say "LOAD-01: the same A/B with the machine deliberately busy"
py -3.7 -u harness/match.py "$ENG" "$ENG" \
    --option-a "EvalFile=E:/machete/sizenets/8000000.nnue" \
    --option-b "EvalFile=E:/machete/sizenets/20000000.nnue" \
    --games 600 --movetime 200 --concurrency 10 --seed 1357 \
    --watch 0 --pgn "" > data/load_noise.txt 2>&1 &
noise=$!
py -3.7 -u harness/match.py "$ENG" "$ENG" \
    --option-a "EvalFile=E:/machete/sizenets/2000000.nnue" \
    --option-b "EvalFile=E:/machete/sizenets/42237185.nnue" \
    --games 600 --movetime 200 --concurrency 6 --seed 2468 \
    --watch 0 --pgn "" > data/load_busy.txt 2>&1
wait $noise
grep -E "^elo|^score" data/load_busy.txt | tee -a "$log"
say "LOAD-01: idle and busy above should agree inside their bars"

say "everything finished"
