"""Making games observable: live on a page while they run, and kept afterwards.

Any harness that plays games serves one of these, on by default rather than
behind a flag. A match that takes an hour and shows nothing is a black box,
and the first thing anyone asks when a number looks wrong is what the games
actually looked like.

A harness builds a Live, hands it to serve() on a daemon thread, and calls
set_board() as moves are played. Nothing here knows what the harness is
measuring, so the same wall serves a rating ladder, an A/B match and a
gold-set run.

save_game() is the other half. Games are expensive - the gold set cost seven
hours of six engines - and a finished match that kept only its win count has
thrown away everything except one number. The positions are worth keeping even
when there is no immediate use for them: they are where our engine actually
goes, which is not the same distribution a teacher's self-play visits.
"""

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import chess
import chess.pgn

GLYPHS = {
    "K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙",
    "k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟",
}


class Live(object):
    """What the page reads: one slot per worker, plus finished pairings."""

    def __init__(self, workers, title="machete", columns=("opponent", "rating", "W", "D", "L", "score", "implied")):
        self.lock = threading.Lock()
        self.title = title
        self.columns = list(columns)
        self.boards = [{"opponent": "", "white": "", "black": "", "squares": [""] * 64,
                        "lastMove": None, "plies": 0, "result": None} for _ in range(workers)]
        self.finished = []
        self.current = ""
        self.progress = ""

    def set_board(self, slot, board, white_name, black_name, result=None):
        """Show a position. Both sides are named explicitly: a match between two
        of our own networks has no "us" and no "opponent"."""
        squares = []
        for rank in range(7, -1, -1):
            for file in range(8):
                piece = board.piece_at(chess.square(file, rank))
                squares.append(GLYPHS[piece.symbol()] if piece else "")
        last = board.move_stack[-1] if board.move_stack else None
        with self.lock:
            self.boards[slot % len(self.boards)] = {
                "opponent": "{} vs {}".format(white_name, black_name),
                "white": white_name,
                "black": black_name,
                "squares": squares,
                "lastMove": [last.from_square, last.to_square] if last else None,
                "plies": board.ply(),
                "result": result,
            }

    def say(self, current, progress=""):
        with self.lock:
            self.current = current
            self.progress = progress

    def snapshot(self):
        with self.lock:
            return {"boards": list(self.boards), "finished": list(self.finished),
                    "title": self.title, "columns": self.columns,
                    "current": self.current, "progress": self.progress}


PGN_LOCK = threading.Lock()


