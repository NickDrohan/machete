"""Favorite squares: where each piece stands when its side goes on to do well.

    python harness/rl/heatmap.py corpus --out E:/machete/rl-classical/heat_mature.json
        [--corpus E:/machete/corpora/s60_control.bin] [--sample 12000000]
    python harness/rl/heatmap.py league --dir E:/machete/rl-classical      # -> heat_league.json
    python harness/rl/heatmap.py page   --dir E:/machete/rl-classical      # -> heatmap.html

The owner's heat map (turn, tile, piece, outcome), as a measurement. For every
piece kind, square and phase of the game it holds two numbers: how often a
piece of that kind stands there (share), and how its side went on to do from
positions where it did, less the average for that piece in that phase (edge).
Outcome is the game's result for the piece's side, in points. Only positions
the label calls roughly level (within LEVEL centipawns) are counted: over all
positions the maps mostly show where the pieces of a side that is already
winning end up (a knight on the eighth rank), which is no guide to anything.
Black's pieces
are mirrored, so a map reads from its owner's side of the board (a1 at the
bottom left is the owner's queen's rook corner).

Phases are by men on the board: opening 26 or more, middlegame 14 to 25,
endgame 13 or fewer. The league's games also carry the move number, which the
corpus records do not.

`corpus` reads mature play (ordinary Stockfish-labelled games); `league` reads
the positions our own network reached (labels.jsonl with games.jsonl for the
results). `page` draws both and the difference: squares our network uses more
than mature play does, and does worse from. Nothing here changes how the
engine plays; schemas.py scores "move to the favorite square" as one schema
among others.
"""
import argparse
import glob
import json
import os
import sys

import chess
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "nnue"))
from reference import RECORD  # noqa: E402

KINDS = "PNBRQK"
PHASES = ("opening", "middlegame", "endgame")
LEVEL = 100       # centipawns: a position further from level than this is left out
MIN_COUNT = 400  # a square seen less often than this has no edge worth the name


def phase_of(men):
    return 0 if men >= 26 else 1 if men >= 14 else 2


def finish(count, points):
    """count, points: [phase][kind][square] -> the map as lists, with share and edge."""
    out = {}
    for p, phase in enumerate(PHASES):
        out[phase] = {}
        for k, kind in enumerate(KINDS):
            c, s = count[p, k], points[p, k]
            mean = s.sum() / max(1.0, c.sum())
            edge = np.where(c >= MIN_COUNT, s / np.maximum(c, 1) - mean, 0.0)
            out[phase][kind] = dict(share=(c / max(1.0, c.sum())).round(5).tolist(), edge=edge.round(4).tolist(),
                                    count=c.astype(int).tolist(), mean=round(float(mean), 4))
    return out


