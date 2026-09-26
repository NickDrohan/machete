"""A page showing the shared job queue: what runs, what waits, and rough times.

    python harness/queueview.py [--queue E:/machete/queue] [--port 8810] [--team claude]

Reads the queue folder the runner uses and serves one page that refreshes
itself. Other teams' jobs are shown by id, lane and times only; the viewing
team's own jobs also get their watch link and the last line of their log.

Times are estimates, not measurements: a job's length is a typical value for
its kind (ESTIMATE_HOURS), a running job is assumed to be that far along, and
each lane is assumed to run its jobs back to back in queue order. A job
waiting for a file starts no earlier than the job that makes it finishes.
"""

import argparse
import datetime
import glob
import html
import http.server
import json
import os
import re
import socket
import sys

# typical hours per (team, kind); an SPRT at 10+0.1 stops anywhere from half
# an hour to its 4000-game cap, so these are middles, not bounds
ESTIMATE_HOURS = {
    ("claude", "measure"): 1.5, ("cursor", "measure"): 1.5,
    ("claude", "train"): 0.6, ("cursor", "train"): 1.6,
}
LANE = {"measure": "cpu", "data": "cpu", "train": "gpu"}


def load(folder):
    jobs = []
    for path in sorted(glob.glob(os.path.join(folder, "*.json"))):
        try:
            job = json.load(open(path))
        except (OSError, ValueError):
            continue
        job["_file"] = path
        jobs.append(job)
    return jobs


def parse_time(text):
    return datetime.datetime.strptime(text, "%Y-%m-%d %H:%M:%S") if text else None


def hours(job):
    return ESTIMATE_HOURS.get((job.get("team"), job.get("kind")))


def watch_port(job):
    argv = job.get("argv") or []
    for i, word in enumerate(argv):
        if word == "--watch" and i + 1 < len(argv):
            return argv[i + 1]
    return None


def last_log_line(queue, job):
    name = os.path.splitext(os.path.basename(job["_file"]))[0] + ".txt"
    path = os.path.join(queue, "logs", name)
    try:
        with open(path, "rb") as handle:
            handle.seek(max(0, os.path.getsize(path) - 4000))
            text = handle.read().decode("utf-8", "replace")
    except OSError:
        return ""
    lines = [l.strip() for l in re.split(r"[\r\n]+", text) if l.strip()]
    return lines[-1][:160] if lines else ""


def listening(port):
    with socket.socket() as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", int(port))) == 0


def schedule(queue, now):
    running = load(os.path.join(queue, "running"))
    pending = load(os.path.join(queue, "pending"))
    free = {"cpu": now, "gpu": now}
    ready_at = {}          # output file -> estimated finish of the job making it
    rows = []
    for job in running:
        lane = LANE.get(job.get("kind"), "cpu")
        started = parse_time(job.get("started")) or now
        est = hours(job)
        finish = started + datetime.timedelta(hours=est) if est else None
        if finish and finish < now:
            finish = now + datetime.timedelta(minutes=10)
        if finish:
            free[lane] = max(free[lane], finish)
        if job.get("test", "").endswith(".nnue") and finish:
            ready_at[os.path.normcase(job["test"])] = finish
        rows.append((job, "running", started, finish))
    for job in pending:
        lane = LANE.get(job.get("kind"), "cpu")
        start = free[lane]
        for need in job.get("requires") or []:
            made = ready_at.get(os.path.normcase(need))
            if made and made > start:
                start = made
        est = hours(job)
        finish = start + datetime.timedelta(hours=est) if est else None
        if finish and not (job.get("requires") and start > free[lane]):
            free[lane] = finish
        elif finish:
            free[lane] = max(free[lane], finish)
        if job.get("test", "").endswith(".nnue") and finish:
            ready_at[os.path.normcase(job["test"])] = finish
        rows.append((job, "pending", start, finish))
    return rows


def page(queue, team):
    now = datetime.datetime.now()
    rows = schedule(queue, now)
    out = ["<!doctype html><html><head><meta charset='utf-8'><title>Machete Queue</title>",
           "<meta http-equiv='refresh' content='30'>",
           "<style>body{font:14px system-ui;margin:16px;background:#111;color:#ddd}"
           "table{border-collapse:collapse;width:100%}td,th{padding:4px 8px;border-bottom:1px solid #333;text-align:left}"
           "tr.claude td{color:#8fd}tr.cursor td{color:#fb8}tr.running td{font-weight:bold}"
           "a{color:#9cf}.note{color:#999}</style></head><body>",
           "<h2>Job queue at {}</h2>".format(now.strftime("%H:%M")),
           "<p class='note'>Estimated times: an SPRT is taken as {:.1f} h, training as {:.1f} h (claude) or {:.1f} h (cursor); "
           "lanes run back to back. Refreshes every 30 s.</p>".format(
               ESTIMATE_HOURS[("claude", "measure")], ESTIMATE_HOURS[("claude", "train")], ESTIMATE_HOURS[("cursor", "train")]),
           "<table><tr><th>#</th><th>state</th><th>job</th><th>team</th><th>lane</th><th>start</th><th>finish</th><th>watch / progress</th></tr>"]
    for n, (job, state, start, finish) in enumerate(rows, 1):
        mine = job.get("team") == team
        extra = ""
        if mine:
            port = watch_port(job)
            if port:
                live = listening(port)
                extra = "<a href='http://127.0.0.1:{0}'>:{0}</a> {1}".format(port, "live" if live else "")
            if state == "running":
                extra += " <span class='note'>{}</span>".format(html.escape(last_log_line(queue, job)))
            if job.get("requires") and state == "pending":
                missing = [r for r in job["requires"] if not os.path.exists(r)]
                if missing:
                    extra += " <span class='note'>waits for {}</span>".format(
                        html.escape(", ".join(os.path.basename(m) for m in missing)))
        fmt = lambda t: t.strftime("%a %H:%M") if t else "?"
        out.append("<tr class='{} {}'><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            job.get("team"), state, n, state, html.escape(job.get("id", "?")), job.get("team"),
            LANE.get(job.get("kind"), "cpu"), fmt(start), fmt(finish) if hours(job) else "unknown", extra))
    out.append("</table></body></html>")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", default="E:/machete/queue")
    parser.add_argument("--port", type=int, default=8810)
    parser.add_argument("--team", default="claude")
    args = parser.parse_args()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = page(args.queue, args.team).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print("queue view at http://127.0.0.1:{}".format(args.port))
    sys.stdout.flush()
    server.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
