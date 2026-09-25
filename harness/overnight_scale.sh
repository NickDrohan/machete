#!/usr/bin/env bash
# One night, one goal: a stronger network by morning, and a measurement of it.
#
# SIZE-02 showed corpus size is not saturated - about +45 Elo per doubling at
# 42M positions - and 21.3M positions from an earlier run were sitting unused.
# They were made by the same pipeline: the same five teachers, the same opening
# book, and matching score, piece-count and draw distributions (checked on a
# 400,000-position random sample of each before this was written).
#
#   JOIN-A   the 42.2M corpus and the unused 21.3M                 -> 63.6M
#   TRAIN-A  network A on it, on the GPU, while...
#   GEN-03   ...28M new positions are made the same way on the CPU, fresh seed
#   JOIN-B   everything                                            -> about 92M
#   TRAIN-B  network B on it, on the GPU, while...
#   SPRT-A   ...an SPRT asks whether A beats the network that ships
#   SPRT-B   does B beat the network that ships
#
# Nothing is promoted automatically. A verdict is a recommendation, and the
# shipping network changes only after someone has looked at it.
#
# Meant to be started with harness/detach.ps1 -Priority BelowNormal, so it
# survives a Claude session ending and anything interactive on the machine wins
# every contest for the CPU. Generation labels by node count, so its output is
# identical at any speed; the SPRTs record whether other heavy work was running.
set -uo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"
log=data/overnight_scale.log
say() { printf '\n=== %s  %s ===\n' "$(date '+%m-%d %H:%M')" "$1" | tee -a "$log"; }

ENG="$here/out/windows-x86_64/release/bin/machete.exe"
SHIP="$here/net/machete.nnue"
# Corpora on D:, a SATA disk, where every earlier corpus lives; networks on E:.
# Both are spinning disks, so train() reads a corpus through once first: 64 GB
# of RAM holds it in the file cache, and training's random reads then never
# wait on a seek.
C=data/scale
N=E:/machete/scalenets
mkdir -p "$C" "$N"

engines() { tasklist 2>/dev/null | grep -ciE "machete|cont\.exe|rybka" || true; }
heavy() {
    local found
    found=$(tasklist 2>/dev/null | grep -iE "FactoryGame|Satisfactory" | awk '{print $1}' | sort -u | paste -sd ' ' -)
    echo "${found:-none}"
}
train() {   # corpus, out, log
    cat "$1" > /dev/null
    py -3.13 -u harness/nnue/train.py "$1" --epochs 14 --scale 150 --blend 1.0 --seed 7 \
        --out "$2" > "$3" 2>&1
}
sprt() {    # name, network, pgn, seed
    say "$1: $2 against the shipping network (other heavy work running: $(heavy))"
    py -3.7 -u harness/match.py "$ENG" "$ENG" \
        --option-a "EvalFile=$2" --option-b "EvalFile=$SHIP" \
        --name-a "$(basename "$2" .nnue)" --name-b "shipping net" \
        --sprt 0 10 --games 6000 --movetime 200 --concurrency 10 --seed "$4" \
        --watch 8765 --pgn "$3" >> "$log" 2>&1
    say "$1 finished (other heavy work running at the end: $(heavy))"
}

: > "$log"
say "start"
for _ in $(seq 1 240); do [[ "$(engines)" -le 0 ]] && break; sleep 30; done

# ------------------------------------------------------------------- JOIN-A
say "JOIN-A: 42.2M + the unused 21.3M"
py -3.13 -u harness/nnue/join.py data/train2_noseer.bin data/train3.bin "$C/train4.bin" >> "$log" 2>&1

# ------------------------------------------------------ TRAIN-A with GEN-03
say "TRAIN-A on the GPU, GEN-03 on the CPU"
trainer=""
if [[ -f "$C/train4.bin" ]]; then
    train "$C/train4.bin" "$N/net_64M.nnue" data/train_a.log &
    trainer=$!
fi
rm -f "$C/gen3.bin"
py -3.7 -u harness/nnue/gen.py "$C/gen3.bin" \
    --positions 28000000 --workers 12 --nodes 1500 --seed 91 > data/gen3.log 2>&1
say "GEN-03 finished: $(tr '\r' '\n' < data/gen3.log | grep -E 'written' | tail -1)"
if [[ -n "$trainer" ]]; then wait "$trainer"; fi
say "TRAIN-A finished: $(grep -E 'epoch 14 done' data/train_a.log | tail -1)"

# ------------------------------------------------------------------- JOIN-B
if [[ -f "$C/gen3.bin" && -f "$C/train4.bin" ]]; then
    say "JOIN-B: everything"
    py -3.13 -u harness/nnue/join.py "$C/train4.bin" "$C/gen3.bin" "$C/train5.bin" >> "$log" 2>&1
fi

# ------------------------------------------------------ TRAIN-B with SPRT-A
trainer=""
if [[ -f "$C/train5.bin" ]]; then
    say "TRAIN-B on the GPU"
    train "$C/train5.bin" "$N/net_92M.nnue" data/train_b.log &
    trainer=$!
fi
if [[ -f "$N/net_64M.nnue" ]]; then
    sprt "SPRT-A" "$N/net_64M.nnue" data/games_scale_a.pgn 6464
fi
if [[ -n "$trainer" ]]; then wait "$trainer"; fi
say "TRAIN-B finished: $(grep -E 'epoch 14 done' data/train_b.log 2>/dev/null | tail -1)"

# ------------------------------------------------------------------- SPRT-B
if [[ -f "$N/net_92M.nnue" ]]; then
    sprt "SPRT-B" "$N/net_92M.nnue" data/games_scale_b.pgn 9292
fi

say "done - verdicts:"
grep -E "^=== |accepted H|^elo |^games " "$log" | tail -20 > "$log.summary"
cat "$log.summary"
