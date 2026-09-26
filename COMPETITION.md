# Cursor against Claude: two machetes, one final

Two agents each take machete from the same starting point and make it as
strong as they can with what is on this machine. Then the two engines play
each other under a referee neither side controls.

| team | agent | worktree | branches | deliverable folder |
|---|---|---|---|---|
| **cursor** | the Cursor agent | `D:/Dev/Claude/machete-cursor` | `cursor/*` | `E:/machete/competition/cursor/` |
| **claude** | Claude Code | `D:/Dev/Claude/machete-claude` | `claude/*` | `E:/machete/competition/claude/` |

Set by the owner on 2026-09-25. Only the owner changes this file after the fork.

## The fork

Both teams start from tag **`competition-fork`**: the engine at that commit
(machete 0.1's search plus X-04 and P0-2), network A (`net/machete.nnue`), the
whole harness, and every rule in ROADMAP_3500.md, HANDOFF.md and CLAUDE.md.
Both worktrees are created from it on the same commit.

**Nothing is shared after the fork.** Each team builds its own tools, fixes
its own bugs and writes its own ledger (`RESULTS.tsv` in its worktree). Do not
read, run, copy or merge from the other team's branches, worktree, deliverable
folder, data folder, or queue logs. Work already on other branches before the
fork (for example `feat/8`) belongs to whoever wrote it and is not part of the
common start.

## What each team may use

- Everything in the repository at the fork, including network A.
- The data on disk at the fork, read-only: `E:/machete/corpora/`,
  `E:/machete/subsets/`, `E:/machete/sizes/`, `data/*.bin` in the main
  worktree, and the networks under `E:/machete/`. Copy what you need into your
  own data folder, `E:/machete/<team>/`; never modify the originals.
- The external engines on this machine (Arena's engines, Stockfish and the
  rest) as teachers, labellers, sparring partners and analysers.
- **New data, within the budget:** at most **48 machine-hours** of data
  generation per team (`--kind data` jobs). The queue charges the hours and
  stops a job at the limit; `jobqueue.py status` shows both teams' tallies.
  Only the owner changes the budget, in `E:/machete/queue/budget.json`.

## How the machine is shared

First come, first served, through the one queue (`harness/jobqueue.py`,
queue folder `E:/machete/queue`, one runner):

- Every match, SPRT, gauntlet, tournament and data-generation run is a job,
  submitted with `--team <your team>`. Training is a job too, `--kind train`,
  in the queue's GPU lane, so two trainings never share the GPU.
- Outside the queue, only short single-threaded work: builds, unit tests,
  bench, `check.sh` gates that take under a few minutes. Check
  `jobqueue.py status` first and do not start them beside a running job.
- The runner is shared: do not stop it while the other team has a job running
  or pending, and do not change the runner's code in the shared queue's
  runner process - it runs from the `referee-v1` tag, not from either branch.
- The owner's own work (Arena tournaments, `--team owner` jobs) comes first.

## The engine rules

The delivered engine must, under the final's conditions:

- speak UCI and be named `machete <team>` in `id name`;
- search on **one thread** when given `Threads 1`, and use **at most 128 MB**
  for its transposition table and other search tables (the network itself is
  not counted);
- carry **no opening book and no endgame tablebases** of its own;
- load its network from `machete.nnue` beside the executable, as a GUI does.

Anything else is fair: search, evaluation, network architecture, training,
time management, speed.

## Delivering

Put `machete.exe` and `machete.nnue` in your deliverable folder, and a file
`READY` containing the commit hash that built them. Re-delivering replaces the
previous entry; the final uses whatever is in the folder when it starts. A
team may deliver early and keep improving.

## The final

Played by `harness/referee.py` from a clean checkout of tag **`referee-v1`**,
never from either team's branch:

```bash
py -3.7 -u harness/referee.py --a cursor=E:/machete/competition/cursor \
    --b claude=E:/machete/competition/claude --tc 10+0.1 --games 400 \
    --concurrency 8 --out E:/machete/competition/final-10+0.1.json
py -3.7 -u harness/referee.py --a cursor=E:/machete/competition/cursor \
    --b claude=E:/machete/competition/claude --tc 180+2 --games 200 \
    --concurrency 8 --out E:/machete/competition/final-180+2.json
```

- One thread and 128 MB each, set by the referee; the balanced book
  (`harness/books/balanced_200.epd`), every opening played twice with colours
  reversed; real clocks; no adjudication and no move cap - games end by the
  rules.
- A crash, an illegal move, or overrunning the clock (by 100 ms, or by 10 s
  for a hang) loses that game; the engine is restarted for the next.
- **The winner** scores more than half the points over all 600 games, pairs
  from both time controls pooled. The report gives the pentanomial Elo and its
  95% interval for each time control and pooled; if the interval contains
  zero, it says so beside the winner's name.
- The final starts when both `READY` files exist and both teams have said
  they are done, or when the owner calls it. There is no deadline.

## Changing these rules

Only the owner changes this file. A team that finds a rule is ambiguous or
unfair says so to the owner rather than interpreting it in its own favour.
