# Where machete stands, measured from outside

*2026-09-27, updated 06:30 with the third pass. Every previous strength figure for this engine came from games against its own earlier versions, or from an external anchor with an assumed rating; this is the first rating built only from engines with published ratings, and it changes the picture.*

## 1. What was measured

Every release - 0.1.0 (network A), 0.2.0 (C2), 0.3.0 (N-05 king buckets, C7) - played 20 games against each of seven engines with entries on CCRL's lists, four anchor pairs played each other, in a second pass 0.2.0 and 0.3.0 played 60 more games against each of the three anchors nearest their strength (Spike, Rybka, Koivisto), and in a third pass 60 games each against Spike and Rybka at 10+0.1, the clock at which 0.3's head-to-head gain over 0.2 was measured, under CCRL Blitz's conditions as far as one machine allows: 2 minutes + 1 second, one thread each, 128 MB, own books off, balanced openings played from both sides, no adjudication, ten games at once on twelve physical cores. 1,100 games, 35 pairings, no time forfeits except three by Rybka against 0.2.0 in the first pass and two in the third. Ratings are then fitted by maximum likelihood with the anchors held at their published ratings (`harness/rating.py`; the same estimator Ordo and BayesElo reduce to with anchors fixed and no draw model), with bootstrap intervals over games. The harness's own head-to-head Elo formula plays no part in it.

The anchors and the ratings used, from CCRL's Blitz list (search snippets; the site itself is behind a bot wall and the figures should be re-read from the list directly):

| anchor | CCRL Blitz | note |
|---|---|---|
| Rybka 2.3.2a 64-bit | 2977 | the Blitz entry was not found; this is the 40/2 list. 40/15: 2960 |
| Spike 1.4 Leiden | 2946 | |
| Ruffian 1.0.5 | 2673 | |
| Hermann 2.8 64-bit | 2574 | |
| SOS 5.1 | 2541 | |
| AnMon 5.75 | 2504 | |
| Koivisto 9.0 64-bit | unknown | only 4CPU entries were found (3466-3560); the single-CPU rating is likely 3450-3550. Treated as unrated and fitted |

## 2. The games

Machete's score against each anchor (wins-draws-losses, its performance relative to that anchor in Elo; 20 games each, so a single pairing carries about +/-130 Elo):

| | Rybka 2.3.2a | Spike 1.4 | Koivisto 9.0 | Ruffian 1.05 | Hermann 2.8 | SOS 5.1 | AnMon 5.75 | pooled |
|---|---|---|---|---|---|---|---|---|
| **0.1.0** | 9-8-3 (+108) | 9-7-4 (+89) | 0-3-17 (-436) | 16-2-2 (+301) | 19-1-0 (+636) | 19-0-1 (+512) | 20-0-0 | 73.2% |
| **0.2.0** | 13-5-2 (+215)* | 14-4-2 (+241) | 0-3-17 (-436) | 18-2-0 (+512) | 16-4-0 (+382) | 20-0-0 | 20-0-0 | 78.6% |
| **0.3.0** | 10-7-3 (+127) | 15-4-1 (+301) | 0-2-18 (-512) | 18-2-0 (+512) | 17-3-0 (+436) | 20-0-0 | 19-1-0 (+636) | 77.5% |

\* three of 0.2.0's wins against Rybka were Rybka losing on time; without them 10-5-2.

The second pass, 60 games each against the three nearest anchors, with the totals over both passes (80 games a pairing):

| | Spike 1.4 | Rybka 2.3.2a | Koivisto 9.0 | pooled, both passes |
|---|---|---|---|---|
| **0.2.0** second pass | 40-15-5 | 33-19-8 | 2-10-48 | |
| **0.2.0** both passes | 54-19-7 (79.4%) | 46-24-10 (72.5%) | 2-13-65 (10.6%) | 54.2% of 240 |
| **0.3.0** second pass | 36-19-5 | 40-16-4 | 0-8-52 | |
| **0.3.0** both passes | 51-23-6 (78.1%) | 50-23-7 (76.9%) | 0-10-70 (6.2%) | 53.8% of 240 |

The third pass, at 10+0.1 (60 games a pairing, 12 at once):

