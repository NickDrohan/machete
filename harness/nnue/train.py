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
BUCKETS = reference.BUCKETS
QA = reference.QA
QB = reference.QB
SCALE = reference.SCALE

PAD = INPUTS            # a frozen all-zero row, so every position has 32 features
LAMBDA = 0.7            # how much of the target is the search score, the rest the result
CLIP = 127.0 / QB       # the largest weight that survives quantization


class Net(nn.Module):
    def __init__(self, hidden):
        super(Net, self).__init__()
        self.features = nn.EmbeddingBag(INPUTS + 1, hidden, mode="sum", padding_idx=PAD)
        self.feature_bias = nn.Parameter(torch.zeros(hidden))
        # one output layer per band of piece counts (reference.bucket); all
        # are computed and the position's own is picked, which on a GPU costs
        # less than gathering eight weight rows per position
        self.out = nn.Linear(2 * hidden, BUCKETS)
        nn.init.uniform_(self.features.weight, -0.01, 0.01)
        with torch.no_grad():
            self.features.weight[PAD].zero_()

    def forward(self, us, them, bucket):
        ours = torch.clamp(self.features(us) + self.feature_bias, 0.0, 1.0)
        theirs = torch.clamp(self.features(them) + self.feature_bias, 0.0, 1.0)
        every = self.out(torch.cat([ours, theirs], dim=1))
        return every.gather(1, bucket[:, None]).squeeze(1)

    def clip_weights(self):
        with torch.no_grad():
            self.features.weight.clamp_(-CLIP, CLIP)
            self.feature_bias.clamp_(-CLIP, CLIP)
            self.out.weight.clamp_(-CLIP, CLIP)
            self.features.weight[PAD].zero_()


