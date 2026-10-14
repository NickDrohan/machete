# Status branch

This branch is not for merging. It carries machete's status reports while the
owner is away: every two hours an unattended session on the home PC checks
everything that is running (lichess bot, queues, GPU training, the Mac and Pi
farm, the search tune), fixes what it can, keeps the queues full, and commits a
report here.

- `STATUS.md` is the latest report.
- `reports/YYYY-MM-DD/HHMM.md` keeps every report.

To steer the work, comment on the pull request that tracks this branch. Each
run reads new comments, answers them there, and acts on them where the
instruction is clear.
