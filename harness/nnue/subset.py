"""Cut named subsets out of a training corpus, so they can be raced on a board.

    python harness/nnue/subset.py data/train2_noseer.bin --size 8000000 --out E:/machete/subsets

We have no reliable way to tell, from a position alone, whether training on it
will make the engine stronger. Loss on a held-out slice does not answer it: a
corpus predicts its own held-out slice well by construction, so every subset
looks good on its own validation set and the comparison is circular. The only
measurement that is not circular is a game.

So this cuts the corpus along the axes we actually suspect matter, holds the
size of every cut equal, and hands them to `harness/tournament.py`, which trains
one network per cut and plays them against each other. Equal size is the point:
a subset that wins because it is larger tells us nothing we did not already
know from the corpus-growth experiments.

The cuts, and the question each one asks:

  uniform   the whole corpus, sampled at random. The control. Every other cut
            has to beat this to have found anything.
  balanced  |score| <= 150. Positions whose game is still open. The claim being
            tested is that a network learns evaluation from close positions and
            only learns "this is winning" from lopsided ones.
  decided   |score| >= 400. The opposite claim: that the network needs to see
            large advantages to calibrate its output range at all.
  endgame   12 pieces or fewer. Few pieces, long horizons - where a static
            evaluation has the most to say and search the least.
  opening   25 pieces or more. The other end.
  solo      one teacher (Stockfish) only. Half of the teacher-diversity
            question, which has never been isolated: five teachers and book
            openings were changed together in the +157 Elo bundle.
  spread    an equal share from each of the five teachers. The other half. If
            `spread` beats `solo` the diversity was worth something; if `solo`
            wins, the weaker teachers were diluting the corpus.

Every cut is drawn without replacement from the positions that match, with a
fixed seed, so the run reproduces. A cut that cannot supply the requested size
is reported and skipped rather than quietly delivered short, because a short
subset would confound the very comparison the tournament is for.
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reference import RECORD

CHUNK = 1 << 20


def masks(data):
    """Every cut's membership mask, built in one pass over the fields."""
    score = np.abs(data["score"].astype(np.int32))
    count = data["count"]
    engine = data["engine"]
    return [
        ("uniform",  np.ones(len(data), dtype=bool)),
        ("balanced", score <= 150),
        ("decided",  score >= 400),
        ("endgame",  count <= 12),
        ("opening",  count >= 25),
        ("solo",     engine == 0),
    ], engine


def pick(rng, mask, size):
    """`size` indices drawn without replacement from where `mask` is true."""
    available = np.flatnonzero(mask)
    if len(available) < size:
        return None
    return np.sort(rng.choice(available, size=size, replace=False))


def pick_spread(rng, engine, size):
    """An equal share from each teacher, so no teacher's taste dominates."""
    teachers = np.unique(engine)
    share = size // len(teachers)
    parts = []
    for teacher in teachers:
        chosen = pick(rng, engine == teacher, share)
        if chosen is None:
            return None
        parts.append(chosen)
    return np.sort(np.concatenate(parts))


def write(data, indices, path):
    with open(path, "wb") as handle:
        for start in range(0, len(indices), CHUNK):
            handle.write(data[indices[start:start + CHUNK]].tobytes())
    return len(indices)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus")
    parser.add_argument("--size", type=int, default=8000000)
    parser.add_argument("--out", default="data/subsets")
    parser.add_argument("--seed", type=int, default=4242)
    parser.add_argument("--only", default="", help="comma-separated cut names")
    args = parser.parse_args()

    data = np.memmap(args.corpus, dtype=RECORD, mode="r")
    print("{:,} positions in {}".format(len(data), args.corpus))
    if not os.path.isdir(args.out):
        os.makedirs(args.out)

    wanted = set(n.strip() for n in args.only.split(",") if n.strip())
    named, engine = masks(data)
    named.append(("spread", None))          # built per teacher, not by mask
    rng = np.random.RandomState(args.seed)

    written = []
    for name, mask in named:
        if wanted and name not in wanted:
            continue
        path = os.path.join(args.out, "{}.bin".format(name))
        if os.path.exists(path) and os.path.getsize(path) == args.size * RECORD.itemsize:
            print("{:<10} already written".format(name))
            written.append((name, path))
            continue
        indices = (pick_spread(rng, engine, args.size) if mask is None
                   else pick(rng, mask, args.size))
        if indices is None:
            print("{:<10} SKIPPED: fewer than {:,} positions match".format(name, args.size))
            continue
        pool = len(data) if mask is None else int(mask.sum())
        print("{:<10} {:,} drawn from {:,} matching -> {}".format(
            name, write(data, indices, path), pool, path))
        written.append((name, path))

    print("\n{} cuts of {:,} positions each".format(len(written), args.size))
    for name, path in written:
        print("  {:<10} {}".format(name, path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
