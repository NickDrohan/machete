"""The job queue's claims, checked against a throwaway queue and ledger.

    python harness/test_jobqueue.py

Two runners are started at the same moment on the same queue. The claims:
exactly one of them works it and the other refuses; the jobs never overlap
in time; a job whose input does not exist yet is passed over and run once it
does; and every job leaves one ledger line, with match.py's summary parsed
and the prediction attached. Exits non-zero on the first failure, naming it.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "jobqueue.py")

# a stand-in for match.py: records when it ran, optionally creates a file,
# and prints the summary lines the runner parses
FAKE_MATCH = r"""
import sys, time
spans, name, make = sys.argv[1], sys.argv[2], sys.argv[3]
start = time.time()
time.sleep(1.5)
if make != "-":
    open(make, "w").close()
with open(spans, "a") as f:
    f.write("{} {:.3f} {:.3f}\n".format(name, start, time.time()))
# exactly match.py's closing lines for a finished SPRT
print("games 10 wins 4 draws 3 losses 3")
print("score 0.550")
print("llr +2.95")
print("accepted H1: the change is worth at least 10 Elo")
print("elo +35 +/- 120")
"""


def check(name, condition, detail=""):
    if condition:
        print("  ok   {}".format(name))
        return 0
    print("  FAIL {} {}".format(name, detail))
    return 1


def main():
    work = tempfile.mkdtemp(prefix="jobqueue-test-")
    queue = os.path.join(work, "queue")
    ledger = os.path.join(work, "RESULTS.tsv")
    spans = os.path.join(work, "spans.txt")
    made = os.path.join(work, "made-by-first-job")
    fake = os.path.join(work, "fake_match.py")
    with open(fake, "w") as f:
        f.write(FAKE_MATCH)
    with open(ledger, "w") as f:
        f.write("date\tid\tchange\ttest\tagainst\ttc\tgames\tresult\telo\tmargin95\tverdict\tsource")

    def jobqueue(*args):
        return [sys.executable, SCRIPT, "--queue", queue, "--ledger", ledger] + list(args)

    # submitted first, but it needs a file the second job creates
    subprocess.check_call(jobqueue("submit", "--id", "T-WAITS", "--change", "waits for an input",
                                   "--predicted", "+5", "--requires", made, "--",
                                   sys.executable, fake, spans, "waits", "-"),
                          stdout=subprocess.DEVNULL)
    time.sleep(0.01)
    subprocess.check_call(jobqueue("submit", "--id", "T-MAKES", "--change", "creates the input",
                                   "--predicted", "0", "--",
                                   sys.executable, fake, spans, "makes", made),
                          stdout=subprocess.DEVNULL)

    run = jobqueue("run", "--exit-when-empty", "--no-wait-quiet")
    runners = [subprocess.Popen(run, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                universal_newlines=True) for _ in range(2)]
    outputs, codes = [], []
    for r in runners:
        out, _ = r.communicate(timeout=60)
        outputs.append(out)
        codes.append(r.returncode)

    failures = 0
    failures += check("one runner works the queue and the other refuses",
                      sorted(codes) == [0, 3], "exit codes {}".format(codes))

    with open(spans) as f:
        rows = [line.split() for line in f if line.strip()]
    order = [row[0] for row in rows]
    failures += check("both jobs ran, the one waiting for its input second",
                      order == ["makes", "waits"], "order {}".format(order))
    spans_by_start = sorted((float(row[1]), float(row[2]), row[0]) for row in rows)
    overlaps = ["{} started {:.2f} s before {} ended".format(b[2], a[1] - b[0], a[2])
                for a, b in zip(spans_by_start, spans_by_start[1:]) if b[0] < a[1]]
    failures += check("no two jobs overlapped in time", not overlaps, "; ".join(overlaps))

    with open(ledger) as f:
        lines = f.read().splitlines()
    body = [line.split("\t") for line in lines[1:]]
    failures += check("every job left exactly one ledger line, in the order they ran",
                      [row[1] for row in body] == ["T-MAKES", "T-WAITS"],
                      "ids {}".format([row[1] for row in body]))
    failures += check("ledger lines have all twelve columns", all(len(row) == 12 for row in body),
                      "widths {}".format([len(row) for row in body]))
    if body:
        row = body[-1]
        failures += check("match.py's summary is parsed into the line",
                          row[6] == "10" and row[7] == "4-3-3" and row[8] == "+35" and row[9] == "120",
                          "games {} result {} elo {} margin {}".format(*row[6:10]))
        failures += check("the prediction is recorded next to the verdict",
                          "accepted H1" in row[10] and "LLR +2.95" in row[10]
                          and "predicted +5" in row[10], row[10])

    done = os.listdir(os.path.join(queue, "done"))
    failures += check("both jobs end in done/", len(done) == 2, "done/ holds {}".format(done))
    if done:
        with open(os.path.join(queue, "done", sorted(done)[0])) as f:
            job = json.load(f)
        failures += check("a finished job keeps its log path and exit code",
                          job.get("exit") == 0 and job.get("log", "").endswith(".txt"), str(job))

    if failures:
        print("runner output:\n" + "\n---\n".join(outputs))
        print("left in {}".format(work))
        return 1
    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
