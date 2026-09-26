"""One queue for the machine: measurements run one at a time, never two at once.

    python harness/jobqueue.py submit --team cursor --id SPRT-S06 \
        --change "S-06: mate distance pruning" --against "dev (b454e97)" \
        --tc "movetime 200" --predicted +3 --requires E:/machete/ab/s06.exe -- \
        py -3.7 -u harness/match.py E:/machete/ab/s06.exe E:/machete/ab/dev.exe --sprt 0 10 ...
    python harness/jobqueue.py status
    python harness/jobqueue.py run          # the runner; start it with harness/detach.ps1

Agents write patches faster than the machine can judge them, and two
measurements at once contaminate each other (ROADMAP_3500.md P0-5). So a
measurement is a job file, and exactly one runner plays jobs, in two lanes:

- **cpu** (`--kind measure`, the default, and `--kind data`): strictly one at
  a time, in submission order, and only once the machine is quiet - no
  engine, match driver, data generator or Arena running outside the queue.
- **gpu** (`--kind train`): network training, one at a time, in order, beside
  whatever the cpu lane is doing. Training barely touches the CPU, but two
  trainings at once would fight over one 8 GB GPU.

A job whose `--requires` files do not exist yet is passed over and retried,
so point it at finished copies, never at a network still training. Every
job, pass or fail, leaves one line in the submitter's RESULTS.tsv with the
prediction written before it ran, and its whole output in logs/.

Jobs run in the working tree they were submitted from, so two worktrees (the
COMPETITION.md teams) share one queue and one runner but each keeps its own
code and ledger. `--kind data` is charged to the team: once a team's data
jobs have used budget.json's `data_hours`, its next one is refused and a
running one is stopped at the limit.

A second runner refuses to start. A job that was running when its runner
died goes back to the front of its lane once, then fails.

The queue lives in MACHETE_QUEUE, default E:/machete/queue: pending/,
running/, done/, failed/, logs/, runner.pid, runner.log, budget.json. This
is not harness/queue.py because a module of that name here would shadow the
standard library's queue for every script in the folder.
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

try:
    import psutil
except ImportError:
    psutil = None

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
QUEUE = os.environ.get("MACHETE_QUEUE", "E:/machete/queue")
LEDGER = os.path.join(ROOT, "RESULTS.tsv")

TEAMS = ("cursor", "claude", "owner")
KINDS = {"measure": "cpu", "data": "cpu", "train": "gpu"}
DEFAULT_BUDGET = {"data_hours": 48.0}

# What counts as a measurement or heavy CPU work that a job must not overlap.
# Training is deliberately absent: it runs on the GPU and barely touches the CPU.
BUSY_NAMES = re.compile(r"^(machete.*|arena|cutechess.*|fastchess.*|cont)\.exe$", re.I)
BUSY_SCRIPTS = re.compile(
    r"harness[\\/](match|tournament|ladder|stable|scaling|endgame_suite|conversion|"
    r"shadow|divergence|watch|missed|audit|blunders|referee)\.py|"
    r"harness[\\/]nnue[\\/](gen|endgames|panel|calibrate|disagree)\.py", re.I)

EXIT_ALREADY_RUNNING = 3
MAX_ATTEMPTS = 2
LEDGER_COLUMNS = 12


def now():
    return datetime.datetime.now()


def stamp():
    return now().strftime("%Y-%m-%d %H:%M:%S")


class Queue(object):
    def __init__(self, root, ledger):
        self.root = root
        self.ledger = ledger
        self.dirs = {name: os.path.join(root, name)
                     for name in ("pending", "running", "done", "failed", "logs")}
        for path in self.dirs.values():
            os.makedirs(path, exist_ok=True)
        self.pidfile = os.path.join(root, "runner.pid")
        self.logfile = os.path.join(root, "runner.log")
        self.budgetfile = os.path.join(root, "budget.json")
        # the two lanes share the log, the ledgers and the job folders
        self.mutex = threading.RLock()

    def say(self, text):
        line = "{}  {}".format(stamp(), text)
        with self.mutex:
            print(line, flush=True)
            with open(self.logfile, "a", encoding="utf-8") as log:
                log.write(line + "\n")

    def jobs(self, state, lane=None):
        folder = self.dirs[state]
        paths = [os.path.join(folder, name) for name in sorted(os.listdir(folder))
                 if name.endswith(".json")]
        if lane is None:
            return paths
        return [p for p in paths if KINDS.get((try_load(p) or {}).get("kind", "measure")) == lane]

    def budget(self):
        if os.path.exists(self.budgetfile):
            with open(self.budgetfile) as f:
                merged = dict(DEFAULT_BUDGET)
                merged.update(json.load(f))
                return merged
        return dict(DEFAULT_BUDGET)

    def hours(self, team, kind):
        """Machine-hours a team's jobs of one kind have used, finished or running."""
        total = 0.0
        for state in ("done", "failed", "running"):
            for path in self.jobs(state):
                job = try_load(path)
                if job is None or job.get("team") != team or job.get("kind", "measure") != kind:
                    continue
                start = job.get("started_ts")
                if start:
                    total += (job.get("finished_ts") or time.time()) - start
        return total / 3600.0

    # ------------------------------------------------------------ submitting

    def submit(self, job):
        # the name sorts by submission time, which is the order jobs run in
        name = "{}-{}.json".format(now().strftime("%Y%m%d-%H%M%S-%f"),
                                   re.sub(r"[^A-Za-z0-9_.-]", "_", job["id"]))
        path = os.path.join(self.dirs["pending"], name)
        temp = path + ".tmp"
        with open(temp, "w", encoding="utf-8") as out:
            json.dump(job, out, indent=2)
        # a runner never sees a half-written job
        os.replace(temp, path)
        return path

    # ------------------------------------------------------------ the lock

    def lock(self):
        """Become the only runner, or say which process already is."""
        for _ in range(2):
            try:
                fd = os.open(self.pidfile, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                holder = read_pid(self.pidfile)
                if holder and pid_alive(holder):
                    return holder
                # left by a runner that died; take it over
                os.remove(self.pidfile)
                continue
            with os.fdopen(fd, "w") as out:
                out.write(str(os.getpid()))
            return None
        return read_pid(self.pidfile)

    def unlock(self):
        if read_pid(self.pidfile) == os.getpid():
            os.remove(self.pidfile)

    # ------------------------------------------------------------ running

    def recover(self):
        """A job left in running/ belonged to a runner that died mid-job."""
        for path in self.jobs("running"):
            job = load(path)
            job["attempts"] = job.get("attempts", 0) + 1
            job.setdefault("history", []).append("{} runner died while this ran".format(stamp()))
            job.pop("started_ts", None)
            if job["attempts"] >= MAX_ATTEMPTS:
                self.finish(path, job, "failed", "runner died {} times".format(job["attempts"]))
            else:
                save(path, job)
                shutil.move(path, self.dirs["pending"])
                self.say("{}: requeued after its runner died".format(job["id"]))

    def next_job(self, lane):
        """The first pending job in this lane whose inputs exist."""
        with self.mutex:
            for path in self.jobs("pending", lane):
                job = load(path)
                missing = [f for f in job.get("requires", []) if not os.path.exists(f)]
                if not missing:
                    return path, job
        return None, None

    def wait_quiet(self, ignore):
        reported = 0.0
        while True:
            busy = busy_processes(ignore)
            if not busy:
                return
            if time.time() - reported > 600:
                self.say("waiting for a quiet machine: " + "; ".join(busy[:5]))
                reported = time.time()
            time.sleep(30)

    def run_one(self, path, job):
        timeout = job.get("timeout_hours")
        if job.get("kind") == "data":
            left = self.budget()["data_hours"] - self.hours(job.get("team"), "data")
            if left <= 0:
                with self.mutex:
                    self.finish(path, job, "failed", "refused: {} has spent its data budget".format(job.get("team")))
                return
            timeout = left if timeout is None else min(timeout, left)
        with self.mutex:
            running = os.path.join(self.dirs["running"], os.path.basename(path))
            shutil.move(path, running)
            job["started"] = stamp()
            job["started_ts"] = time.time()
            save(running, job)
        log = os.path.join(self.dirs["logs"], os.path.basename(path)[:-5] + ".txt")
        cwd = job.get("cwd") or ROOT
        self.say("{} [{}]: started in {} - {}".format(job["id"], job.get("team", "-"), cwd,
                                                    " ".join(job["argv"])))
        code, error = None, ""
        with open(log, "w", encoding="utf-8") as out:
            out.write("# {} [{}]\n# {}\n# predicted {}\n".format(
                job["id"], job.get("team", "-"), " ".join(job["argv"]), job.get("predicted", "-")))
            out.flush()
            try:
                proc = subprocess.Popen(job["argv"], cwd=cwd, stdout=out, stderr=subprocess.STDOUT)
                try:
                    code = proc.wait(timeout=timeout * 3600 if timeout else None)
                except subprocess.TimeoutExpired:
                    kill_tree(proc.pid)
                    code = proc.wait()
                    error = "stopped at its limit of {:.2f} h{}".format(
                        timeout, " (data budget)" if job.get("kind") == "data" else "")
                    out.write("\n# {}\n".format(error))
            except Exception as e:
                # the type, not just the message: an empty message once cost 740 games
                error = "{}: {}".format(type(e).__name__, e)
                out.write("\n# could not run: {}\n".format(error))
        with self.mutex:
            job["finished"] = stamp()
            job["finished_ts"] = time.time()
            job["exit"] = code
            job["log"] = shown_path(log)
            summary = parse_result(read_text(log))
            state = "done" if code == 0 and not error else "failed"
            note = error or ("" if code == 0 else "exit {}".format(code))
            self.finish(running, job, state, note, summary)

    def finish(self, path, job, state, note, summary=None):
        summary = summary or {}
        job["state"] = state
        job["result"] = summary
        if note:
            job["note"] = note
        save(path, job)
        shutil.move(path, self.dirs[state])
        self.record(job, summary, note)
        self.say("{}: {} - {}".format(job["id"], state, summary.get("verdict") or note or "no verdict"))

    def record(self, job, summary, note):
        verdict = summary.get("verdict") or ("no result - " + note if note else "no verdict parsed")
        if job.get("predicted"):
            verdict = "{} (predicted {})".format(verdict, job["predicted"])
        row = [now().strftime("%Y-%m-%d"), job["id"], job.get("change", "-"),
               job.get("test", "-"), job.get("against", "-"), job.get("tc", "-"),
               summary.get("games", "-"), summary.get("wdl", "-"), summary.get("elo", "-"),
               summary.get("margin", "-"), verdict, job.get("log", "logs")]
        assert len(row) == LEDGER_COLUMNS
        row = [str(cell).replace("\t", " ").replace("\n", " ") for cell in row]
        append_line(job.get("ledger") or self.ledger, "\t".join(row))

    def lane(self, name, ignore, wait_quiet, idle_exit, exit_when_empty, stop):
        idle_since = time.time()
        while not stop.is_set():
            path, job = self.next_job(name)
            if path is None:
                if exit_when_empty and not self.jobs("pending", name):
                    return
                if idle_exit and time.time() - idle_since > idle_exit * 60:
                    return
                time.sleep(1 if exit_when_empty else 30)
                continue
            if wait_quiet and name == "cpu":
                self.wait_quiet(ignore)
            self.run_one(path, job)
            idle_since = time.time()

    def run(self, ignore, wait_quiet, idle_exit, exit_when_empty):
        holder = self.lock()
        if holder:
            print("another runner is already working this queue (pid {})".format(holder))
            return EXIT_ALREADY_RUNNING
        try:
            self.say("runner started, pid {}".format(os.getpid()))
            self.recover()
            stop = threading.Event()
            gpu = threading.Thread(target=self.lane,
                                   args=("gpu", ignore, wait_quiet, idle_exit, exit_when_empty, stop))
            gpu.daemon = True
            gpu.start()
            self.lane("cpu", ignore, wait_quiet, idle_exit, exit_when_empty, stop)
            gpu.join()
            self.say("runner stopping: {}".format(
                "queue empty" if exit_when_empty else "nothing runnable for {} minutes".format(idle_exit)))
            return 0
        finally:
            self.unlock()

    def status(self):
        holder = read_pid(self.pidfile)
        alive = bool(holder and pid_alive(holder))
        print("queue: {}".format(self.root))
        print("runner: {}".format("pid {}".format(holder) if alive else "not running"))
        for state in ("running", "pending", "failed", "done"):
            jobs = self.jobs(state)
            print("{}: {}".format(state, len(jobs)))
            if state in ("running", "pending"):
                for path in jobs:
                    job = load(path)
                    missing = [f for f in job.get("requires", []) if not os.path.exists(f)]
                    print("  {} [{} {}]{}".format(job["id"], job.get("team", "-"), job.get("kind", "measure"),
                                                 "  (waiting for {})".format(missing[0]) if missing else ""))
        budget = self.budget()["data_hours"]
        for team in TEAMS:
            used = {kind: self.hours(team, kind) for kind in KINDS}
            if any(used.values()):
                print("{}: measure {:.1f} h, data {:.1f} of {:.0f} h, train {:.1f} h".format(
                    team, used["measure"], used["data"], budget, used["train"]))
        busy = busy_processes(None)
        print("machine: {}".format("quiet" if not busy else "busy - " + "; ".join(busy[:5])))


# ---------------------------------------------------------------- helpers

def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def try_load(path):
    """A job file, or None if the other lane moved it in the meantime."""
    try:
        return load(path)
    except (OSError, ValueError):
        return None


def save(path, job):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(job, f, indent=2)


def read_text(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def shown_path(path):
    """Relative to the repository when it is inside it; a queue on another drive stays absolute."""
    try:
        rel = os.path.relpath(path, ROOT)
    except ValueError:
        return path.replace("\\", "/")
    return (path if rel.startswith("..") else rel).replace("\\", "/")


def read_pid(path):
    try:
        with open(path) as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def need_psutil():
    if psutil is None:
        raise RuntimeError("jobqueue needs psutil (py -3.7 -m pip install psutil)")


def pid_alive(pid):
    need_psutil()
    if not psutil.pid_exists(pid):
        return False
    try:
        return "jobqueue" in " ".join(psutil.Process(pid).cmdline())
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def kill_tree(pid):
    need_psutil()
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    for child in parent.children(recursive=True) + [parent]:
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass


def append_line(path, line):
    """Append one row, adding the newline the file might be missing."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        needs_newline = f.tell() > 0
        if needs_newline:
            f.seek(-1, os.SEEK_END)
            needs_newline = f.read(1) != b"\n"
    with open(path, "ab") as f:
        f.write(((b"\n" if needs_newline else b"") + line.encode("utf-8") + b"\n"))


def busy_processes(ignore):
    """Other work on the machine that a measurement must not overlap."""
    need_psutil()
    me = os.getpid()
    found = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        info = p.info
        if info["pid"] == me:
            continue
        name = info.get("name") or ""
        line = " ".join(info.get("cmdline") or [])
        if ignore and (ignore.search(name) or ignore.search(line)):
            continue
        match = BUSY_SCRIPTS.search(line)
        if BUSY_NAMES.match(name) or match:
            found.append("{} ({}{})".format(name, info["pid"], ", " + match.group(0) if match else ""))
    return found


def parse_result(text):
    """The summary match.py prints at the end, as ledger fields."""
    out = {}
    m = re.search(r"^games (\d+) wins (\d+) draws (\d+) losses (\d+)", text, re.M)
    if m:
        out["games"] = m.group(1)
        out["wdl"] = "{}-{}-{}".format(m.group(2), m.group(3), m.group(4))
    m = re.search(r"^elo ([+-]?\S+)(?: \+/- (\S+))?", text, re.M)
    if m:
        out["elo"] = m.group(1)
        out["margin"] = m.group(2) or "-"
    m = re.search(r"^(accepted H[01]|inconclusive).*$", text, re.M)
    if m:
        out["verdict"] = m.group(0).strip()
        llr = re.search(r"^llr (\S+)", text, re.M)
        if llr:
            out["verdict"] += ", LLR " + llr.group(1)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--queue", default=QUEUE, help="queue folder (default $MACHETE_QUEUE or E:/machete/queue)")
    parser.add_argument("--ledger", default=LEDGER,
                        help="ledger a submitted job reports to (default this worktree's RESULTS.tsv)")
    commands = parser.add_subparsers(dest="command")

    submit = commands.add_parser("submit", help="add a job; everything after -- is its command")
    submit.add_argument("--team", required=True, choices=TEAMS, help="whose job this is (COMPETITION.md)")
    submit.add_argument("--kind", default="measure", choices=sorted(KINDS),
                        help="measure (cpu lane), data (cpu lane, charged to the data budget), train (gpu lane)")
    submit.add_argument("--id", required=True, help="ledger id, e.g. SPRT-S06")
    submit.add_argument("--change", required=True, help="what is being tested")
    submit.add_argument("--predicted", required=True,
                        help="the Elo you expect, written before it runs (ROADMAP section 4); '-' for data or training")
    submit.add_argument("--test", default="-", help="the candidate, e.g. wp/S-06")
    submit.add_argument("--against", default="-", help="the baseline, with its commit")
    submit.add_argument("--tc", default="-", help="time control or node count")
    submit.add_argument("--requires", action="append", default=[],
                        help="a file that must exist before the job may start; repeatable")
    submit.add_argument("--timeout-hours", type=float, default=None, help="stop the job after this long")
    submit.add_argument("argv", nargs=argparse.REMAINDER)

    run = commands.add_parser("run", help="be the runner")
    run.add_argument("--idle-exit", type=float, default=60,
                     help="stop after this many minutes with nothing runnable; 0 = never")
    run.add_argument("--exit-when-empty", action="store_true",
                     help="stop as soon as nothing is pending (tests)")
    run.add_argument("--no-wait-quiet", action="store_true",
                     help="do not wait for other work to finish (tests only)")
    run.add_argument("--ignore", default="",
                     help="regex of process names or command lines that do not count as busy")

    commands.add_parser("status", help="what is queued, running, and on the machine")
    args = parser.parse_args()

    queue = Queue(os.path.abspath(args.queue), os.path.abspath(args.ledger))
    if args.command == "submit":
        argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
        if not argv:
            parser.error("submit needs a command after --")
        job = {"id": args.id, "team": args.team, "kind": args.kind, "change": args.change,
               "predicted": args.predicted, "test": args.test, "against": args.against, "tc": args.tc,
               "requires": [os.path.abspath(f) for f in args.requires],
               "timeout_hours": args.timeout_hours,
               "cwd": ROOT, "ledger": os.path.abspath(args.ledger),
               "argv": argv, "submitted": stamp(), "attempts": 0}
        print(queue.submit(job))
        return 0
    if args.command == "run":
        ignore = re.compile(args.ignore, re.I) if args.ignore else None
        return queue.run(ignore, not args.no_wait_quiet, args.idle_exit, args.exit_when_empty)
    if args.command == "status":
        queue.status()
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