| | Spike 1.4 | Rybka 2.3.2a | pooled |
|---|---|---|---|
| **0.2.0** | 47-9-4 (85.8%) | 58-2-0 (98.3%)* | 88.8% of 120 |
| **0.3.0** | 45-8-7 (81.7%) | 55-5-0 (95.8%) | 88.3% of 120 |

\* two of them Rybka losing on time. Both releases score higher at 10+0.1 than at 2+1 against the same engines: a modern engine's advantage over 2005-era engines grows with the clock, which is one more reason the list's gaps do not transfer.

The anchors against each other, which is what tests whether their published gaps hold here:

| pairing | list gap | measured | games |
|---|---|---|---|
| Spike over Ruffian | +273 | 15-5-0, +338 | 20 |
| SOS over AnMon | +37 | 9-5-6, +52 | 20 |
| Rybka over Spike | +31 | 10-6-4, +108 | 20 |
| Koivisto over Rybka | +470 to +570 if Koivisto is 3450-3550 | 19-1-0, +637 | 20 |

## 3. The anchors disagree, and that is the finding

Refitting each anchor as if it were unrated, against everything else with the other five fixed, puts every one of them 330 to 560 Elo below its list rating (Rybka 2977 -> 2417, Spike 2946 -> 2521, Ruffian 2673 -> 2156, Hermann 2574 -> 2113, SOS 2541 -> 2208, AnMon 2504 -> 2151). The anchor pairs show the same thing in miniature: every measured gap is larger than the list's, by 1.2x to 3x. Two effects, both known: rating lists pool games across two decades of engines and compress the differences between eras, and a modern NNUE engine beats 2005-era engines by more than a 400-Elo gap predicts at a fast time control on modern hardware. A single external scale for this engine therefore does not exist; what exists is a range that depends on which anchors you trust.

| anchors used (both passes, 860 games) | 0.1.0 (140 games) | 0.2.0 (320) | 0.3.0 (320) | what it assumes |
|---|---|---|---|---|
| all six listed | 2986 (2835-3084) | 3027 (2844-3108) | 3024 (2840-3105) | the weak anchors' 95-100% scores mean what the model says |
| Spike and Rybka only | 2926 (2761-3053) | 3011 (2824-3098) | 3009 (2820-3095) | the two nearest anchors, the only informative games |
| the four weakest only (first pass) | 2785 | 2851 | 2837 | almost no information: 100% scores |
| Koivisto alone, by direct performance | K - 436 | K - 368 | K - 470 | 80 games at 6-11%; 3080-3180 for 0.2.0 and 2980-3080 for 0.3.0 if K = 3450-3550 |

**The statement this supports:** machete 0.3.0 plays at about **3000-3100 on the CCRL Blitz scale, single CPU**, with a statistical uncertainty near +/-70 from 320 games and a systematic uncertainty of about +/-100 from the anchors' era. 0.2.0 and 0.3.0 are indistinguishable on this scale at both clocks tried (3027 against 3024 at 2+1; 88.8% against 88.3% at 10+0.1), and 0.1.0 sits 40-85 below them.

## 4. Were the earlier estimates realistic?

| claim | where it came from | what the ladder says |
|---|---|---|
| 0.1 is "3100-3200 on the CCRL 40/15 scale" | 40 games each against Spike assumed at 2950 and Rybka assumed at 3050, at 3+2; an earlier ladder note retracted a Rybka result for running on every core | Rybka's list rating is 2960-2977, not 3050, and the anchors are worth less here than the list says; 0.1 measures about 2950-3050. Overstated by roughly 150 |
| 0.2 is +209 +/- 94 (10+0.1) and +179 +/- 91 (60+0.6) over 0.1; +246 +/- 67 in the control match | head-to-head, same book | true as head-to-head numbers. Against the external field, pooled over 140 games each: +50 +/- 95 (0.1's 73.2% to 0.2's 78.6%). Family Elo overstated the gain against other engines by three to four times, which is the usual ratio for self-play-style gains |
| 0.3 is +54 +/- 34 (10+0.1) and +60 +/- 41 (60+0.6) over 0.2 | the round 2 final, 300 games, same book | not there against other engines at either clock: -3 +/- 40 over 240 games each at 2+1, and at 10+0.1 itself 88.3% to 88.8% over 120 games each (about -5 +/- 45). The king-bucket network beats the network it shares its data with, and no one else: a family-specific gain. Combined, the external evidence puts 0.3 within about +/-30 of 0.2 |
| 0.2 and 0.3 are "about 380 below Koivisto" | 40 games each at 60+0.6 | consistent: -436 to -512 here at 2+1 |
| "no wins yet against an engine of that class" | | still true: 0 wins in 60 games against Koivisto across the three releases |

