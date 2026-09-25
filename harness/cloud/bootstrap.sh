#!/usr/bin/env bash
# Set a fresh Ubuntu GPU box up to generate machete's training data, and start.
#
#   bash harness/cloud/bootstrap.sh setup      # tools, teachers, gates
#   bash harness/cloud/bootstrap.sh generate   # start generation, detached
#   bash harness/cloud/bootstrap.sh status
#
# Run from the unpacked bundle that harness/cloud/push.sh copies up. The
# private repository is never cloned here, so the box holds no credentials.
#
# The teachers must be the ones our corpus was labelled with. Stockfish 17 has
# an official Linux build; Berserk 13, Alexandria 8.1.12, Obsidian 16.0 and
# Caissa 1.23 do not, so they are built from source at those tags. Then every
# teacher has to reproduce, exactly, the scores the Windows builds give on ten
# fixed positions at a fixed node count (harness/cloud/teacher_check.py). A
# teacher that fails to build or to match is left out of generation, and says
# so - labels from a different source have cost this project 159 Elo before.
set -uo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$here"
T="$here/teachers"
LOG="$here/data/bootstrap.log"
mkdir -p "$T" data
say() { printf '\n=== %s  %s ===\n' "$(date '+%m-%d %H:%M')" "$1" | tee -a "$LOG"; }
SUDO=""; [[ $(id -u) -ne 0 ]] && SUDO="sudo"

build_teachers() {
    say "Stockfish 17 (official Linux build)"
    ( cd "$T" && curl -sSL -o sf.tar \
        https://github.com/official-stockfish/Stockfish/releases/download/sf_17/stockfish-ubuntu-x86-64-avx2.tar \
      && tar xf sf.tar && rm sf.tar ) >> "$LOG" 2>&1

    say "Berserk 13 (source)"
    ( cd "$T" && rm -rf berserk && git clone -q --depth 1 -b 13 https://github.com/jhonnold/berserk.git \
      && cd berserk/src && make -j"$(nproc)" build ARCH=avx2 ) >> "$LOG" 2>&1 \
      || ( cd "$T/berserk/src" && make -j"$(nproc)" ) >> "$LOG" 2>&1

    say "Alexandria 8.1.12 (source)"
    ( cd "$T" && rm -rf Alexandria && git clone -q --depth 1 -b v8.1.12 https://github.com/PGG106/Alexandria.git \
      && cd Alexandria && make -j"$(nproc)" ) >> "$LOG" 2>&1

    say "Obsidian 16.0 (source)"
    ( cd "$T" && rm -rf Obsidian && git clone -q --depth 1 -b v16.0 https://github.com/gab8192/Obsidian.git \
      && cd Obsidian && make -j"$(nproc)" ) >> "$LOG" 2>&1

    say "Caissa 1.23 (source)"
    ( cd "$T" && rm -rf Caissa && git clone -q --depth 1 -b 1.23 https://github.com/Witek902/Caissa.git \
      && cd Caissa && mkdir -p build && cd build \
      && cmake -DCMAKE_BUILD_TYPE=Final ../src && make -j"$(nproc)" ) >> "$LOG" 2>&1
}

write_panel() {
    python3 - "$T" <<'PY'
import json, os, subprocess, sys
T = sys.argv[1]
def pick(folder, pattern):
    out = subprocess.run(["bash", "-c", "find '{}/{}' -maxdepth 4 -type f -perm -u+x -iname '{}' "
                          "! -name '*.sh' ! -name '*.py' 2>/dev/null | head -1".format(T, folder, pattern)],
                         capture_output=True, text=True).stdout.strip()
    return out or None
panel = {
    "Stockfish":  pick("stockfish", "stockfish*"),
    "Berserk":    pick("berserk", "berserk*"),
    "Alexandria": pick("Alexandria", "Alexandria*"),
    "Obsidian":   pick("Obsidian", "Obsidian*"),
    "Caissa":     pick("Caissa", "caissa*"),
}
found = {k: v for k, v in panel.items() if v}
json.dump(found, open(os.path.join(T, "panel.json"), "w"), indent=1)
for k, v in panel.items():
    print("  {:<11} {}".format(k, v or "NOT BUILT"))
PY
}

case "${1:-}" in
setup)
    : > "$LOG"
    say "system packages"
    $SUDO apt-get update -qq >> "$LOG" 2>&1
    $SUDO apt-get install -y -qq build-essential git cmake curl python3-pip >> "$LOG" 2>&1
    python3 -m pip install -q --upgrade chess numpy >> "$LOG" 2>&1
    python3 -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())" 2>/dev/null \
        || python3 -m pip install -q torch >> "$LOG" 2>&1
    chmod +x out/linux-x86_64/release/bin/machete

    say "machete on this machine: bench must read 158026, as it does on Windows"
    out/linux-x86_64/release/bin/machete bench 2>/dev/null | grep '^bench' | tee -a "$LOG"

    build_teachers
    say "teachers found"
    write_panel | tee -a "$LOG"

    say "teacher equivalence against the Windows builds"
    MACHETE_PANEL="$T/panel.json" python3 harness/cloud/teacher_check.py compare \
        harness/cloud/teacher_scores.json 2>&1 | grep -v "Unexpected engine output" | tee -a "$LOG"
    MACHETE_PANEL="$T/panel.json" python3 harness/cloud/teacher_check.py compare \
        harness/cloud/teacher_scores.json 2>/dev/null | tail -1 > "$T/good_teachers.txt"
    say "teachers cleared for generation: $(cat "$T/good_teachers.txt")"
    ;;
generate)
    good=$(cat "$T/good_teachers.txt" 2>/dev/null)
    [[ -z "$good" ]] && { echo "no cleared teachers - run setup first"; exit 1; }
    workers=$(( $(nproc) - 1 ))
    say "generating with $workers workers, teachers: $good"
    MACHETE_PANEL="$T/panel.json" setsid nohup python3 -u harness/nnue/gen.py data/cloud_gen.bin \
        --engines "$good" --positions 400000000 --workers "$workers" --nodes 1500 --seed 2323 \
        > data/cloud_gen.log 2>&1 < /dev/null &
    echo "generator pid $!" | tee -a "$LOG"
    ;;
status)
    tr '\r' '\n' < data/cloud_gen.log 2>/dev/null | grep -E "positions" | tail -1
    ls -la data/cloud_gen.bin* 2>/dev/null | awk '{s+=$5} END {printf "%.0f positions on disk\n", s/70}'
    nvidia-smi --query-gpu=name,utilization.gpu --format=csv,noheader 2>/dev/null
    ;;
*)
    echo "usage: bootstrap.sh setup | generate | status"; exit 2 ;;
esac
