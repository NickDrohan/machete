"""The live wall for ladder.py: every game in progress, on one page.

Kept apart from the ladder itself so the measurement code stays readable; the
ladder imports serve() and hands it the shared Live object.
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

WALL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>machete ladder</title>
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
<h1>machete rating ladder</h1>
<div class="sub" id="sub">starting...</div>
<div class="wall" id="wall"></div>
<table>
  <thead><tr><th class="name">opponent</th><th>rating</th><th>W</th><th>D</th><th>L</th>
  <th>score</th><th>implied</th></tr></thead>
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

  document.getElementById('rows').innerHTML = state.finished.map(row =>
    '<tr><td class="name">' + row.name + '</td><td>' + row.rating + '</td><td>' + row.w
    + '</td><td>' + row.d + '</td><td>' + row.l + '</td><td>' + row.score.toFixed(3)
    + '</td><td class="implied">' + Math.round(row.implied) + '</td></tr>').join('');
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
