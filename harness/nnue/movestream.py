"""Training positions as games: Stockfish's binpack format for machete's own data (the owner, 2026-11-25).

    py -3.13 harness/nnue/movestream.py roundtrip              self-test: encode random games, decode, compare
    py -3.13 harness/nnue/movestream.py botcorpus OUT.binpack  the bot-vs-bot corpus as move streams, checked
    py -3.13 harness/nnue/movestream.py expand IN.binpack OUT.bin   the labelled positions as 70-byte records

A position on disk has been a 70-byte record (28 bytes once the trainer packs it): every piece and its square.
But training positions come from games, and a game is its first position and then its moves. binpack (Tomasz
Sobczyk's format for Stockfish's training data, MIT; machete already reads it in src/binpack.mach and
harness/nnue/leela.py) stores exactly that: a 32-byte stem for a game's first position, then each move as an index
among the moving side's pieces and then among that piece's destinations - a few bits, never more than the choice
needs - and each position's score as a variable-length difference from the last one.

This module is the writer, the inverse of leela.py's reader. A position with no label is written with Stockfish's
VALUE_NONE (32002) as its score, as nnue-pytorch writes skipped positions, and the reader here leaves it out, so a
game sampled every third ply costs the moves in between and nothing else. A labelled position with no legal move (a
stalemate that ends a game) cannot be a binpack entry, which is a position and the move played from it: those few go
to a sidecar of ordinary records, FILE.rest.bin, which `expand` reads too. Scores are our centipawns as they are, not
Stockfish's internal units: these files are read with `expand` (or `binpack convert --cp`), never through Leela's
scale.
"""
import argparse
import glob
import json
import os
import random
import sys

import chess
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reference import RECORD  # noqa: E402
import leela  # noqa: E402

VALUE_NONE = 32002
CHUNK_BYTES = 1 << 20


def signed_to_unsigned(x):
    """The inverse of leela.unsigned_to_signed: binpack's zig-zag-like 16-bit code."""
    u = x & 0xFFFF
    if u & 0x8000:
        u ^= 0x7FFF
    return ((u << 1) | (u >> 15)) & 0xFFFF


class BitWriter(object):
    """binpack.h's PackedMoveScoreList writer: bits fill each byte from the top."""

    def __init__(self):
        self.out = bytearray()
        self.free = 0

    def put(self, value, count):
        for i in range(count - 1, -1, -1):
            if self.free == 0:
                self.out.append(0)
                self.free = 8
            self.free -= 1
            if (value >> i) & 1:
                self.out[-1] |= 1 << self.free

    def vle16(self, value, block=4):
        mask = (1 << block) - 1
        while True:
            part = value & mask
            value >>= block
            if value:
                part |= 1 << block
            self.put(part, block + 1)
            if not value:
                return


def index_below(bits, square):
    return bin(bits & ((1 << square) - 1)).count("1")


