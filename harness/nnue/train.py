"""Train the network and write the file the engine reads.

    python harness/nnue/train.py data/train.bin --epochs 12 --out machete.nnue

Runs under a Python with PyTorch, which is not the Python the rest of the
harness uses: python-chess lives on 3.7 here and torch on 3.13. The two never
have to meet, because this script reads a binary file of positions and writes a
binary file of weights, and nothing in between is shared.

What it learns is a blend of two targets: what a strong engine's search thought
the position was worth, and how the game actually ended. The search score alone
teaches a net to reproduce an evaluation; the result alone is too noisy to
learn from. Mixing them is what everyone settled on, and LAMBDA is the dial.

Weights are clipped every step so that the quantized network cannot overflow
an int16 accumulator. That is a training-time constraint for a run-time
representation, which is unusual enough to be worth saying out loud: without
it a net can train beautifully and then evaluate garbage once quantized.
"""

import argparse
import os
import sys
import time

import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reference
from reference import RECORD, feature_indices

INPUTS = reference.INPUTS
HIDDEN = reference.HIDDEN
QA = reference.QA
QB = reference.QB
SCALE = reference.SCALE

PAD = INPUTS            # a frozen all-zero row, so every position has 32 features
LAMBDA = 0.7            # how much of the target is the search score, the rest the result
CLIP = 127.0 / QB       # the largest weight that survives quantization


class Net(nn.Module):
    def __init__(self):
        super(Net, self).__init__()
        self.features = nn.EmbeddingBag(INPUTS + 1, HIDDEN, mode="sum", padding_idx=PAD)
        self.feature_bias = nn.Parameter(torch.zeros(HIDDEN))
        self.out = nn.Linear(2 * HIDDEN, 1)
        nn.init.uniform_(self.features.weight, -0.01, 0.01)
        with torch.no_grad():
            self.features.weight[PAD].zero_()

    def forward(self, us, them):
        ours = torch.clamp(self.features(us) + self.feature_bias, 0.0, 1.0)
        theirs = torch.clamp(self.features(them) + self.feature_bias, 0.0, 1.0)
        return self.out(torch.cat([ours, theirs], dim=1)).squeeze(1)

    def clip_weights(self):
        with torch.no_grad():
            self.features.weight.clamp_(-CLIP, CLIP)
            self.feature_bias.clamp_(-CLIP, CLIP)
            self.out.weight.clamp_(-CLIP, CLIP)
            self.features.weight[PAD].zero_()


def targets(rows):
    """The number the network is asked to produce, as a win probability."""
    score = rows["score"].astype(np.float32)
    result = rows["result"].astype(np.float32) / 2.0
    from_search = 1.0 / (1.0 + np.exp(-score / SCALE))
    return LAMBDA * from_search + (1.0 - LAMBDA) * result


def batches(data, order, size, device):
    for at in range(0, len(order) - size + 1, size):
        rows = data[np.sort(order[at:at + size])]
        us, them = feature_indices(rows)
        yield (torch.from_numpy(us).to(device),
               torch.from_numpy(them).to(device),
               torch.from_numpy(targets(rows)).to(device))


def export(model, path):
    """Quantize and write, refusing anything that would not survive int16."""
    with torch.no_grad():
        fw = model.features.weight[:INPUTS].cpu().numpy() * QA
        fb = (model.feature_bias.cpu().numpy()) * QA
        ow = model.out.weight[0].cpu().numpy() * QB
        ob = float(model.out.bias[0]) * QA * QB

    fw, fb, ow = np.rint(fw), np.rint(fb), np.rint(ow)
    for name, array in (("feature weights", fw), ("feature bias", fb),
                        ("output weights", ow)):
        if np.abs(array).max() > 32767:
            raise SystemExit("{} do not fit in int16 (max {:.0f})".format(
                name, np.abs(array).max()))
    # the worst case an accumulator can reach: the bias plus the 32 largest
    # weights in any one hidden unit
    worst = np.abs(fb).max() + np.sort(np.abs(fw), axis=0)[-32:].sum(axis=0).max()
    if worst > 32767:
        raise SystemExit("an accumulator could reach {:.0f}, past int16".format(worst))

    reference.save(path, fw.astype(np.int16), fb.astype(np.int16),
                   ow.astype(np.int16), int(round(ob)))
    return worst


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data")
    parser.add_argument("--out", default="machete.nnue")
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch", type=int, default=16384)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--validation", type=int, default=200000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--scale", type=int, default=0,
                        help="centipawn scale for the target; 0 keeps the default")
    args = parser.parse_args()

    if args.scale:
        reference.set_scale(args.scale)
        globals()["SCALE"] = args.scale
        print("target scale {}".format(args.scale))

    device = "cuda" if torch.cuda.is_available() else "cpu"
    data = np.memmap(args.data, dtype=RECORD, mode="r")
    print("{:,} positions, training on {}".format(len(data), device))
    if len(data) < args.validation * 4:
        raise SystemExit("not enough positions to hold out a validation set")

    rng = np.random.RandomState(args.seed)
    order = rng.permutation(len(data))
    held_out, training = order[:args.validation], order[args.validation:]

    model = Net().to(device)
    optimiser = torch.optim.Adam(model.parameters(), lr=args.lr)
    schedule = torch.optim.lr_scheduler.StepLR(optimiser, step_size=1, gamma=0.8)
    loss_of = nn.MSELoss()

    for epoch in range(args.epochs):
        model.train()
        rng.shuffle(training)
        started, seen, running = time.time(), 0, 0.0
        for us, them, target in batches(data, training, args.batch, device):
            predicted = torch.sigmoid(model(us, them))
            loss = loss_of(predicted, target)
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
            model.clip_weights()
            running += float(loss)
            seen += 1
            if seen % 100 == 0:
                rate = seen * args.batch / (time.time() - started)
                sys.stdout.write("\repoch {}  {:,} positions  loss {:.5f}  {:,.0f}/s".format(
                    epoch + 1, seen * args.batch, running / seen, rate))
                sys.stdout.flush()
        schedule.step()

        model.eval()
        with torch.no_grad():
            error, count = 0.0, 0
            for us, them, target in batches(data, held_out, args.batch, device):
                predicted = torch.sigmoid(model(us, them))
                error += float(((predicted - target) ** 2).sum())
                count += len(target)
        print("\repoch {} done: training loss {:.5f}, validation {:.5f}      ".format(
            epoch + 1, running / max(1, seen), error / max(1, count)))
        worst = export(model, args.out)
        print("  wrote {} (worst accumulator {:.0f} of 32767)".format(args.out, worst))
    return 0


if __name__ == "__main__":
    sys.exit(main())
