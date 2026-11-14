# machete status, 2026-10-14 12:23

## What I did

First full run, done by hand to test the loop end to end (12:23).

- Everything standing is running; nothing needed repair.
- GPU: TRAIN-C33F280 in epoch 5 of 14 (about 4 hours left). Its matches against 0.4.0's network start by themselves.
- Lane A: 0.3.0 search tune at 60+0.6 against 0.4.0's defaults (400 games). So far it has +38 ± 35 (SPRT, 381 games) and +17 ± 22 (1,000 games) at 10+0.1.
- Lane B: the search tune (SPSA), chunk 2 of 6, about step 7,800 of 15,000.
- No comments from the owner yet.

The schedule now runs inside the owner's main Claude session every two hours, at 17 minutes past even hours. The desktop scheduled task was turned off because its permission prompts could not be seen.

## Processes

- lichess bot: running
- orchestrator: running
- GPU queue runner: running
- lane A runner: running
- lane B runner: running
- farm watchdog: running
- deep-mate search: running
- GPU: 74 %, 6522 MiB, 8188 MiB, 59 (utilisation, memory used, memory total, temperature)

## Queues

**gpu**: 1 running, 2 pending
- running `TRAIN-C33F280` since 2026-10-14 09:42:32: epoch 4 done: training loss 0.01679, validation 0.01687; last line: epoch 5  419,430,400 positions  loss 0.01648  452,310/s
- pending `TRAIN-C33F140K16F`
- pending `TRAIN-D15000X60`

**lane A**: 1 running, 5 pending
- running `LONG-SPSA030-ON-040` since 2026-10-14 11:04:55
- pending `LADDER-C33F280-C33F140` (waits for c33f280.nnue)
- pending `LADDER-C33F280-C33` (waits for c33f280.nnue)
- pending `ZONES-C33F140K16F-C33F140` (waits for c33f140k16f.nnue)
- pending `TIMED-C33F140K16F-C33F140` (waits for c33f140k16f.nnue)
- pending `LADDER-D15000X60-D500X60` (waits for d15000x60.nnue)

**lane B**: 1 running, 4 pending
- running `SPSA040-R2` since 2026-10-14 12:11:07
- pending `SPSA040-R3`
- pending `SPSA040-R4`
- pending `SPSA040-R5`
- pending `SPSA040-R6`

## Results in the last 26 hours

| job | finished | W-D-L | Elo | verdict |
|---|---|---|---|---|
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
| `SPRT-C33F140P3-C33F140` | 10-13 18:55 | 446-1123-376 | +13 ± 15 | accepted H1: the change is worth at least 10 Elo |
| `LONG-C33F140P3-C33F140` | 10-13 12:10 | 57-295-48 | +8 ± 34 |  |
| `CONFIRM-C33F140P3-C33F140` | 10-13 10:57 | 262-528-210 | +18 ± 22 |  |

## Search tune (SPSA)

step 7867 of 15000; plus side +3335 =9190 -3169

| constant | default | now |
|---|---|---|
| AspWindow | 25 | 19.8 |
| FutBase | 120 | 114.9 |
| FutMul | 110 | 102.0 |
| IirDepth | 6 | 5.7 |
| LmpBase | 6 | 6.9 |
| LmrBase | 75 | 83.5 |
| LmrDiv | 225 | 219.3 |
| LmrHistDiv | 4096 | 3888.4 |
| NmpBase | 3 | 2.2 |
| NmpDiv | 3 | 2.8 |
| NmpEvalDiv | 200 | 187.7 |
| QsDelta | 200 | 199.2 |
| RfpMargin | 85 | 65.8 |
| SeDepth | 8 | 6.5 |
| SeMargin | 2 | 2.1 |

## Lichess bot

- ratings: bullet 2739 (310 games), blitz 2766 (1066 games), rapid 2802 (35 games)
- last 24 hours: 99 games: 11 W 45 D 43 L; not won against lower-rated: 14; last game started 14 min ago
- 10-12 23:37  ALARM: the lichess bot has played no game for 61 minutes and has no daily limit: restarting it
- 10-13 00:41  ALARM: the lichess bot has played no game for 63 minutes and has no daily limit: restarting it
- 10-13 01:42  ALARM: the lichess bot has played no game for 61 minutes and has no daily limit: restarting it
- 10-13 02:44  ALARM: the lichess bot has played no game for 61 minutes and has no daily limit: restarting it
- 10-14 03:05  ALARM: the lichess bot has played no game for 64 minutes and has no daily limit: restarting it

## Farm and orchestrator (last lines of its log)

```
10-13 18:55  pi-02 starts n15000_pi02_08 (1000000 positions at 15,000 nodes, seed 88308)
10-14 01:05  the GPU queue runner is not running: restarting it
10-14 03:05  ALARM: the lichess bot has played no game for 64 minutes and has no daily limit: restarting it
10-14 05:20  mac finished n15000_mac_08 (4000444 positions): pulled; the 15,000-node set is at 61.7M
10-14 05:20  mac starts n15000_mac_09 (4000000 positions at 15,000 nodes, seed 88109)
10-14 05:22  the 15,000-node set has reached 60M: training D15000X60 and matching it against D500X60
10-14 05:22  queueing TRAIN-D15000X60
10-14 05:22  queueing LADDER-D15000X60-D500X60
10-14 06:36  pi-02 finished n15000_pi02_08 (1000187 positions): pulled; the 15,000-node set is at 62.7M
10-14 06:36  pi-02 starts n15000_pi02_09 (1000000 positions at 15,000 nodes, seed 88309)
10-14 09:09  pi-01 finished n15000_pi01_06 (1000359 positions): pulled; the 15,000-node set is at 63.7M
10-14 09:09  pi-01 starts n15000_pi01_07 (1000000 positions at 15,000 nodes, seed 88207)
```

## Disks

- C 17 GB free of 299
- D 296 GB free of 3001
- E 6832 GB free of 8001