def save_game(path, board, white_name, black_name, event, outcome,
              headers=None, clocks=None):
    """Append one finished game. Safe to call from several workers at once.

    `clocks`, when the game was played on a real clock, holds each mover's
    remaining time after each move, in milliseconds, and is written as the
    standard `[%clk h:mm:ss]` comment that GUIs show beside the move.
    """
    if not path:
        return
    game = chess.pgn.Game.from_board(board)
    game.headers["Event"] = event
    game.headers["White"] = white_name
    game.headers["Black"] = black_name
    game.headers["Result"] = outcome
    for name, value in (headers or {}).items():
        game.headers[name] = value
    if clocks and any(c is not None for c in clocks):
        # the clocks cover the moves the engines played, which are the last
        # ones; opening moves given to them come first and carry no clock
        node = game
        for _ in range(max(0, len(board.move_stack) - len(clocks))):
            node = node.variation(0)
        for remaining in clocks:
            if not node.variations:
                break
            node = node.variation(0)
            if remaining is not None:
                seconds = max(0.0, remaining / 1000.0)
                node.comment = "[%clk {}:{:02d}:{:04.1f}]".format(
                    int(seconds // 3600), int(seconds % 3600 // 60), seconds % 60)
    with PGN_LOCK:
        with open(path, "a") as handle:
            handle.write(str(game) + chr(10) + chr(10))


def free_port(preferred):
    """The preferred port, or any free one. A dead server's socket can linger."""
    for candidate in (preferred, 0):
        probe = socket.socket()
        try:
            probe.bind(("127.0.0.1", candidate))
            port = probe.getsockname()[1]
            probe.close()
            return port
        except OSError:
            probe.close()
    return preferred


def start(live, port, title):
    """Serve the wall on a daemon thread and print where to watch it."""
    chosen = free_port(port)
    threading.Thread(target=serve, args=(live, chosen), daemon=True).start()
    print("watch {} at http://127.0.0.1:{}".format(title, chosen))
    return chosen

WALL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>machete</title>
<style>
  :root { --bg:#12141a; --panel:#1b1e26; --line:#2c313d; --text:#e6e9f0; --dim:#8a93a6;
          --light:#b9a789; --dark:#6d5e48; --mark:#c8a33266; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text); padding:18px;
         font:14px/1.5 "Segoe UI", system-ui, sans-serif; }
  h1 { font-size:18px; margin:0 0 2px; letter-spacing:.3px; }
  .sub { color:var(--dim); font-size:13px; margin-bottom:16px; }
  .wall { display:flex; flex-wrap:wrap; gap:14px; }
  .game { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:10px; }
  .tag { font-size:12px; color:var(--dim); margin-bottom:6px; white-space:nowrap; }
  .tag b { color:var(--text); font-weight:600; }
  .board { display:grid; grid-template-columns:repeat(8,26px); grid-template-rows:repeat(8,26px);
           border-radius:3px; overflow:hidden; }
  .sq { display:flex; align-items:center; justify-content:center; font-size:19px; line-height:1; }
  .sq.light { background:var(--light); } .sq.dark { background:var(--dark); }
  .sq.mark { box-shadow: inset 0 0 0 40px var(--mark); }
  .sq span.w { color:#fcfcfa; text-shadow:0 0 1px #000,0 0 2px #000; }
  .sq span.b { color:#17181c; text-shadow:0 0 1px rgba(255,255,255,.5); }
  table { border-collapse:collapse; margin-top:20px; font-size:13px;
          font-variant-numeric:tabular-nums; }
  th, td { text-align:right; padding:5px 14px 5px 0; }
  th { color:var(--dim); font-weight:500; border-bottom:1px solid var(--line); }
  td.name, th.name { text-align:left; }
  .implied { color:#7fd18a; font-weight:600; }
</style>
</head>
<body>
<h1 id="title">machete</h1>
<div class="sub" id="sub">starting...</div>
<div class="wall" id="wall"></div>
<table>
  <thead id="head"></thead>
  <tbody id="rows"></tbody>
</table>
<script>
const wall = document.getElementById('wall');
const BLACK_PIECES = '\\u265a\\u265b\\u265c\\u265d\\u265e\\u265f';

function cellsFor(el) {
  if (el.children.length) return [...el.children];
  for (let i = 0; i < 64; i++) {
    const sq = document.createElement('div');
    const rank = Math.floor(i / 8), file = i % 8;
    sq.className = 'sq ' + ((rank + file) % 2 === 0 ? 'light' : 'dark');
    el.appendChild(sq);
  }
  return [...el.children];
}

function squareIndex(sq) {        // chess square number -> cell, white at the bottom
  return (7 - Math.floor(sq / 8)) * 8 + (sq % 8);
}

async function tick() {
  let state;
  try { state = await (await fetch('/state')).json(); } catch (e) { return; }
  document.getElementById('sub').textContent = state.current + '   ' + state.progress;

  state.boards.forEach((game, i) => {
    let card = document.getElementById('g' + i);
    if (!card) {
      card = document.createElement('div');
      card.className = 'game';
      card.id = 'g' + i;
      card.innerHTML = '<div class="tag" id="t' + i + '"></div>'
                     + '<div class="board" id="b' + i + '"></div>';
      wall.appendChild(card);
    }
    const cells = cellsFor(document.getElementById('b' + i));
    game.squares.forEach((glyph, n) => {
      const isBlack = glyph && BLACK_PIECES.includes(glyph);
      cells[n].innerHTML = glyph
        ? '<span class="' + (isBlack ? 'b' : 'w') + '">' + glyph + '</span>' : '';
      cells[n].classList.remove('mark');
    });
    if (game.lastMove) game.lastMove.forEach(sq => cells[squareIndex(sq)].classList.add('mark'));
    document.getElementById('t' + i).innerHTML =
      '<b>' + (game.white || '') + '</b> vs <b>' + (game.black || '') + '</b>'
      + ' &middot; ' + game.plies + ' plies'
      + (game.result ? ' &middot; ' + game.result : '');
  });

  document.title = state.title;
  document.getElementById('title').textContent = state.title;
  document.getElementById('head').innerHTML = '<tr>' + state.columns.map((c, i) =>
    '<th' + (i === 0 ? ' class="name"' : '') + '>' + c + '</th>').join('') + '</tr>';
  document.getElementById('rows').innerHTML = state.finished.map(row =>
    '<tr>' + row.map((cell, i) =>
      '<td' + (i === 0 ? ' class="name"' : (i === row.length - 1 ? ' class="implied"' : ''))
      + '>' + cell + '</td>').join('') + '</tr>').join('');
}
tick();
setInterval(tick, 500);
</script>
</body>
</html>
"""


def serve(live, port):
    """Serve the wall and the state it reads. Runs forever; call on a daemon thread."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/state"):
                body = json.dumps(live.snapshot()).encode("utf-8")
                kind = "application/json"
            else:
                body = WALL.encode("utf-8")
                kind = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