def corpus(args):
    data = np.memmap(args.corpus, dtype=RECORD, mode="r")
    rng = np.random.RandomState(1)
    count = np.zeros((3, 6, 64))
    points = np.zeros((3, 6, 64))
    step = 500000
    starts = sorted(rng.choice(max(1, len(data) - step), size=max(1, args.sample // step), replace=False))
    for start in starts:
        rows = np.array(data[start:start + step])
        rows = rows[np.abs(rows["score"].astype(int)) <= LEVEL]
        men = rows["count"].astype(int)
        phase = np.where(men >= 26, 0, np.where(men >= 14, 1, 2))
        on = np.arange(32)[None, :] < men[:, None]
        code = rows["pieces"].astype(int)
        white = code < 6
        kind = code % 6
        square = rows["squares"].astype(int)
        square = np.where(white, square, square ^ 56)
        # the result is from the side to move: 0 lost, 1 drew, 2 won
        mover_white = (rows["stm"] == 0)[:, None]
        mine = rows["result"].astype(float)[:, None] / 2
        got = np.where(white == mover_white, mine, 1 - mine)
        index = (phase[:, None] * 6 + kind) * 64 + square
        count += np.bincount(index[on], minlength=3 * 6 * 64).reshape(3, 6, 64)
        points += np.bincount(index[on], weights=got[on], minlength=3 * 6 * 64).reshape(3, 6, 64)
    out = dict(source=args.corpus, positions=int(count[:, 5].sum() // 2), maps=finish(count, points))
    json.dump(out, open(args.out, "w"))
    print("%d positions of %s -> %s" % (out["positions"], args.corpus, args.out))


def league(args):
    results = {}
    for path in glob.glob(os.path.join(args.dir, "gen-*", "games.jsonl")):
        gen = os.path.basename(os.path.dirname(path))
        for line in open(path, encoding="utf-8"):
            g = json.loads(line)
            results[(gen, g["game"])] = g["result"]
    count = np.zeros((3, 6, 64))
    points = np.zeros((3, 6, 64))
    n = 0
    for line in open(os.path.join(args.dir, "labels.jsonl"), encoding="utf-8"):
        row = json.loads(line)
        result = results.get((row["gen"], row["game"]))
        if result is None or row["cp"] is None or abs(row["cp"]) > LEVEL:
            continue
        white_points = 1.0 if result == "1-0" else 0.0 if result == "0-1" else 0.5
        board = chess.Board(row["fen"])
        p = phase_of(chess.popcount(board.occupied))
        for square, piece in board.piece_map().items():
            k = piece.piece_type - 1
            sq = square if piece.color else square ^ 56
            count[p, k, sq] += 1
            points[p, k, sq] += white_points if piece.color else 1 - white_points
        n += 1
    out = dict(source=args.dir, positions=n, maps=finish(count, points))
    path = os.path.join(args.dir, "heat_league.json")
    json.dump(out, open(path, "w"))
    print("%d league positions -> %s" % (n, path))


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Favorite Squares</title><style>
:root{--bg:#f6f5f1;--ink:#1d1d1b;--mute:#6a6a63;--line:#d9d6cc;--card:#fff}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#17181a;--ink:#ecebe6;--mute:#9a9a92;--line:#33353a;--card:#1f2124}}
:root[data-theme="dark"]{--bg:#17181a;--ink:#ecebe6;--mute:#9a9a92;--line:#33353a;--card:#1f2124}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 60px}
h1{font-size:26px;margin:0 0 6px}h2{font-size:18px;margin:34px 0 4px}p{color:var(--mute);margin:4px 0 14px;max-width:70ch}
.row{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px}
.card b{display:block;font-size:13px;margin-bottom:6px}
.board{display:grid;grid-template-columns:repeat(8,1fr);aspect-ratio:1;border:1px solid var(--line)}
.board i{display:block}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}
.tabs button{font:inherit;padding:6px 12px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
.tabs button[aria-pressed="true"]{background:var(--ink);color:var(--bg)}
.key{font-size:13px;color:var(--mute)}
</style></head><body><main>
<h1>Favorite squares</h1>
<p>Each board is one piece in one phase, seen from its owner's side (the owner's back rank is at the bottom).
Green squares are where that piece stands when its side goes on to score above its average; red, below.
Stronger colour is a bigger edge. Squares seen too rarely are left blank.</p>
<div class="tabs" id="tabs"></div><p class="key" id="note"></p><div id="out"></div>
<script>
const DATA = __DATA__;
const KINDS = {P:"Pawn",N:"Knight",B:"Bishop",R:"Rook",Q:"Queen",K:"King"};
const VIEWS = [["mature","Mature play"],["league","Our network"],["diff","Difference"]];
let view = "mature";
function colour(v, scale){ const a = Math.min(1, Math.abs(v)/scale); return v>0 ? `rgba(34,150,83,${a})` : `rgba(204,62,54,${a})`; }
function board(values, scale){
  let h = '<div class="board">';
  for (let r=7;r>=0;r--) for (let f=0;f<8;f++){ const v = values[r*8+f]; h += `<i title="${"abcdefgh"[f]}${r+1}: ${v>0?"+":""}${(100*v).toFixed(1)}" style="background:${v===0?"transparent":colour(v,scale)}"></i>`; }
  return h + "</div>";
}
function draw(){
  const out = document.getElementById("out"); let h = "";
  const notes = {mature:`Mature play: ${DATA.mature.positions.toLocaleString()} positions from ordinary Stockfish-labelled games, roughly level ones only. Colour is points above the piece's average (full colour at 2 points in 100).`,
    league:`Our network: ${DATA.league ? DATA.league.positions.toLocaleString() : 0} positions from the Pis' games. Same scale.`,
    diff:"Difference: how much more often our network has the piece on a square than mature play does (red = more often, green = less), full colour at 3 points of share."};
  document.getElementById("note").textContent = notes[view];
  for (const phase of ["opening","middlegame","endgame"]){
    h += `<h2>${phase[0].toUpperCase()+phase.slice(1)}</h2><div class="row">`;
    for (const k of "PNBRQK"){
      let values, scale = 0.02;
      if (view === "diff"){ if(!DATA.league) continue; const a = DATA.league.maps[phase][k].share, b = DATA.mature.maps[phase][k].share; values = a.map((x,i)=>-(x-b[i])); scale = 0.03; }
      else { const src = DATA[view]; if(!src) continue; values = src.maps[phase][k].edge; }
      h += `<div class="card"><b>${KINDS[k]}</b>${board(values, scale)}</div>`;
    }
    h += "</div>";
  }
  out.innerHTML = h;
}
const tabs = document.getElementById("tabs");
for (const [id,label] of VIEWS){ const b = document.createElement("button"); b.textContent = label; b.setAttribute("aria-pressed", id===view); b.onclick = () => { view = id; for (const x of tabs.children) x.setAttribute("aria-pressed", x===b); draw(); }; tabs.appendChild(b); }
draw();
</script></main></body></html>
"""


def page(args):
    data = dict(mature=json.load(open(os.path.join(args.dir, "heat_mature.json"))), league=None)
    path = os.path.join(args.dir, "heat_league.json")
    if os.path.exists(path):
        data["league"] = json.load(open(path))
    for source in data.values():
        if source:
            for phase in source["maps"].values():
                for m in phase.values():
                    m.pop("count", None)
    out = os.path.join(args.dir, "heatmap.html")
    open(out, "w", encoding="utf-8").write(PAGE.replace("__DATA__", json.dumps(data)))
    print(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["corpus", "league", "page"])
    parser.add_argument("--dir", default="E:/machete/rl-classical")
    parser.add_argument("--out", default="")
    parser.add_argument("--corpus", default="E:/machete/corpora/s60_control.bin")
    parser.add_argument("--sample", type=int, default=30000000)
    args = parser.parse_args()
    if args.command == "corpus":
        args.out = args.out or os.path.join(args.dir, "heat_mature.json")
        corpus(args)
    elif args.command == "league":
        league(args)
    else:
        page(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
