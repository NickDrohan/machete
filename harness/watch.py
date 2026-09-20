"""Watch machete play another UCI engine, live, in a browser.

    python harness/watch.py                      # machete vs Stockfish at 1500 Elo
    python harness/watch.py --elo 2200 --movetime 500 --threads 8
    python harness/watch.py --opponent path/to/other-engine.exe

Runs the game in one thread and serves a page from another, so the board
updates as the moves are played. Everything is local: no CDN, no network, one
file, and the page is plain HTML with a polling fetch.

Both engines report what they are thinking, so the page shows each side's
score, depth and node count as the game goes.
"""

import argparse
import glob
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import chess
import chess.engine
import chess.pgn

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MACHETE = os.path.join(HERE, "..", "out", "windows-x86_64", "release", "bin", "machete.exe")

GLYPHS = {
    "K": "\u2654", "Q": "\u2655", "R": "\u2656", "B": "\u2657", "N": "\u2658", "P": "\u2659",
    "k": "\u265a", "q": "\u265b", "r": "\u265c", "b": "\u265d", "n": "\u265e", "p": "\u265f",
}


def find_stockfish():
    pattern = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages",
                           "Stockfish.Stockfish*", "stockfish", "*.exe")
    found = sorted(glob.glob(pattern))
    return found[0] if found else "stockfish"


class Game(object):
    """The shared state the page reads: one lock, one snapshot."""

    def __init__(self, white_name, black_name):
        self.lock = threading.Lock()
        self.board = chess.Board()
        self.white_name = white_name
        self.black_name = black_name
        self.moves = []
        self.info = {"white": {}, "black": {}}
        self.result = None
        self.last_move = None
        self.thinking = "white"
        self.started = time.time()
        self.game_number = 1
        self.tally = {"machete": 0, "opponent": 0, "draw": 0}
        self.machete_is_white = True

    def snapshot(self):
        with self.lock:
            board = self.board
            squares = []
            for rank in range(7, -1, -1):
                for file in range(8):
                    piece = board.piece_at(chess.square(file, rank))
                    squares.append(GLYPHS[piece.symbol()] if piece else "")
            return {
                "squares": squares,
                "fen": board.fen(),
                "moves": self.moves,
                "white": self.white_name,
                "black": self.black_name,
                "info": self.info,
                "result": self.result,
                "lastMove": self.last_move,
                "thinking": self.thinking,
                "check": board.is_check(),
                "elapsed": int(time.time() - self.started),
                "gameNumber": self.game_number,
                "tally": self.tally,
            }


def describe(info):
    """Pull score, depth and nodes out of whatever the engine reported."""
    out = {}
    score = info.get("score")
    if score is not None:
        pov = score.white()
        if pov.is_mate():
            out["score"] = "mate in {}".format(abs(pov.mate()))
            out["cp"] = 10000 if pov.mate() > 0 else -10000
        else:
            out["score"] = "{:+.2f}".format(pov.score() / 100.0)
            out["cp"] = pov.score()
    for key in ("depth", "nodes", "nps", "time"):
        if info.get(key) is not None:
            out[key] = info[key]
    return out


def play_one(game, white, black, movetime, max_plies):
    """Play a single game to its end, updating the shared state as it goes."""
    limit = chess.engine.Limit(time=movetime / 1000.0)
    try:
        while True:
            with game.lock:
                board = game.board.copy()
                if board.is_game_over(claim_draw=True) or board.ply() >= max_plies:
                    game.result = board.result(claim_draw=True) if board.is_game_over(claim_draw=True) else "1/2-1/2"
                    game.thinking = None
                    return
                side = "white" if board.turn == chess.WHITE else "black"
                game.thinking = side
            engine = white if board.turn == chess.WHITE else black
            result = engine.play(board, limit, info=chess.engine.INFO_ALL)
            if result.move is None or result.move not in board.legal_moves:
                with game.lock:
                    game.result = "illegal move from {}".format(side)
                    game.thinking = None
                return
            san = board.san(result.move)
            with game.lock:
                game.info[side] = describe(result.info or {})
                game.board.push(result.move)
                game.last_move = [result.move.from_square, result.move.to_square]
                game.moves.append(san)
    except Exception as problem:  # a crashed engine should show on the page, not just the console
        with game.lock:
            game.result = "stopped: {}".format(problem)
            game.thinking = None


