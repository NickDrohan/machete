#!/usr/bin/env bash
# Bring a cloud box's generated data and logs home.
#
#   bash harness/cloud/pull.sh USER@HOST
#
# Generation writes one shard per worker and joins them only when it finishes,
# so an overnight run that is still going has only shards. They are copied as
# they are and joined here with harness/nnue/join.py, after a check that each
# is a whole number of records - a shard caught mid-write is trimmed to the
# last complete one rather than read as garbage.
set -euo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$here"
target="$1"
KEY="$HOME/.ssh/qubrid_machete"
dest="data/cloud"
mkdir -p "$dest"
scp -i "$KEY" "$target:~/machete/data/*.log" "$dest/" || true
scp -i "$KEY" "$target:~/machete/data/cloud_gen.bin*" "$dest/"
py -3.13 - "$dest" <<'PY'
import glob, os, sys
total = 0
for path in sorted(glob.glob(os.path.join(sys.argv[1], "cloud_gen.bin*"))):
    size = os.path.getsize(path)
    whole = size - size % 70
    if whole != size:
        with open(path, "r+b") as handle:
            handle.truncate(whole)
        print("trimmed {} by {} bytes to its last whole record".format(path, size - whole))
    total += whole // 70
print("{:,} positions pulled".format(total))
PY
