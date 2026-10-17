# machete status, 2026-10-14 21:00

## What I did

**Correction.** The 19:50 report said more Fischer Random data "does not help beyond 140M". That was wrong, and the line is open.

- The two tests behind it (C33F200 -18 ± 41 over 275 games, C33F280 -15 ± 37 over 351) were SPRTs with ±15 bounds that stopped early. Accepting H0 there means "not shown to gain 15 Elo". It does not mean worse, and both results are consistent with zero or a small gain.
- On 100,000 unseen classical positions with deep labels, the error falls with every addition: C33 0.00414, 0.4.0's network (140M) 0.00393, 200M 0.00390, 280M 0.00384. On 1,500-node labels: 0.00633, 0.00607, 0.00600, 0.00590.
- The trainer change between those runs was checked: the old and new trainers differ by no more than two runs of the same one.
- The real test is queued: CONFIRM-C33F280-C33F140, 1,500 games at 10+0.1, no early stop.

## Processes

- lichess bot: running
- orchestrator: running
- GPU queue runner: running
- lane A runner: running
- lane B runner: running
- farm watchdog: running
- live page relay: running
- deep-mate search: running
- GPU: 6 %, 6224 MiB, 8188 MiB, 44 (utilisation, memory used, memory total, temperature)

## Queues

**gpu**: 1 running, 1 pending
- running `TRAIN-C33F140K16F` since 2026-10-14 16:24:39: epoch 8 done: training loss 0.01558, validation 0.01619; last line: wrote E:/machete/claude/nets/c33f140k16f.nnue.partial (worst accumulator 16523 of 32767)
- pending `TRAIN-D15000X60`

**lane A**: 1 running, 4 pending
- running `KOI-C33F140-FAST2` since 2026-10-14 19:50:08
- pending `ZONES-C33F140K16F-C33F140` (waits for c33f140k16f.nnue)
- pending `TIMED-C33F140K16F-C33F140` (waits for c33f140k16f.nnue)
- pending `LADDER-D15000X60-D500X60` (waits for d15000x60.nnue)
- pending `CONFIRM-C33F280-C33F140`

**lane B**: 1 running, 1 pending
- running `SPSA040-R8` since 2026-10-14 20:51:11
- pending `SPSA040-R9`

## Results in the last 26 hours

| job | finished | W-D-L | Elo | verdict |
|---|---|---|---|---|
| `SPSA040-R7` | 10-14 20:51 |  |  |  |
| `SPSA040-R6` | 10-14 17:14 |  |  |  |
| `LADDER-C33F280-C33` | 10-14 16:54 | 57-102-42 | +26 ± 48 | accepted H1: the change is worth at least 15 Elo |
| `LADDER-C33F280-C33F140` | 10-14 16:43 | 70-196-85 | -15 ± 37 | accepted H0: the change is worth at most -15 Elo |
| `TRAIN-C33F280` | 10-14 16:24 |  |  |  |
| `SPSA040-R5` | 10-14 16:14 |  |  |  |
| `KOI-SPSA030-FAST` | 10-14 15:24 | 44-304-852 | -284 ± 27 |  |
| `SPSA040-R4` | 10-14 15:13 |  |  |  |
| `SPSA040-R3` | 10-14 14:12 |  |  |  |
| `SPSA040-R2` | 10-14 13:11 |  |  |  |
| `LONG-SPSA030-ON-040` | 10-14 13:07 | 49-326-25 | +21 ± 34 |  |
| `SPSA040-R1` | 10-14 12:11 |  |  |  |
| `SPSA-040-6` | 10-14 11:10 |  |  |  |
| `CONFIRM-SPSA030-ON-040` | 10-14 11:04 | 198-652-150 | +17 ± 22 |  |
| `SPSA-040-5` | 10-14 10:09 |  |  | **failed**: exit 4294967295 |
| `SPSA-040-4` | 10-14 10:09 |  |  |  |
| `SPSA-040-3` | 10-14 10:09 |  |  |  |
| `SPSA-040-2` | 10-14 10:08 |  |  |  |
| `SPSA-040-1` | 10-14 10:08 |  |  |  |
| `LADDER-C33F200-C33` | 10-14 09:57 | 45-74-28 | +40 ± 57 | accepted H1: the change is worth at least 15 Elo |
| `LADDER-C33F200-C33F140` | 10-14 09:52 | 57-147-71 | -18 ± 41 | accepted H0: the change is worth at most -15 Elo |
| `TRAIN-C33F200` | 10-14 09:42 |  |  |  |
| `SPRT-SPSA030-ON-040` | 10-14 03:10 | 88-247-46 | +38 ± 35 | accepted H1: the change is worth at least 10 Elo |
| `KOI-C33F140-FAST` | 10-14 02:48 | 34-290-876 | -302 ± 28 |  |
| `KOI-C33F140P3-FAST` | 10-14 02:47 | 33-315-852 | -290 ± 27 |  |
| `LONG2-C33F140P3-C33F140` | 10-13 21:29 | 125-570-105 | +9 ± 24 |  |

