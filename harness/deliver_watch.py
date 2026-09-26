"""Re-deliver team claude's strongest proven engine as SPRT verdicts arrive.

    python harness/deliver_watch.py --ledger RESULTS.tsv --folder E:/machete/competition/claude

Written for one night: the owner starts the final in the morning, and the
verdicts that decide what plays arrive while nobody is awake to act on them.
The rule is fixed here, in advance, so what is delivered follows from the
ledger and nothing else:

  1. SPRT-C-FULL accepted H1                       -> bundle + C2
  2. SPRT-C-NET2 and SPRT-C-BUNDLE both H1, and
     SPRT-C-FULL not rejected                      -> bundle + C2
  3. SPRT-C-NET2 accepted H1                       -> main + C2
  4. SPRT-C-BUNDLE accepted H1                     -> bundle + network A
  5. otherwise                                     -> main + network A

Only "accepted H1" counts as proof; an inconclusive run proves nothing. Each
candidate is checked before it is delivered (it names itself `machete
claude` and reads its network), files are copied under temporary names and
renamed, and READY names the commit and the network. Once a referee is
running, the watcher delivers nothing more and exits: the final uses the
folder as it stood when it began.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

DELIVERABLES = "E:/machete/claude/deliverables"
# which binary and network each candidate is; the commit that built each
# binary is in DELIVERABLES/manifest.json, so a faster build of the same
# search (an identical tree) can replace a binary while this runs
CANDIDATES = {
    "bundle+c2": ("bundle.exe", "c2.nnue"),
    "main+c2": ("main.exe", "c2.nnue"),
    "bundle+A": ("bundle.exe", "A.nnue"),
    "main+A": ("main.exe", "A.nnue"),
}


def verdicts(ledger):
    found = {}
    try:
        lines = open(ledger, encoding="utf-8").read().splitlines()
    except OSError:
        return found
    for line in lines[1:]:
        fields = line.split("\t")
        if len(fields) > 10:
            found[fields[1]] = fields[10]
    return found


def accepted(v, job):
    return v.get(job, "").startswith("accepted H1")


def rejected(v, job):
    return v.get(job, "").startswith("accepted H0")


def choose(v):
    if accepted(v, "SPRT-C-FULL"):
        return "bundle+c2"
    if accepted(v, "SPRT-C-NET2") and accepted(v, "SPRT-C-BUNDLE") and not rejected(v, "SPRT-C-FULL"):
        return "bundle+c2"
    if accepted(v, "SPRT-C-NET2"):
        return "main+c2"
    if accepted(v, "SPRT-C-BUNDLE"):
        return "bundle+A"
    return "main+A"


def referee_running():
    # psutil takes 35-50 s to walk this machine's processes; WMI answers for
    # just the Python ones in a second or two
    out = subprocess.run(["wmic", "process", "where", "name='python.exe' or name='py.exe'",
                          "get", "commandline"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         universal_newlines=True, timeout=60).stdout
    return "referee.py" in out


def md5(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()[:8]


def check(exe, net):
    out = subprocess.run([exe], input="uci\nquit\n", stdout=subprocess.PIPE,
                         universal_newlines=True, timeout=30).stdout
    if "id name machete claude" not in out:
        return "does not name itself machete claude"
    probe = subprocess.run([exe, "nnue", net, "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR", "w", "KQkq", "-", "0", "1"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    if probe.returncode != 0:
        return "cannot read its network"
    return ""


def fingerprint(name):
    """What delivering this candidate now would put in the folder."""
    exe_name, net_name = CANDIDATES[name]
    return (name, md5(os.path.join(DELIVERABLES, exe_name)), md5(os.path.join(DELIVERABLES, net_name)))


def deliver(name, folder, log):
    exe_name, net_name = CANDIDATES[name]
    exe = os.path.join(DELIVERABLES, exe_name)
    net = os.path.join(DELIVERABLES, net_name)
    commit = json.load(open(os.path.join(DELIVERABLES, "manifest.json")))[exe_name]
    problem = check(exe, net)
    if problem:
        log("NOT delivering {}: {}".format(name, problem))
        return False
    for source, target in ((exe, "machete.exe"), (net, "machete.nnue")):
        shutil.copyfile(source, os.path.join(folder, target + ".new"))
    for target in ("machete.exe", "machete.nnue"):
        os.replace(os.path.join(folder, target + ".new"), os.path.join(folder, target))
    with open(os.path.join(folder, "READY"), "w") as handle:
        handle.write("{}\n# {}: {} (md5 {}), network {} (md5 {})\n".format(
            commit, name, exe_name, md5(exe), net_name, md5(net)))
    log("delivered {}: {} + {}".format(name, exe_name, net_name))
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", default="RESULTS.tsv")
    parser.add_argument("--folder", default="E:/machete/competition/claude")
    parser.add_argument("--log", default="E:/machete/claude/deliver.log")
    parser.add_argument("--interval", type=int, default=60)
    args = parser.parse_args()

    def log(text):
        with open(args.log, "a") as handle:
            handle.write("{} {}\n".format(time.strftime("%Y-%m-%d %H:%M:%S"), text))

    current = None
    log("watching {} (rule: FULL, NET2+BUNDLE, NET2, BUNDLE, main+A)".format(args.ledger))
    while True:
        if referee_running():
            log("a referee is running: the folder is frozen, watcher exiting")
            return 0
        v = verdicts(args.ledger)
        want = fingerprint(choose(v))
        if want != current:
            log("verdicts: " + "; ".join("{} {}".format(k, v.get(k, "pending")[:40])
                                          for k in ("SPRT-C-FULL", "SPRT-C-NET2", "SPRT-C-BUNDLE")))
            if deliver(want[0], args.folder, log):
                current = want
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