def stem(board, move, score, result):
    """32 bytes: the position, its move, score, ply, result and fifty-move counter (leela.read_stem's inverse)."""
    out = bytearray(32)
    occupied = board.occupied
    out[0:8] = occupied.to_bytes(8, "big")
    ep_pawn = None
    if board.ep_square is not None:
        ep_pawn = board.ep_square + (8 if board.turn == chess.BLACK else -8)
    index, squares = 0, occupied
    while squares:
        square = (squares & -squares).bit_length() - 1
        squares &= squares - 1
        piece = board.piece_at(square)
        nibble = (piece.piece_type - 1) << 1 | (0 if piece.color == chess.WHITE else 1)
        if piece.piece_type == chess.PAWN and square == ep_pawn:
            nibble = 12
        elif piece.piece_type == chess.ROOK and board.castling_rights & chess.BB_SQUARES[square]:
            nibble = 13 if piece.color == chess.WHITE else 14
        elif piece.piece_type == chess.KING and piece.color == chess.BLACK and board.turn == chess.BLACK:
            nibble = 15
        out[8 + index // 2] |= nibble << (4 * (index % 2))
        index += 1
    if move.promotion:
        packed = 1 << 14 | move.from_square << 8 | move.to_square << 2 | (move.promotion - chess.KNIGHT)
    elif board.is_castling(move):
        rook = chess.square(7 if chess.square_file(move.to_square) == 6 else 0, chess.square_rank(move.from_square))
        packed = 2 << 14 | move.from_square << 8 | rook << 2
    elif board.is_en_passant(move):
        packed = 3 << 14 | move.from_square << 8 | move.to_square << 2
    else:
        packed = move.from_square << 8 | move.to_square << 2
    out[24:26] = packed.to_bytes(2, "big")
    out[26:28] = signed_to_unsigned(score).to_bytes(2, "big")
    ply = (board.fullmove_number - 1) * 2 + (1 if board.turn == chess.BLACK else 0)
    out[28:30] = (signed_to_unsigned(result) << 14 | (ply & 0x3FFF)).to_bytes(2, "big")
    out[30:32] = min(board.halfmove_clock, 0xFFFF).to_bytes(2, "big")
    return bytes(out)


def write_move(board, move, bits):
    """leela.next_move's inverse: the moving piece among ours, then the destination among its."""
    us = board.turn
    ours = board.occupied_co[us]
    theirs = board.occupied_co[not us]
    occupied = ours | theirs
    source = move.from_square
    bits.put(index_below(ours, source), leela.used_bits_safe(bin(ours).count("1")))
    kind = board.piece_type_at(source)
    if kind == chess.PAWN:
        forward = 8 if us == chess.WHITE else -8
        targets = theirs
        if board.ep_square is not None and board.has_legal_en_passant():
            targets |= chess.BB_SQUARES[board.ep_square]
        destinations = chess.BB_PAWN_ATTACKS[us][source] & targets
        ahead = source + forward
        if not occupied & chess.BB_SQUARES[ahead]:
            destinations |= chess.BB_SQUARES[ahead]
            if chess.square_rank(source) == (1 if us == chess.WHITE else 6) \
                    and not occupied & chess.BB_SQUARES[ahead + forward]:
                destinations |= chess.BB_SQUARES[ahead + forward]
        count = bin(destinations).count("1")
        at = index_below(destinations, move.to_square)
        if chess.square_rank(source) == (6 if us == chess.WHITE else 1):
            bits.put(at * 4 + (move.promotion - chess.KNIGHT), leela.used_bits_safe(count * 4))
        else:
            bits.put(at, leela.used_bits_safe(count))
        return
    if kind == chess.KING:
        rights = board.castling_rights & (chess.BB_RANK_1 if us == chess.WHITE else chess.BB_RANK_8)
        attacks = chess.BB_KING_ATTACKS[source] & ~ours
        size = bin(attacks).count("1")
        width = leela.used_bits_safe(size + bin(rights).count("1"))
        if board.is_castling(move):
            long_side = chess.square_file(move.to_square) == 2
            has_long = bool(rights & (chess.BB_A1 | chess.BB_A8))
            bits.put(size if long_side else size + (1 if has_long else 0), width)
        else:
            bits.put(index_below(attacks, move.to_square), width)
        return
    attacks = board.attacks_mask(source) & ~ours
    bits.put(index_below(attacks, move.to_square), leela.used_bits_safe(bin(attacks).count("1")))


def encode_game(board, moves, scores, results):
    """One game from `board`: moves[i] is played from the i-th position, scored scores[i] (None for no label), with
    results[i] (+1, 0, -1 from the side to move). Returns the stem, the ply count and the packed move text."""
    board = board.copy()
    score0 = VALUE_NONE if scores[0] is None else scores[0]
    head = stem(board, moves[0], score0, results[0])
    bits = BitWriter()
    last = leela.int16(-score0)
    board.push(moves[0])
    for i in range(1, len(moves)):
        write_move(board, moves[i], bits)
        score = VALUE_NONE if scores[i] is None else scores[i]
        bits.vle16(signed_to_unsigned(leela.int16(score - last)))
        last = leela.int16(-score)
        board.push(moves[i])
    return head + (len(moves) - 1).to_bytes(2, "big") + bytes(bits.out)


class Writer(object):
    """Games collected into binpack chunks of about a megabyte."""

    def __init__(self, path):
        self.handle = open(path, "wb")
        self.chunk = bytearray()
        self.games = 0

    def add(self, game):
        if len(self.chunk) + len(game) > CHUNK_BYTES and self.chunk:
            self.flush()
        self.chunk += game
        self.games += 1

    def flush(self):
        if self.chunk:
            self.handle.write(b"BINP" + len(self.chunk).to_bytes(4, "little") + bytes(self.chunk))
            self.chunk = bytearray()

    def close(self):
        self.flush()
        self.handle.close()


def record(board, score, result, engine=0):
    """One 70-byte record, as extract_bots.py and gen.py write it: pieces in square order."""
    row = np.zeros(1, dtype=RECORD)[0]
    row["stm"] = 0 if board.turn == chess.WHITE else 1
    items = sorted(board.piece_map().items())
    row["count"] = len(items)
    for slot, (square, piece) in enumerate(items):
        row["pieces"][slot] = (0 if piece.color == chess.WHITE else 1) * 6 + piece.piece_type - 1
        row["squares"][slot] = square
    row["score"] = score
    row["result"] = result + 1
    row["engine"] = engine
    return row


def expand(path, engine=0):
    """Every labelled position of a move-stream file, as records, then its sidecar's."""
    rows = []
    for chunk in leela.chunks(path):
        for board, _, score, result in leela.games(chunk):
            if score != VALUE_NONE:
                rows.append(record(board, score, result, engine))
    out = np.array(rows, dtype=RECORD)
    if os.path.exists(path + ".rest.bin"):
        out = np.concatenate([out, np.fromfile(path + ".rest.bin", dtype=RECORD)])
    return out


# ------------------------------------------------------------------ commands
def roundtrip(n=300, seed=1):
    """Random legal games with random labels, promotions, castling and en passant included, encoded and read back."""
    rng = random.Random(seed)
    tmp = os.path.join(os.environ.get("TEMP", "/tmp"), "movestream_roundtrip.binpack")
    w = Writer(tmp)
    expect = []
    for _ in range(n):
        board, moves, scores, results = chess.Board(), [], [], []
        white_result = rng.choice((-1, 0, 1))   # binpack keeps one result a game, from each side to move in turn
        for _ in range(rng.randrange(1, 200)):
            legal = list(board.legal_moves)
            if not legal:
                break
            m = rng.choice(legal)
            s = None if rng.random() < 0.6 else rng.randrange(-3000, 3001)
            r = white_result if board.turn == chess.WHITE else -white_result
            if s is not None:
                expect.append(record(board, s, r).tobytes())
            moves.append(m)
            scores.append(s)
            results.append(r)
            board.push(m)
        if moves:
            w.add(encode_game(chess.Board(), moves, scores, results))
    w.close()
    got = [r.tobytes() for r in expand(tmp)]
    ok = got == expect
    print("round trip: %d games, %d labelled positions, %s" % (n, len(expect), "identical" if ok else "DIFFERENT"))
    return 0 if ok else 1


def bot_games():
    """The bot-vs-bot corpus's games, as extract_bots.py kept them: id -> (moves in SAN, winner)."""
    seen, out = set(), {}
    for path in sorted(glob.glob("E:/machete/claude/r3/botgames/games/*.ndjson")):
        for line in open(path, encoding="utf-8"):
            g = json.loads(line)
            if g["id"] in seen or g.get("variant") != "standard" or not g.get("rated"):
                continue
            seen.add(g["id"])
            out[g["id"]] = (g.get("moves", "").split(), g.get("winner"))
    return out


def botcorpus(out_path, labelled="E:/machete/corpora/botcorpus/mid_bot_%03d.bin",
              provenance="E:/machete/claude/r3/botgames/raw0/mid_bot_%03d.json", chunks=12, only=None):
    """The labelled bot corpus as move streams: one chain per game from its first labelled position to its last,
    every other position on the way written without a label. Then read back and compared, record for record."""
    games = bot_games()
    labels = {}                          # game id -> {ply: score}
    originals = []
    for n in (range(chunks) if only is None else [only]):
        prov = json.load(open(provenance % n))
        data = np.fromfile(labelled % n, dtype=RECORD)
        assert len(prov) == len(data)
        originals.append(data)
        for (gid, ply, _res), row in zip(prov, data):
            labels.setdefault(gid, {})[ply] = int(row["score"])
    w = Writer(out_path)
    rest = []
    tails = 0
    for gid, by_ply in labels.items():
        sans, winner = games[gid]
        board, moves = chess.Board(), []
        for san in sans:
            moves.append(board.parse_san(san))
            board.push(moves[-1])
        first, last = min(by_ply), max(by_ply)
        board = chess.Board()
        for m in moves[:first]:
            board.push(m)
        start = board.copy()
        chain, scores, results = [], [], []
        for ply in range(first, last + 1):
            if ply == len(moves):
                break                    # the game's last position has no move: written on its own below
            chain.append(moves[ply])
            scores.append(by_ply.get(ply))
            stm_white = board.turn == chess.WHITE
            results.append(0 if winner is None else (1 if (winner == "white") == stm_white else -1))
            board.push(moves[ply])
        if chain:
            w.add(encode_game(start, chain, scores, results))
        if last == len(moves):
            # a labelled final position: a one-position game whose move is any legal one (it is never played)
            legal = next(iter(board.legal_moves), None)
            stm_white = board.turn == chess.WHITE
            r = 0 if winner is None else (1 if (winner == "white") == stm_white else -1)
            if legal is not None:
                w.add(encode_game(board, [legal], [by_ply[last]], [r]))
                tails += 1
            else:
                rest.append(record(board, by_ply[last], r))
    w.close()
    if rest:
        np.array(rest, dtype=RECORD).tofile(out_path + ".rest.bin")
    size = os.path.getsize(out_path) + (os.path.getsize(out_path + ".rest.bin") if rest else 0)
    original = np.concatenate(originals)
    got = expand(out_path)
    a = np.sort(original.view(np.dtype((np.void, RECORD.itemsize))))
    b = np.sort(got.view(np.dtype((np.void, RECORD.itemsize))))
    same = len(a) == len(b) and bool((a == b).all())
    print("bot corpus: %d games (%d final positions on their own, %d stalemates as records), %d labelled positions"
          % (w.games, tails, len(rest), len(original)))
    print("move streams %.1f MB against %.1f MB of records (%.1fx smaller), %.2f bytes a labelled position"
          % (size / 1e6, original.nbytes / 1e6, original.nbytes / size, size / len(original)))
    print("read back: %d records, %s" % (len(got), "identical to the corpus, as a multiset" if same else "DIFFERENT"))
    return 0 if same else 1


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("roundtrip")
    b = sub.add_parser("botcorpus")
    b.add_argument("out")
    b.add_argument("--chunk", type=int, default=None, help="convert one labelled chunk, NNN of mid_bot_NNN")
    e = sub.add_parser("expand")
    e.add_argument("src")
    e.add_argument("out")
    args = ap.parse_args()
    if args.cmd == "roundtrip":
        return roundtrip()
    if args.cmd == "botcorpus":
        return botcorpus(args.out, only=args.chunk)
    rows = expand(args.src)
    rows.tofile(args.out)
    print("%s: %d records" % (args.out, len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
