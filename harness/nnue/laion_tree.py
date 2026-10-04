"""A repertoire tree for one side, chosen by results over the LAION games.

    python harness/nnue/laion_tree.py E:/chess-data/laion-chess --side black --root "e4 c5"
        --force "e4 c5 Nf3 Nc6:Nc6" ... [--files 40] [--depth 16] [--min 20000] [--share 0.05]
        [--system kalashnikov] [--out lines.txt]

Counts results by move prefix (UCI strings, so in bulk with pyarrow) over the
games that begin with --root, then walks the tree: at the repertoire side's
turns it takes the one move with the best score for that side among moves
with --min games; at the opponent's turns it follows every move played in
--share or more of the games. --force "PREFIX:MOVE" fixes our move after a
given prefix (the system's defining moves, such as 2...Nc6 and 4...e5 for
the Kalashnikov), whatever the counts say. Prints each leaf line in
repertoire.txt form with its games and score.

--minimax prints, instead, what each --system-root is worth under best play
by both sides: at our turns the best of our moves, at the opponent's the best
of theirs (each among moves with --min games), down to --depth. An average
over all games rewards a system where the opponent often goes wrong; LAION's
openings are partly random, so the Kalashnikov averaged 51.5% for Black while
its main line, 6.N1c3 a6 7.Na3 b5 8.Nd5, scored 31.7%.
"""
import argparse
import collections
import glob
import os
import sys

import chess
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


def san_to_uci(text):
    b = chess.Board()
    out = []
    for san in text.split():
        m = b.parse_san(san)
        out.append(m.uci())
        b.push(m)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data")
    parser.add_argument("--side", choices=("white", "black"), required=True)
    parser.add_argument("--root", required=True, help="SAN moves every line starts with")
    parser.add_argument("--force", action="append", default=[], help="'SAN prefix:SAN move' fixes our move there")
    parser.add_argument("--files", type=int, default=40)
    parser.add_argument("--depth", type=int, default=16)
    parser.add_argument("--min", type=int, default=20000)
    parser.add_argument("--share", type=float, default=0.05)
    parser.add_argument("--system", default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--minimax", action="store_true")
    parser.add_argument("--system-root", action="append", default=[],
                        help="NAME=SAN moves: a system to value by minimax (with --minimax)")
    args = parser.parse_args()

    root = san_to_uci(args.root)
    forced = {}
    for f in args.force:
        prefix, move = f.rsplit(":", 1)
        p = san_to_uci(prefix)
        b = chess.Board()
        for u in p:
            b.push(chess.Move.from_uci(u))
        forced[" ".join(p)] = b.parse_san(move).uci()
    me = 0 if args.side == "white" else 1  # our moves are at even plies for white

    counts = collections.defaultdict(lambda: [0, 0, 0])  # prefix -> [black won, draw, white won]
    root_s = " ".join(root)
    for path in sorted(glob.glob(os.path.join(args.data, "*.parquet")))[:args.files]:
        t = pq.read_table(path, columns=["Moves", "Result"])
        moves = t.column("Moves").combine_chunks()
        start = pc.binary_join(pc.list_slice(moves, 0, len(root)), " ")
        keep = pc.equal(start, root_s)
        moves = moves.filter(keep)
        result = pc.if_else(pc.equal(t.column("Result").filter(keep), "1-0"), 2,
                            pc.if_else(pc.equal(t.column("Result").filter(keep), "0-1"), 0, 1))
        for k in range(len(root), args.depth + 1):
            key = pc.binary_join(pc.list_slice(moves, 0, k), " ")
            # one string per (prefix, result)
            tagged = pc.binary_join_element_wise(key, pc.cast(result, pa.string()), "|")
            vc = tagged.value_counts()
            for v, c in zip(vc.field(0).to_pylist(), vc.field(1).to_pylist()):
                if v is None:
                    continue
                prefix, r = v.rsplit("|", 1)
                if len(prefix.split()) == k:
                    counts[prefix][int(r)] += c
        print("%s: %d prefixes" % (os.path.basename(path), len(counts)), file=sys.stderr, flush=True)

    children = collections.defaultdict(list)
    for prefix in counts:
        parts = prefix.split()
        if len(parts) > len(root):
            children[" ".join(parts[:-1])].append(parts[-1])

    def score(prefix):
        b, d, w = counts[prefix]
        n = b + d + w
        mine = (w if me == 0 else b) + d / 2.0
        return n, (100.0 * mine / n if n else 0.0)

    lines = []

    def walk(prefix):
        parts = prefix.split()
        ply = len(parts)
        kids = [prefix + " " + m for m in children.get(prefix, []) if score(prefix + " " + m)[0] >= args.min]
        if ply >= args.depth or not kids:
            lines.append(prefix)
            return
        if ply % 2 == me:  # our move
            if prefix in forced:
                pick = prefix + " " + forced[prefix]
                if counts.get(pick) is None or score(pick)[0] < args.min:
                    lines.append(prefix)
                    return
            else:
                # our move: the best under best play by both sides, not the
                # best average (see --minimax)
                pick = max(kids, key=lambda k: value(k, [])[0])
            walk(pick)
        else:
            total = score(prefix)[0]
            followed = [k for k in kids if score(k)[0] >= args.share * total]
            if not followed:
                lines.append(prefix)
                return
            for k in sorted(followed, key=lambda k: -score(k)[0]):
                walk(k)

    memo = {}

    def value(prefix, path):
        # the value depends only on the prefix: work each one out once
        if prefix not in memo:
            memo[prefix] = value_of(prefix)
        v, leaf = memo[prefix]
        return v, path + [leaf]

    def value_of(prefix):
        path = []
        kids = [prefix + " " + m for m in children.get(prefix, []) if score(prefix + " " + m)[0] >= args.min]
        if len(prefix.split()) >= args.depth or not kids:
            return score(prefix)[1], prefix
        ours = len(prefix.split()) % 2 == me
        if ours and prefix in forced:
            pick = prefix + " " + forced[prefix]
            if counts.get(pick) is None or score(pick)[0] < args.min:
                return score(prefix)[1], prefix
            v, p = value(pick, path)
            return v, p[-1]
        vals = [value(k, path) for k in kids]
        v, p = max(vals) if ours else min(vals)
        return v, p[-1]

    if args.minimax:
        print("%-14s %12s %8s %9s   %s" % ("system", "games", "average", "minimax", "the line both sides' best moves lead to"))
        for spec in args.system_root:
            name, moves = spec.split("=", 1)
            start = " ".join(san_to_uci(moves))
            if start not in counts:
                print("%-14s not reached" % name)
                continue
            v, path = value(start, [])
            end = path[-1]
            b = chess.Board()
            sans = []
            for u in end.split():
                m = chess.Move.from_uci(u)
                sans.append(b.san(m))
                b.push(m)
            print("%-14s %12s %7.1f%% %8.1f%%   %s" % (name, format(score(start)[0], ","), score(start)[1], v, " ".join(sans)))
        return 0

    walk(root_s)
    out = []
    for prefix in lines:
        b = chess.Board()
        tokens = []
        for i, u in enumerate(prefix.split()):
            m = chess.Move.from_uci(u)
            san = b.san(m)
            tokens.append(("%d.%s" % (i // 2 + 1, san)) if i % 2 == 0 else san)
            b.push(m)
        n, s = score(prefix)
        out.append("%s %s: %s   # %s games, %s scores %.1f%%" % (args.side, args.system or "line", " ".join(tokens), format(n, ","), args.side, s))
    print("\n".join(out))
    if args.out:
        open(args.out, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
