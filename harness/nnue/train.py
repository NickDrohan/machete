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
from reference import RECORD

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


class Corpus(object):
    """The whole corpus on the device, as the columns training reads.

    Gathering rows from a memmap and building features with numpy kept the GPU
    two-thirds idle: gen5 trained at ~110-330k positions/s with the card at
    26-41%. Held on the card, a batch is an index gather and a few integer ops,
    and the CPU leaves the loop. 55M positions take 3.85 GB.
    """

    CHUNK = 1 << 22

    def __init__(self, data, device):
        self.device = device
        count = len(data)
        self.stm = torch.empty(count, dtype=torch.uint8, device=device)
        self.count = torch.empty(count, dtype=torch.uint8, device=device)
        self.pieces = torch.empty((count, 32), dtype=torch.uint8, device=device)
        self.squares = torch.empty((count, 32), dtype=torch.uint8, device=device)
        self.score = torch.empty(count, dtype=torch.int16, device=device)
        self.result = torch.empty(count, dtype=torch.uint8, device=device)
        for at in range(0, count, self.CHUNK):
            rows = np.asarray(data[at:at + self.CHUNK])
            end = at + len(rows)
            for name in ("stm", "count", "pieces", "squares", "score", "result"):
                column = torch.from_numpy(np.ascontiguousarray(rows[name]))
                getattr(self, name)[at:end] = column.to(device)
        self.slots = torch.arange(32, device=device)[None, :]

    def features(self, index):
        """reference.feature_indices, on the device."""
        pieces = self.pieces[index].long()
        squares = self.squares[index].long()
        live = self.slots < self.count[index].long()[:, None]
        white = pieces * 64 + squares
        black = ((pieces + 6) % 12) * 64 + (squares ^ 56)
        black_to_move = (self.stm[index] == 1)[:, None]
        us = torch.where(black_to_move, black, white)
        them = torch.where(black_to_move, white, black)
        pad = torch.full_like(us, INPUTS)
        return torch.where(live, us, pad), torch.where(live, them, pad)

    def targets(self, index):
        """The number the network is asked to produce, as a win probability."""
        from_search = torch.sigmoid(self.score[index].float() / SCALE)
        result = self.result[index].float() / 2.0
        return LAMBDA * from_search + (1.0 - LAMBDA) * result

    def batches(self, order, size):
        for at in range(0, len(order) - size + 1, size):
            index = torch.from_numpy(np.sort(order[at:at + size])).to(self.device)
            us, them = self.features(index)
            yield us, them, self.targets(index)


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
    parser.add_argument("--blend", type=float, default=-1.0,
                        help="how much of the target is the search score, the rest "
                             "the game result; -1 keeps the default")
    args = parser.parse_args()

    if args.scale:
        reference.set_scale(args.scale)
        globals()["SCALE"] = args.scale
        print("target scale {}".format(args.scale))
    if args.blend >= 0.0:
        globals()["LAMBDA"] = args.blend
        print("target blend {} search / {} result".format(
            args.blend, round(1.0 - args.blend, 2)))

    device = "cuda" if torch.cuda.is_available() else "cpu"
    data = np.memmap(args.data, dtype=RECORD, mode="r")
    print("{:,} positions, training on {}".format(len(data), device))
    if len(data) < args.validation * 4:
        raise SystemExit("not enough positions to hold out a validation set")

    rng = np.random.RandomState(args.seed)
    order = rng.permutation(len(data))
    held_out, training = order[:args.validation], order[args.validation:]

    corpus = Corpus(data, device)
    model = Net().to(device)
    optimiser = torch.optim.Adam(model.parameters(), lr=args.lr)
    schedule = torch.optim.lr_scheduler.StepLR(optimiser, step_size=1, gamma=0.8)
    loss_of = nn.MSELoss()

    for epoch in range(args.epochs):
        model.train()
        rng.shuffle(training)
        # the loss stays on the device and is read back every 100 steps;
        # reading it every step made the CPU wait on the GPU each batch
        started, seen, running = time.time(), 0, torch.zeros((), device=device)
        for us, them, target in corpus.batches(training, args.batch):
            predicted = torch.sigmoid(model(us, them))
            loss = loss_of(predicted, target)
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
            model.clip_weights()
            running += loss.detach()
            seen += 1
            if seen % 100 == 0:
                rate = seen * args.batch / (time.time() - started)
                sys.stdout.write("\repoch {}  {:,} positions  loss {:.5f}  {:,.0f}/s".format(
                    epoch + 1, seen * args.batch, float(running) / seen, rate))
                sys.stdout.flush()
        schedule.step()

        model.eval()
        with torch.no_grad():
            error, count = 0.0, 0
            for us, them, target in corpus.batches(held_out, args.batch):
                predicted = torch.sigmoid(model(us, them))
                error += float(((predicted - target) ** 2).sum())
                count += len(target)
        print("\repoch {} done: training loss {:.5f}, validation {:.5f}      ".format(
            epoch + 1, float(running) / max(1, seen), error / max(1, count)))
        worst = export(model, args.out)
        print("  wrote {} (worst accumulator {:.0f} of 32767)".format(args.out, worst))
    return 0


if __name__ == "__main__":
    sys.exit(main())
