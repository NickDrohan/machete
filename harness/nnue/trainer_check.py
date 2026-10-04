"""Hold the Mach trainer (src/train.mach) to train.py, step by step.

    python harness/nnue/trainer_check.py CORPUS.bin TRAIN_EXE [--steps 20] [--batch 1024]
        [--threads 4] [--lr 0.001] [--scale 150] [--blend 0.7] [--seed 1]

Builds train.py's own Net at the engine's width, writes its starting weights
as a .flat file, and trains it with train.py's pieces - the same targets, the
same loss, torch's Adam, clip_weights - for --steps batches of --batch
positions taken from the front of the corpus in file order. The Mach trainer
does the same from the same .flat file (`train check`). Both report every
step's loss; then the final weights are compared.

The two sum floats in different orders (torch's matmul blocks, the Mach
trainer splits hidden units between threads), so they are not bit-identical.
Over a few steps (20 or fewer) every loss agrees to LOSS_TOL relative and every
weight to WEIGHT_TOL absolute. Over many steps Adam amplifies rounding: a weight
whose gradient is nearly zero moves a full learning-rate step in whichever
direction its rounding points. So a long run is judged against a yardstick:
torch against itself with every batch's positions in another order - the same
arithmetic, rounded differently. The Mach trainer passes if it is no further
from torch than torch is from itself, within YARDSTICK_SLACK. Exit 0 on a pass.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reference  # noqa: E402
import train  # noqa: E402
from reference import RECORD  # noqa: E402

LOSS_TOL = 1e-4
WEIGHT_TOL = 1e-4
YARDSTICK_SLACK = 2.0


def flat_of(model):
    with torch.no_grad():
        parts = [model.features.weight[:train.PAD], model.feature_bias, model.out.weight, model.out.bias]
        return [p.detach().cpu().numpy().astype("<f4").reshape(-1).copy() for p in parts]


def write_flat(path, parts):
    with open(path, "wb") as handle:
        for p in parts:
            handle.write(p.tobytes())


def read_flat(path, hidden):
    blob = np.fromfile(path, dtype="<f4")
    sizes = [train.PAD * hidden, hidden, reference.BUCKETS * 2 * hidden, reference.BUCKETS]
    out, at = [], 0
    for n in sizes:
        out.append(blob[at:at + n])
        at += n
    assert at == len(blob), "flat file has %d floats, expected %d" % (len(blob), at)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus")
    parser.add_argument("trainer")
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--batch", type=int, default=1024)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--scale", type=int, default=150)
    parser.add_argument("--blend", type=float, default=0.7)
    parser.add_argument("--hidden", type=int, default=768)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    torch.set_num_threads(4)
    train.SCALE, train.LAMBDA = args.scale, args.blend
    model = train.Net(args.hidden)
    work = tempfile.mkdtemp(prefix="trainer_check_")
    init, torch_out, mach_out = (os.path.join(work, n) for n in ("init.flat", "torch.flat", "mach.flat"))
    write_flat(init, flat_of(model))

    rows = np.fromfile(args.corpus, dtype=RECORD, count=args.steps * args.batch)
    if len(rows) < args.steps * args.batch:
        raise SystemExit("the corpus holds only %d records" % len(rows))
    start = [p.copy() for p in flat_of(model)]
    t0 = time.time()
    torch_losses = run_torch(model, rows, args, permute=False)
    torch_seconds = time.time() - t0
    write_flat(torch_out, flat_of(model))
    twin = train.Net(args.hidden)
    load_into(twin, start)
    twin_losses = run_torch(twin, rows, args, permute=True)
    twin_flat = flat_of(twin)

    t0 = time.time()
    run = subprocess.run([args.trainer, "check", args.corpus, init, mach_out, str(args.steps), str(args.batch),
                          str(args.lr), str(args.threads), str(args.scale), str(args.blend)],
                         capture_output=True, text=True)
    mach_seconds = time.time() - t0
    if run.returncode != 0:
        print(run.stdout, run.stderr)
        raise SystemExit("the Mach trainer failed (exit %d)" % run.returncode)
    mach_losses = [int(line.split()[3]) / 1e9 for line in run.stdout.splitlines() if line.startswith("step ")]
    return report(args, torch_losses, twin_losses, mach_losses, read_flat(torch_out, args.hidden), twin_flat,
                  read_flat(mach_out, args.hidden), torch_seconds, mach_seconds)


def load_into(model, parts):
    with torch.no_grad():
        model.features.weight[:train.PAD] = torch.from_numpy(parts[0].reshape(train.PAD, -1))
        model.features.weight[train.PAD].zero_()
        model.feature_bias.copy_(torch.from_numpy(parts[1]))
        model.out.weight.copy_(torch.from_numpy(parts[2].reshape(reference.BUCKETS, -1)))
        model.out.bias.copy_(torch.from_numpy(parts[3]))


def run_torch(model, rows, args, permute):
    optimiser = torch.optim.Adam(model.parameters(), lr=args.lr)
    loss_of = torch.nn.MSELoss()
    losses = []
    shuffle = np.random.RandomState(99)
    for step in range(args.steps):
        batch = rows[step * args.batch:(step + 1) * args.batch]
        if permute:
            batch = batch[shuffle.permutation(len(batch))]
        us, them = reference.feature_indices(batch)
        us, them = torch.from_numpy(us), torch.from_numpy(them)
        bucket = torch.from_numpy(np.clip((batch["count"].astype(np.int64) - 2) // 4, 0, reference.BUCKETS - 1))
        target = (args.blend * torch.sigmoid(torch.from_numpy(batch["score"].astype(np.float32)) / args.scale)
                  + (1 - args.blend) * torch.from_numpy(batch["result"].astype(np.float32)) / 2.0)
        predicted = torch.sigmoid(model(us, them, bucket))
        loss = loss_of(predicted, target)
        optimiser.zero_grad()
        loss.backward()
        optimiser.step()
        model.clip_weights()
        losses.append(float(loss))
    return losses


def gaps(losses_a, losses_b, flat_a, flat_b):
    loss = max(abs(a - b) / max(abs(a), 1e-12) for a, b in zip(losses_a, losses_b))
    weights = [float(np.abs(a - b).max()) for a, b in zip(flat_a, flat_b)]
    mean = [float(np.abs(a - b).mean()) for a, b in zip(flat_a, flat_b)]
    return loss, weights, mean


def report(args, torch_losses, twin_losses, mach_losses, torch_flat, twin_flat, mach_flat, torch_s, mach_s):
    if len(mach_losses) != args.steps:
        print("the Mach trainer reported %d steps of %d" % (len(mach_losses), args.steps))
        return 1
    for step in sorted(set((0, 1, 2, args.steps - 1))):
        a, b, c = torch_losses[step], mach_losses[step], twin_losses[step]
        print("step %4d  torch %.9f  mach %.9f  torch reordered %.9f" % (step + 1, a, b, c))
    ml, mw, mm = gaps(torch_losses, mach_losses, torch_flat, mach_flat)
    yl, yw, ym = gaps(torch_losses, twin_losses, torch_flat, twin_flat)
    names = ("feature weights", "feature bias", "output weights", "output bias")
    print("%-16s %25s %27s" % ("", "torch vs mach: max, mean", "torch vs reordered: max, mean"))
    for k, name in enumerate(names):
        print("%-16s %12.2e %12.2e %13.2e %13.2e" % (name, mw[k], mm[k], yw[k], ym[k]))
    print("losses: torch vs mach %.2e relative, torch vs reordered torch %.2e" % (ml, yl))
    if args.steps <= 20:
        ok = ml <= LOSS_TOL and max(mw) <= WEIGHT_TOL
        rule = "exact: losses within %.0e, weights within %.0e" % (LOSS_TOL, WEIGHT_TOL)
    else:
        ok = ml <= YARDSTICK_SLACK * max(yl, LOSS_TOL) and all(
            mm[k] <= YARDSTICK_SLACK * max(ym[k], 1e-7) for k in range(4))
        rule = "within %.0fx of torch's own reordering noise in losses and mean weight gaps" % YARDSTICK_SLACK
    print("%s (%s); %d steps of %d; torch %.1fs on the CPU, mach %.1fs with %d threads"
          % ("PASS" if ok else "FAIL", rule, args.steps, args.batch, torch_s, mach_s, args.threads))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