def play_match(game, machete, opponent, movetime, max_plies, games, pause):
    """Play games back to back, swapping colours, so the board is never idle."""
    for number in range(1, games + 1):
        with game.lock:
            game.game_number = number
            game.board = chess.Board()
            game.moves = []
            game.result = None
            game.last_move = None
            game.info = {"white": {}, "black": {}}
            game.started = time.time()
            machete_white = game.machete_is_white
            if machete_white:
                game.white_name, game.black_name = game.machete_name, game.opponent_name
            else:
                game.white_name, game.black_name = game.opponent_name, game.machete_name
            game.thinking = "white"

        white, black = (machete, opponent) if machete_white else (opponent, machete)
        play_one(game, white, black, movetime, max_plies)

        with game.lock:
            outcome = game.result
            if outcome == "1-0":
                winner = "machete" if machete_white else "opponent"
            elif outcome == "0-1":
                winner = "opponent" if machete_white else "machete"
            else:
                winner = "draw"
            if winner in game.tally:
                game.tally[winner] = game.tally[winner] + 1
            game.machete_is_white = not machete_white
            print("game {}: {} ({})".format(number, outcome, winner))
            sys.stdout.flush()
        if number < games:
            time.sleep(pause)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>machete</title>
<style>
  :root {
    --bg: #12141a; --panel: #1b1e26; --line: #2c313d; --text: #e6e9f0;
    --dim: #8a93a6; --light: #b9a789; --dark: #6d5e48; --mark: #c8a33266;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font: 15px/1.5 "Segoe UI", system-ui, sans-serif;
    display: flex; justify-content: center; padding: 24px 16px;
  }
  .wrap { display: flex; gap: 24px; flex-wrap: wrap; justify-content: center; max-width: 1000px; }
  .board { display: grid; grid-template-columns: repeat(8, 64px); grid-template-rows: repeat(8, 64px);
           border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }
  .sq { display: flex; align-items: center; justify-content: center; font-size: 44px; line-height: 1;
        user-select: none; }
  .sq.light { background: var(--light); } .sq.dark { background: var(--dark); }
  .sq.mark { box-shadow: inset 0 0 0 100px var(--mark); }
  .sq span.w { color: #fcfcfa; text-shadow: 0 0 1px #000, 0 0 2px #000, 0 1px 2px rgba(0,0,0,.6); }
  .sq span.b { color: #17181c; text-shadow: 0 0 1px rgba(255,255,255,.5), 0 1px 1px rgba(255,255,255,.25); }
  .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
           padding: 16px; width: 320px; }
  h1 { font-size: 17px; margin: 0 0 4px; letter-spacing: .3px; }
  .sub { color: var(--dim); font-size: 13px; margin-bottom: 14px; }
  .side { display: flex; justify-content: space-between; align-items: baseline;
          padding: 9px 0; border-top: 1px solid var(--line); }
  .side .who { font-weight: 600; }
  .side .who.on::after { content: " thinking"; color: #7fd18a; font-weight: 400; font-size: 12px; }
  .stat { color: var(--dim); font-size: 12px; font-variant-numeric: tabular-nums; }
  .score { font-variant-numeric: tabular-nums; }
  .moves { margin-top: 12px; max-height: 260px; overflow-y: auto; font-size: 13px;
           font-variant-numeric: tabular-nums; line-height: 1.7; }
  .moves b { color: var(--dim); font-weight: 400; margin-right: 6px; }
  .result { margin-top: 12px; padding: 9px 12px; background: #23283a; border-radius: 6px;
            font-size: 14px; }
  .files, .ranks { color: var(--dim); font-size: 11px; }
  .files { display: grid; grid-template-columns: repeat(8, 64px); text-align: center; padding-top: 4px; }
</style>
</head>
<body>
<div class="wrap">
  <div>
    <div class="board" id="board"></div>
    <div class="files"><div>a</div><div>b</div><div>c</div><div>d</div><div>e</div><div>f</div><div>g</div><div>h</div></div>
  </div>
  <div class="panel">
    <h1>machete</h1>
    <div class="sub" id="sub">a chess engine written in Mach</div>
    <div class="side"><span class="who" id="wname">White</span><span class="score" id="wscore">-</span></div>
    <div class="stat" id="wstat"></div>
    <div class="side"><span class="who" id="bname">Black</span><span class="score" id="bscore">-</span></div>
    <div class="stat" id="bstat"></div>
    <div class="result" id="result" style="display:none"></div>
    <div class="moves" id="moves"></div>
  </div>
</div>
<script>
const board = document.getElementById('board');
for (let i = 0; i < 64; i++) {
  const sq = document.createElement('div');
  const rank = Math.floor(i / 8), file = i % 8;
  sq.className = 'sq ' + ((rank + file) % 2 === 0 ? 'light' : 'dark');
  board.appendChild(sq);
}
const cells = [...board.children];

function squareIndex(sq) {           // chess square number -> cell index, white at the bottom
  return (7 - Math.floor(sq / 8)) * 8 + (sq % 8);
}

function stats(info) {
  const bits = [];
  if (info.depth) bits.push('depth ' + info.depth);
  if (info.nodes) bits.push(info.nodes.toLocaleString() + ' nodes');
  if (info.nps) bits.push(Math.round(info.nps / 1000).toLocaleString() + 'k nps');
  return bits.join(' \\u00b7 ');
}

async function tick() {
  let state;
  try { state = await (await fetch('/state')).json(); } catch (e) { return; }
  state.squares.forEach((glyph, i) => {
    const cell = cells[i];
    const black = glyph && '\\u265a\\u265b\\u265c\\u265d\\u265e\\u265f'.includes(glyph);
    cell.innerHTML = glyph ? '<span class="' + (black ? 'b' : 'w') + '">' + glyph + '</span>' : '';
    cell.classList.remove('mark');
  });
  if (state.lastMove) state.lastMove.forEach(sq => cells[squareIndex(sq)].classList.add('mark'));

  document.getElementById('wname').textContent = state.white;
  document.getElementById('bname').textContent = state.black;
  document.getElementById('wname').className = 'who' + (state.thinking === 'white' ? ' on' : '');
  document.getElementById('bname').className = 'who' + (state.thinking === 'black' ? ' on' : '');
  document.getElementById('wscore').textContent = state.info.white.score || '-';
  document.getElementById('bscore').textContent = state.info.black.score || '-';
  document.getElementById('wstat').textContent = stats(state.info.white);
  document.getElementById('bstat').textContent = stats(state.info.black);

  const moves = [];
  for (let i = 0; i < state.moves.length; i += 2) {
    moves.push('<b>' + (i / 2 + 1) + '.</b>' + state.moves[i] + ' ' + (state.moves[i + 1] || ''));
  }
  const list = document.getElementById('moves');
  list.innerHTML = moves.join('<br>');
  list.scrollTop = list.scrollHeight;

  const tally = state.tally;
  document.getElementById('sub').textContent =
    'game ' + state.gameNumber + '  ·  machete ' + tally.machete +
    ' - ' + tally.opponent + ' - ' + tally.draw + ' (W-L-D)';

  const result = document.getElementById('result');
  if (state.result) {
    result.style.display = 'block';
    result.textContent = state.result + '  \\u00b7  ' + state.moves.length + ' plies in ' + state.elapsed + 's';
  } else {
    // a finished game's banner must not linger over the next one
    result.style.display = 'none';
  }
}
tick();
setInterval(tick, 400);
</script>
</body>
</html>
"""


def serve(game, port):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/state"):
                body = json.dumps(game.snapshot()).encode("utf-8")
                content = "application/json"
            else:
                body = PAGE.encode("utf-8")
                content = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", port), Handler)
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--machete", default=DEFAULT_MACHETE)
    parser.add_argument("--opponent", default=None, help="defaults to the installed Stockfish")
    parser.add_argument("--elo", type=int, default=1500,
                        help="limit the opponent to this Elo (Stockfish accepts 1320-3190)")
    parser.add_argument("--movetime", type=int, default=300, help="milliseconds per move")
    parser.add_argument("--threads", type=int, default=1, help="machete search threads")
    parser.add_argument("--machete-black", action="store_true", help="machete plays black")
    parser.add_argument("--max-plies", type=int, default=300)
    parser.add_argument("--port", type=int, default=8730)
    parser.add_argument("--games", type=int, default=20, help="games to play back to back")
    parser.add_argument("--pause", type=float, default=3.0, help="seconds between games")
    args = parser.parse_args()

    opponent_path = args.opponent or find_stockfish()
    machete = chess.engine.SimpleEngine.popen_uci(os.path.abspath(args.machete))
    opponent = chess.engine.SimpleEngine.popen_uci(opponent_path)

    if args.threads > 1:
        machete.configure({"Threads": args.threads})
    opponent_name = opponent.id.get("name", "opponent")
    try:
        opponent.configure({"UCI_LimitStrength": True, "UCI_Elo": args.elo})
        opponent_name += " @ {} Elo".format(args.elo)
    except Exception:
        pass  # an engine without strength limiting just plays its best

    machete_name = "machete" + (" x{}".format(args.threads) if args.threads > 1 else "")
    game = Game(machete_name, opponent_name)
    game.machete_name = machete_name
    game.opponent_name = opponent_name
    game.machete_is_white = not args.machete_black

    threading.Thread(target=serve, args=(game, args.port), daemon=True).start()
    print("watch at http://127.0.0.1:{}".format(args.port))
    print("{} vs {}, {} ms a move, {} game(s)".format(
        machete_name, opponent_name, args.movetime, args.games))
    sys.stdout.flush()

    try:
        play_match(game, machete, opponent, args.movetime, args.max_plies, args.games, args.pause)
        with game.lock:
            print("match over: machete {} - {} - {} (W-L-D)".format(
                game.tally["machete"], game.tally["opponent"], game.tally["draw"]))
        sys.stdout.flush()
        # keep serving so the final position stays on screen
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        machete.quit()
        opponent.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
