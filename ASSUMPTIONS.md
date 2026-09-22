# What machete's numbers rest on

Every Elo figure in this repo depends on things that were assumed rather than
measured. This file lists them, says which have since been tested and how, and
keeps the untested ones visible instead of letting them sit inside a result.

A gate proves the code does what it says. This file is for the claims a gate
cannot express: that the measurement means what we think it means.

Status: **measured** - tested, with the test named. **open** - not tested, and
the risk if it is wrong. **retired** - tested and found false; what replaced it.

---

## The instrument

### measured - the SPRT implementation is correct
Simulated over 300 trials at each true Elo, against bounds [0, 10]:

| true Elo | accepts H1 | accepts H0 | median games |
|---|---|---|---|
| +0 | 5% | 95% | 2824 |
| +5 | 46% | 52% | 4212 |
| +20 | 100% | 0% | 1201 |
| -20 | 0% | 100% | 737 |

The 5% false-positive rate at true zero matches alpha exactly. A verdict costs
1,200-2,800 games, which is one to two hours at 200 ms and concurrency 11.

### measured - the tournament's rating fit is unbiased, and its bars are wide
Fitted against known ratings: max error 11.6 Elo at 150 games a pairing, 1.4
at 10,000. The 95% bars cover the truth 98% of the time because they are
**1.19x wider than they need to be** - anchoring the field's mean at zero
removes a degree of freedom the variance formula does not know about. Quoted
as they are. A strict 150-0 ordering fits monotonically; a field of nothing
but draws fits flat to 0.00 Elo.

### measured - a longer clock does not reverse our results
SCALE-01, 180 games per budget against Spike 1.4, Hermann 2.8 and Ruffian
1.0.5:

| | 200 ms | 800 ms | 3200 ms |
|---|---|---|---|
| aggregate score | 0.739 | 0.792 | 0.814 |

Six of six pairwise budget increases went up (sign test p = 0.016). The worry
that a rating measured at 200 ms is inflated on the CCRL 40/15 scale it is
quoted against is falsified, and in the safe direction: if anything 2769 is
conservative.

### measured - four random opening plies give enough variety
5,000 seeded openings produce 4,767 distinct positions; the most repeated
appears three times and the ten commonest cover 0.5% of draws. Openings are
not quietly narrowing the sample.

### measured - the 300-ply cap does not favour a side
3.3% of games reach the cap and are scored as draws regardless of the position
on the board. Both engines are equally subject to it, so it inflates the draw
rate - widening error bars - rather than shifting the estimate. Worth
revisiting if the rate climbs at longer time controls.

### open - that net-vs-net ranking at 200 ms holds at tournament time controls
SCALE-01 tested machete against *external* engines. It did not test whether
one of our networks that beats another at 200 ms still beats it at 3200 ms. An
evaluation advantage can saturate with depth even when the engine as a whole
gains. **If wrong:** the subset tournament ranks the wrong data. Cheap partial
check: re-run the top two finishers at 3200 ms.

### open - that results taken on a busy machine are comparable
An orphaned match once held four cores and put every nps figure 20% low.
Time-based paired matches should be robust, because load slows both sides
equally, but this has never been tested directly. **If wrong:** results from
different sessions cannot be pooled. Cheap check: run one A/B twice, idle and
under artificial load, and compare.

---

## The network and its training

### measured - dropping the game-result term is right
Re-swept on the cleaned corpus after contamination fell from 7.3% to 2.9%:
blend 0.9 scored -10 +/- 34 and blend 0.8 scored -43 +/- 34 against blend 1.0.
The prediction on record - that a cleaner corpus would make the result term
valuable again and push the optimum below 1.0 - is **wrong**. Pure search
score stays best.

### measured - colour-swap augmentation is a no-op
Provably, not statistically: the gap is exactly 0.

### retired - that mirroring is a label-preserving symmetry
Falsified. It is not safe, and the augmentation built on it was removed.

### open - that 14 epochs is the right length
Validation loss falls monotonically through epoch 14 and is still falling
(0.01720 to 0.01717 on the last step). We are stopping early, not overfitting.
But the learning rate decays by 0.8 each epoch, so by epoch 14 it is 5.5% of
its initial value: **epoch count and learning-rate schedule are entangled**,
and neither has been varied alone. **If wrong:** every network in every
experiment is undertrained by the same amount, which biases comparisons less
than it biases the absolute rating.

### open - that HIDDEN = 256 is a sensible width
Never varied. **If wrong:** the ceiling on every data experiment is the
architecture, not the data, and the tournament is measuring the wrong thing.

### open - that scale 150 is optimal on the current corpus
Measured +68 +/- 35 on the **old 12M** corpus and carried forward to the 42M
one without re-testing. The corpus has since changed twice. **If wrong:** a
mis-scaled target costs Elo on every network trained since.

### open - that typical quantization headroom is safe
The extremes are now gated in both signs. The typical case reports "worst
accumulator N of 32767" - 2,126 to 7,143 across recent runs - but nothing
fails if that number approaches the limit. **If wrong:** a future wider or
longer-trained network silently saturates. A gate on this is cheap and owed.

---

## The data

### open - which positions are worth training on
The question the subset tournament exists to answer. Held-out loss cannot
answer it: `balanced` reports a validation loss of 0.00723 against `uniform`'s
0.01717, not because it is a better corpus but because near-zero positions are
trivial to predict on their own held-out slice. Every subset scores well on
itself. Only games escape the circle.

### open - that five teachers and book openings each helped
Both were changed together, along with the corpus growth, in the +157 +/- 38
bundle. Neither has been isolated. The tournament's `solo` and `spread` cuts
separate the teacher half of it.

### open - that 1500 nodes per label is enough teacher depth
Never swept. The external-corpus result (-159 Elo against a deeper but less
consistent corpus) hints that consistency matters more than depth, but that is
an inference from one comparison, not a measurement of this parameter.

### open - that RANDOM_MOVE_CHANCE = 0.02 is right
Inherited. Never varied.

---

## The search

### in progress - continuation history
Measured +4 +/- 34, which resolves nothing. Under SPRT now against bounds
[0, 10]. The ablation is exact - `cont_slot` returning -1 disables both the
read and the update - and the two binaries differ in bench node count
(165,161 with, 158,026 without), so the A/B is real.

Its commit also left `fixtures/bench.expected` holding the old count, so the
gate that exists to notice an accidental search change was red and silent from
that commit until it was found.

### open - the corpus rebalance
Measured +23 +/- 34. SPRT owed.

### open - every pruning constant
NMP 3 + depth/3, LMR 0.75 + ln(d)ln(m+1)/2.25, LMP 6 + depth^2, RFP 85*depth,
futility 120 + 110*depth. All inherited from published engines and never tuned
against this engine's evaluation. **If wrong:** the single largest untapped
source of Elo, and the one most likely to interact with the network - a
different evaluation wants different margins.

---

## How this list is used

Six of the last seven measured changes came back sub-threshold: +4, +23, -1,
-10, +17, -43. At 400 games a match the instrument can no longer resolve what
is being changed. That is why the entries above are worth more than another
400-game A/B: an assumption that is wrong is worth tens of Elo, and finding
one costs a few minutes of arithmetic rather than hours of games.

Add to it whenever a number is carried forward without being re-measured.