class Corpus(object):
    """The whole corpus on the device, packed, as the columns training reads.

    Gathering rows from a memmap and building features with numpy kept the GPU
    two-thirds idle: gen5 trained at ~110-330k positions/s with the card at
    26-41%. Held on the card, a batch is an index gather and a few integer ops,
    and the CPU leaves the loop.

    A record is 70 bytes on disk; here it is 28. The occupied squares are one
    64-bit board and the pieces on them are 4-bit codes in square order, so
    the count is the board's population and the squares are its set bits.
    That puts about 190M positions on an 8 GB card rather than 80M.
    """

    CHUNK = 1 << 22
    BYTES = 28

    def __init__(self, sources, device):
        """`sources` is a list of (records, how many to take from the front)."""
        self.device = device
        count = sum(take for _, take in sources)
        self.occupied = torch.empty(count, dtype=torch.int64, device=device)
        self.codes = torch.empty((count, 16), dtype=torch.uint8, device=device)
        self.stm = torch.empty(count, dtype=torch.uint8, device=device)
        self.score = torch.empty(count, dtype=torch.int16, device=device)
        self.result = torch.empty(count, dtype=torch.uint8, device=device)
        at = 0
        for data, take in sources:
            for first in range(0, take, self.CHUNK):
                rows = np.asarray(data[first:min(take, first + self.CHUNK)])
                occupied, codes = pack(rows)
                end = at + len(rows)
                self.occupied[at:end] = torch.from_numpy(occupied.view(np.int64)).to(device)
                self.codes[at:end] = torch.from_numpy(codes).to(device)
                for name in ("stm", "score", "result"):
                    column = torch.from_numpy(np.ascontiguousarray(rows[name]))
                    getattr(self, name)[at:end] = column.to(device)
                at = end
        self.count = count
        self.squares = torch.arange(64, device=device)[None, :]
        self.slots = torch.arange(32, device=device)[None, :]

    def features(self, index):
        """reference.feature_indices, on the device, with the pieces in square
        order, and each position's output bucket (reference.bucket)."""
        bits = (self.occupied[index][:, None] >> self.squares) & 1
        # occupied squares first, each group in ascending order
        squares = torch.argsort(1 - bits, dim=1, stable=True)[:, :32]
        count = bits.sum(dim=1)
        live = self.slots < count[:, None]
        bucket = torch.clamp((count - 2) // 4, 0, BUCKETS - 1)
        codes = self.codes[index]
        pieces = torch.stack([codes & 15, codes >> 4], dim=2).reshape(-1, 32).long()
        white = pieces * 64 + squares
        black = ((pieces + 6) % 12) * 64 + (squares ^ 56)
        black_to_move = (self.stm[index] == 1)[:, None]
        us = torch.where(black_to_move, black, white)
        them = torch.where(black_to_move, white, black)
        pad = torch.full_like(us, INPUTS)
        return torch.where(live, us, pad), torch.where(live, them, pad), bucket

    def targets(self, index):
        """The number the network is asked to produce, as a win probability."""
        from_search = torch.sigmoid(self.score[index].float() / SCALE)
        result = self.result[index].float() / 2.0
        return LAMBDA * from_search + (1.0 - LAMBDA) * result

    def batches(self, order, size):
        for at in range(0, len(order) - size + 1, size):
            index = torch.from_numpy(np.sort(order[at:at + size])).to(self.device)
            us, them, bucket = self.features(index)
            yield us, them, bucket, self.targets(index)


def pack(rows):
    """Records to (occupied board as uint64, 16 bytes of 4-bit piece codes in square order)."""
    count = rows["count"].astype(np.int64)
    live = np.arange(32)[None, :] < count[:, None]
    squares = np.where(live, rows["squares"], 64).astype(np.int16)
    order = np.argsort(squares, axis=1, kind="stable")
    pieces = np.take_along_axis(rows["pieces"], order, axis=1)
    pieces = np.where(live, pieces, 0).astype(np.uint8)
    codes = pieces[:, 0::2] | (pieces[:, 1::2] << 4)
    bits = np.left_shift(np.uint64(1), np.minimum(squares, 63).astype(np.uint64))
    occupied = np.bitwise_or.reduce(np.where(live, bits, np.uint64(0)), axis=1)
    return occupied.astype(np.uint64), np.ascontiguousarray(codes)


def open_sources(specs):
    """`path` or `path@N` (the first N records) for each corpus."""
    sources = []
    for spec in specs:
        path, take = spec, ""
        if "@" in os.path.basename(spec):
            path, take = spec.rsplit("@", 1)
        data = np.memmap(path, dtype=RECORD, mode="r")
        take = int(take) if take else len(data)
        if take > len(data):
            raise SystemExit("{} holds {:,} records, not {:,}".format(path, len(data), take))
        sources.append((data, take))
    return sources


def export(model, path):
    """Quantize and write, refusing anything that would not survive int16."""
    with torch.no_grad():
        fw = model.features.weight[:INPUTS].cpu().numpy() * QA
        fb = (model.feature_bias.cpu().numpy()) * QA
        ow = model.out.weight.cpu().numpy() * QB
        ob = model.out.bias.cpu().numpy().astype(np.float64) * QA * QB

    fw, fb, ow, ob = np.rint(fw), np.rint(fb), np.rint(ow), np.rint(ob)
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
                   ow.astype(np.int16), [int(b) for b in ob])
    return worst


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data", nargs="+", help="corpora, each PATH or PATH@N for its first N records")
    parser.add_argument("--out", default="machete.nnue")
    parser.add_argument("--hidden", type=int, default=reference.HIDDEN,
                        help="hidden width; the engine must be built with the same")
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
    sources = open_sources(args.data)
    total = sum(take for _, take in sources)
    print("{:,} positions ({:.2f} GB packed), training on {}".format(
        total, total * Corpus.BYTES / 1e9, device))
    if total < args.validation * 4:
        raise SystemExit("not enough positions to hold out a validation set")

    rng = np.random.RandomState(args.seed)
    order = rng.permutation(total)
    held_out, training = order[:args.validation], order[args.validation:]

    partial = args.out + ".partial"
    corpus = Corpus(sources, device)
    model = Net(args.hidden).to(device)
    optimiser = torch.optim.Adam(model.parameters(), lr=args.lr)
    schedule = torch.optim.lr_scheduler.StepLR(optimiser, step_size=1, gamma=0.8)
    loss_of = nn.MSELoss()

    for epoch in range(args.epochs):
        model.train()
        rng.shuffle(training)
        # the loss stays on the device and is read back every 100 steps;
        # reading it every step made the CPU wait on the GPU each batch
        started, seen, running = time.time(), 0, torch.zeros((), device=device)
        for us, them, bucket, target in corpus.batches(training, args.batch):
            predicted = torch.sigmoid(model(us, them, bucket))
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
            for us, them, bucket, target in corpus.batches(held_out, args.batch):
                predicted = torch.sigmoid(model(us, them, bucket))
                error += float(((predicted - target) ** 2).sum())
                count += len(target)
        print("\repoch {} done: training loss {:.5f}, validation {:.5f}      ".format(
            epoch + 1, float(running) / max(1, seen), error / max(1, count)))
        # every epoch goes to a .partial file and only the last is renamed to
        # --out, so a job that --requires the network never starts on a
        # network still training
        worst = export(model, partial)
        print("  wrote {} (worst accumulator {:.0f} of 32767)".format(partial, worst))
    os.replace(partial, args.out)
    print("finished: {}".format(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