## Search tune (SPSA)

step 13681 of 15000; plus side +5590 =16234 -5498

| constant | default | now |
|---|---|---|
| AspWindow | 25 | 18.4 |
| FutBase | 120 | 115.4 |
| FutMul | 110 | 100.3 |
| IirDepth | 6 | 5.5 |
| LmpBase | 6 | 7.1 |
| LmrBase | 75 | 86.6 |
| LmrDiv | 225 | 213.5 |
| LmrHistDiv | 4096 | 3891.5 |
| NmpBase | 3 | 2.2 |
| NmpDiv | 3 | 2.9 |
| NmpEvalDiv | 200 | 185.1 |
| QsDelta | 200 | 201.7 |
| RfpMargin | 85 | 59.0 |
| SeDepth | 8 | 6.2 |
| SeMargin | 2 | 2.6 |

## Lichess bot

- ratings: bullet 2748 (317 games), blitz 2798 (1098 games), rapid 2807 (37 games)
- last 24 hours: 106 games: 15 W 54 D 37 L; not won against lower-rated: 13; last game started 25 min ago
- 10-12 23:37  ALARM: the lichess bot has played no game for 61 minutes and has no daily limit: restarting it
- 10-13 00:41  ALARM: the lichess bot has played no game for 63 minutes and has no daily limit: restarting it
- 10-13 01:42  ALARM: the lichess bot has played no game for 61 minutes and has no daily limit: restarting it
- 10-13 02:44  ALARM: the lichess bot has played no game for 61 minutes and has no daily limit: restarting it
- 10-14 03:05  ALARM: the lichess bot has played no game for 64 minutes and has no daily limit: restarting it

## Farm and orchestrator (last lines of its log)

```
10-14 05:20  mac starts n15000_mac_09 (4000000 positions at 15,000 nodes, seed 88109)
10-14 05:22  the 15,000-node set has reached 60M: training D15000X60 and matching it against D500X60
10-14 05:22  queueing TRAIN-D15000X60
10-14 05:22  queueing LADDER-D15000X60-D500X60
10-14 06:36  pi-02 finished n15000_pi02_08 (1000187 positions): pulled; the 15,000-node set is at 62.7M
10-14 06:36  pi-02 starts n15000_pi02_09 (1000000 positions at 15,000 nodes, seed 88309)
10-14 09:09  pi-01 finished n15000_pi01_06 (1000359 positions): pulled; the 15,000-node set is at 63.7M
10-14 09:09  pi-01 starts n15000_pi01_07 (1000000 positions at 15,000 nodes, seed 88207)
10-14 16:26  mac finished n15000_mac_09 (4000242 positions): pulled; the 15,000-node set is at 67.7M
10-14 16:26  mac starts n15000_mac_10 (4000000 positions at 15,000 nodes, seed 88110)
10-14 17:55  pi-02 finished n15000_pi02_09 (1000175 positions): pulled; the 15,000-node set is at 68.7M
10-14 17:55  pi-02 starts n15000_pi02_10 (1000000 positions at 15,000 nodes, seed 88310)
```

## Disks

- C 15 GB free of 299
- D 296 GB free of 3001
- E 6832 GB free of 8001

