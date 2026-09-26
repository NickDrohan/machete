#!/usr/bin/env bash
# SUPERSEDED by harness/jobqueue.py (ROADMAP P0-5), which runs any measurement,
# refuses a second runner, waits for a quiet machine and writes the ledger line.
# Kept only until the jobs written for this format have been played.
#
# Run SPRTs one at a time, from job files, as soon as their inputs exist.
#
#   bash harness/sprt_queue.sh          # usually via harness/detach.ps1
#
# The machine judges about eight SPRTs a day and an agent writes candidates
# faster than that, so the two are decoupled: a candidate becomes a job file in
# data/queue/, and this runner plays jobs strictly one at a time, in name order,
# skipping any whose binaries or networks do not exist yet and coming back to
# them. Jobs can be added while it runs. It stops after an hour with nothing to
# do. This is a first, small version of ROADMAP_3500.md P0-5.
#
# A job is a shell file setting:
#   NAME   short id, used for the log, the PGN and the board labels
#   A, B   the two engine binaries (A is the candidate)
#   NET_A, NET_B   their networks
#   SEED   opening seed
#   BOUNDS optional, default "0 10"; "-5 0" for a simplification
#   LABEL_B optional board label for B, default "base"
#
# Write a job file only once its binaries and networks are complete: a job whose
# inputs exist is started at once, and the trainer writes its network after every
# epoch, so point a job at a finished copy, never at a network still training.
#
# Each result is appended to the job file and the file moved to data/queue/done.
set -uo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"
queue=data/queue
mkdir -p "$queue/done"
log=data/sprt_queue.log
say() { printf '\n=== %s  %s ===\n' "$(date '+%m-%d %H:%M')" "$1" | tee -a "$log"; }
heavy() {
    local found
    found=$(tasklist 2>/dev/null | grep -iE "FactoryGame|Satisfactory" | awk '{print $1}' | sort -u | paste -sd ' ' -)
    echo "${found:-none}"
}

say "queue runner started"
idle=0
while [[ $idle -lt 60 ]]; do
    ran=""
    for job in $(ls "$queue"/*.job 2>/dev/null | sort); do
        NAME=""; A=""; B=""; NET_A=""; NET_B=""; SEED=1; BOUNDS="0 10"; LABEL_B="base"
        # shellcheck disable=SC1090
        source "$job"
        # absolute paths: match.py starts each engine in its own folder, where a
        # relative EvalFile would not be found - and machete would then play on
        # with its hand-written evaluation, invalidating the test without a sound
        A=$(realpath -m "$A"); B=$(realpath -m "$B")
        NET_A=$(realpath -m "$NET_A"); NET_B=$(realpath -m "$NET_B")
        missing=""
        for f in "$A" "$B" "$NET_A" "$NET_B"; do [[ -f "$f" ]] || missing="$f"; done
        if [[ -n "$missing" ]]; then continue; fi

        say "$NAME: $(basename "$A") against $(basename "$B"), SPRT [$BOUNDS] (other heavy work: $(heavy))"
        out="data/sprt_$NAME.txt"
        py -3.7 -u harness/match.py "$A" "$B" \
            --option-a "EvalFile=$NET_A" --option-b "EvalFile=$NET_B" \
            --name-a "$NAME" --name-b "$LABEL_B" \
            --sprt $BOUNDS --games 6000 --movetime 200 --concurrency 8 --seed "$SEED" \
            --watch 8765 --pgn "data/games_sprt_$NAME.pgn" > "$out" 2>&1
        verdict=$(grep -E "^games |^elo |accepted H" "$out" | tr '\n' ' ')
        say "$NAME: ${verdict:-no result - see $out} (other heavy work at the end: $(heavy))"
        printf '\n# result %s: %s\n' "$(date '+%m-%d %H:%M')" "${verdict:-none}" >> "$job"
        mv "$job" "$queue/done/"
        ran=1
        break
    done
    if [[ -n "$ran" ]]; then idle=0; else idle=$((idle + 1)); sleep 60; fi
done
say "queue runner stopping: nothing runnable for an hour"
