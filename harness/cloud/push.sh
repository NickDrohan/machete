#!/usr/bin/env bash
# Copy what a cloud box needs, and nothing else, then run a bootstrap step there.
#
#   bash harness/cloud/push.sh USER@HOST            # copy the bundle, run setup
#   bash harness/cloud/push.sh USER@HOST generate   # start generation
#   bash harness/cloud/push.sh USER@HOST status
#
# The bundle is the harness, the Linux engine, the shipping network and the
# opening book - about 3 MB. The private repository is not cloned on the box,
# so no GitHub credential ever lives there. SSH uses the dedicated key made for
# these machines, ~/.ssh/qubrid_machete.
set -euo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$here"
target="$1"; step="${2:-setup}"
KEY="$HOME/.ssh/qubrid_machete"
SSH="ssh -i $KEY -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30"

if [[ "$step" == "setup" ]]; then
    [[ -f out/linux-x86_64/release/bin/machete ]] || { echo "build the Linux engine first:"; \
        echo "  mach build . --target linux-x86_64 --profile release"; exit 1; }
    bundle=$(mktemp -d)/machete-cloud.tar.gz
    tar czf "$bundle" --exclude='__pycache__' harness out/linux-x86_64/release/bin/machete \
        net/machete.nnue data/book.epd
    echo "bundle: $(du -h "$bundle" | cut -f1)"
    $SSH "$target" "mkdir -p ~/machete"
    scp -i "$KEY" -o StrictHostKeyChecking=accept-new "$bundle" "$target:~/machete/"
    $SSH "$target" "cd ~/machete && tar xzf machete-cloud.tar.gz && rm machete-cloud.tar.gz"
fi
$SSH "$target" "cd ~/machete && bash harness/cloud/bootstrap.sh $step"