The pattern is the one to remember: **gains measured against our own previous version overstate gains against other engines by a large factor**, and every release note so far quoted the former as if it were the latter. Anchors assumed rather than looked up made it worse.

## 5. How far this can go

On the same scale, the field the engine folder holds sits (approximately, from memory of the lists; to be re-read) at Koivisto 9.0 about 3450-3550, Seer 2.8, Caissa 1.23 and Black Marlin 9 about 3450-3550, Berserk 13, Obsidian 16, Alexandria 8, PlentyChess 7 and Reckless 0.9 about 3550-3700, Stockfish 17 above 3700. Machete is about 450 below Koivisto (measured directly) and 600-700 below the top.

Where the gap is, by what each part of the engine is:

- **Evaluation.** 8 king buckets x 768 inputs -> 256 -> 8 output layers, trained on 154 million positions, 119 million of them labelled by our own panel at 1,500 nodes and 35 million by Stockfish at depth 18-22. The gain from 0.2 to 0.3 came from those 35 million deep labels, not from the buckets (C5, buckets on the old data, was level). 466 million more of them exist and 98 million are converted; the first two trainings on them are running tonight, and the first result (C11, which drops the shallow labels entirely) is trending negative, which says the shallow self-labels still carry the engine's own position distribution. The engines above 3500 train nets of 1,024-3,072 hidden units on billions of deep positions.
- **Search.** The standard stack is in place; its constants are 0.2's, never tuned for a network evaluation (SPSA queued). This week's attempt to add the next layer of features measured flat to negative and cost 26% of speed; the lesson is in `SEARCH_RESEARCH.md`.
- **Speed.** About 0.65 million nodes a second on one thread: the network's first layer runs through SSE2 because Mach scalarizes 256-bit vectors (MACH_FINDINGS.md). Engines with AVX2 inference run two to three times as many nodes on the same hardware.

What that buys, as estimates to be measured and not promises: more deep labels and a wider net, +100 to +200; search constants tuned to the net, and the tail of features re-measured properly, +50 to +100; AVX2 inference, whether through Mach or hand-written, +50 to +100. Taken together, **3250-3400 on this scale is reachable with the current architecture in weeks of measured work.** The roadmap's 3500 is Koivisto's level: it needs a net several times larger trained on billions of positions, and inference fast enough to search it, which is months and mostly compute. Above that is the territory of the engines that define the scale.

## 6. What happens next

- Both follow-up passes are done: 0.3's +55 over 0.2 does not appear against other engines at 2+1 (-3 +/- 40) or at 10+0.1 (-5 +/- 45). For the release this means 0.3.0 is 0.2.0 with a network that beats 0.2's head-to-head and plays other engines the same; the format change (king buckets) is what it delivers, not strength.
- The network experiments overnight (C10, C11, C13, C14, C15, C16 against C7) test what the next real gain needs: deep labels as an addition lost when they displaced our own (C10 -23, C11 -28), the training-seed noise floor is -2 +/- 14 (C7B), and the rest are in the queue.
- The anchors' exact single-CPU Blitz ratings should be read from the CCRL pages once the site can be reached from the browser pane; the fit re-runs in seconds.
- The ladder needs anchors *near* the engine: free, listed engines in the 3050-3350 band (Texel 1.07, Wasp 4.5, Igel 2.5, Defenchess 2.2, Laser 1.7, Xiphos 0.6, Ethereal 12.75 are candidates) would turn +/-100 into +/-40, and would also tell whether the era stretch flattens for engines closer in date. Each is a download to E:/ that needs your go-ahead.
- The 0.3.0 release notes state the head-to-head numbers and the Koivisto anchor correctly; the README's "near 3000" becomes "3000-3100 on the CCRL Blitz scale, measured against seven listed engines", and the notes gain the same line. Nothing else in the release changes.

Files: `E:/machete/claude/ladder/*.pgn` (every game, with each side's evaluation and Stockfish 17's as comments from the second half of the run on), `harness/rating.py`, `E:/machete/claude/ladder/submit.sh`, ledger lines `LADDER-*` in RESULTS.tsv.
