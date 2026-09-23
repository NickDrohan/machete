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

### retired - that a rating-ladder anchor was running multi-threaded
LADDER-02 reported 2928 +/- 78 with chi2/dof 1.59, and Rybka 2.3.2a sat low at
2809. It was blamed on Rybka's multi-processor build, whose `Max CPUs` option
defaults to 2048, and a figure of 2963 +/- 65 was quoted without it. Both are
withdrawn. Measured: Rybka runs 3 threads idle and 3 throughout a timed search
on this 24-CPU machine - one search thread. The disagreement was not significant
(chi2 9.5 on 6 degrees of freedom, p = 0.15), and dropping the largest outlier
always lowers chi2, so that "confirmation" could not have failed. 2928 +/- 78
stands. The lesson is recorded as rule 18 in ROADMAP_3500.md.

### open - that net-vs-net ranking at 200 ms holds at tournament time controls
SCALE-01 tested machete against *external* engines. It did not test whether
one of our networks that beats another at 200 ms still beats it at 3200 ms. An
evaluation advantage can saturate with depth even when the engine as a whole
gains. **If wrong:** the subset tournament ranks the wrong data. Cheap partial
check: re-run the top two finishers at 3200 ms.

### measured - absolute throughput is uninterpretable without the machine state
The same gate, the same binary, three times in one afternoon:

| machine | 1-thread nps |
|---|---|
| 11-game tournament running | 428,950 |
| tournament finished, ten orphaned harness processes alive | 541,676 |
| after clearing them | 769,675 |

A 79% spread with no code change. **No nps figure means anything unless what
else was running is recorded next to it.** Any two speed numbers in this repo
taken in different sessions should be assumed incomparable.

### open - that *paired* results on a busy machine are still comparable
The above is about absolute throughput. The separate and still-untested claim
is that an A/B *Elo* measurement survives load, because a time-based match
slows both sides equally and a score is a ratio. That is the assumption every
pooled Elo figure here rests on, and it is the one that actually matters.
**If wrong:** results from different sessions cannot be pooled at all. Cheap
check: run one A/B twice, idle and under artificial load, and compare - now
cheaper than before, since the load can simply be a second copy of the match.

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

### measured - quantization headroom is enforced when we train a network
This entry was first written claiming nothing fails as the accumulator
approaches the limit. That was wrong. `train.py`'s `export()` refuses to write
at all: it checks every array against int16 and bounds the accumulator by the
bias plus the 32 largest weights in any hidden unit, 32 being the most pieces
a position can have. Perturbed to confirm the refusal fires rather than being
decorative - a hidden unit whose 32 largest weights reach 24,498 is written,
36,755 is refused, and a single weight past int16 is refused separately.
Recent real networks land between 2,126 and 7,143, roughly a quarter of the
budget.

### open - that a network we did not train would be caught
The bound above lives in the trainer. `nn.load` accepts any file of the right
shape, so a network converted from elsewhere, or hand-built, would saturate
silently. Low risk while we only ever load our own, and worth a gate if that
stops being true.

---

## The data

### measured - breadth beats every slice we know how to cut
Seven networks, one per cut, 8,000,000 positions each, trained identically,
4,200 games all-play-all at 200 ms:

| network | score | Elo | trained on |
|---|---|---|---|
| control | 0.754 | +245 +/- 27 | *the same file as uniform* |
| spread | 0.752 | +244 +/- 27 | 1.6M from each of 5 teachers |
| uniform | 0.743 | +234 +/- 27 | random 8M of all 42.2M |
| solo | 0.717 | +210 +/- 28 | Stockfish only |
| decided | 0.396 | -86 +/- 34 | \|score\| >= 400 |
| opening | 0.345 | -136 +/- 35 | >= 25 pieces |
| endgame | 0.157 | -342 +/- 35 | <= 12 pieces |
| balanced | 0.137 | -368 +/- 35 | \|score\| <= 150 |

**The control validates the instrument.** `uniform` and `control` are
byte-identical networks entered twice. Head to head they scored 0.493 over 150
games and their fitted ratings differ by 11 Elo, so the noise floor is about
11 and the 600-Elo spread below it is not an artifact.

**Held-out loss is anti-correlated with strength.** `balanced` has the best
validation loss in the field - 0.00723 against `uniform`'s 0.01717, 2.4x
better - and finishes 602 Elo behind it. Near-zero positions are trivial to
predict on their own slice. This is the circularity demonstrated rather than
argued, and it is the reason this tournament exists.

**A corpus of only close positions is the worst of all**, below even the
endgame-only cut that has never seen an opening. The mechanism is visible in
the ordering: `decided` at -86 is 282 Elo above `balanced`, so knowing which
positions are won matters far more than fine discrimination near zero. A
network that only ever saw |score| <= 150 cannot tell +200 from +800 and has
nothing to steer toward.

No slice beat uniform sampling. If a subset exists that would make a
world-class engine, it is not selectable by score band or by game phase - the
two most natural axes, both now closed.

### open - that five teachers and book openings each helped
Both were changed together, along with the corpus growth, in the +157 +/- 38
bundle. The tournament separated the teacher half: pooling the three diverse
networks against `solo` gives **+37 +/- 32 over 450 games**, with all three
head-to-heads pointing the same way (+21, +44, +47). It excludes zero, but
`uniform` and `control` are the same network so those samples are correlated -
directionally supported, not established. `spread` and `uniform` finish inside
the noise floor of each other, so five teachers helps against one while
*equalising their shares* adds nothing.

Book openings remain unisolated.

### open - that 1500 nodes per label is enough teacher depth
Never swept. The external-corpus result (-159 Elo against a deeper but less
consistent corpus) hints that consistency matters more than depth, but that is
an inference from one comparison, not a measurement of this parameter.

### open - that RANDOM_MOVE_CHANCE = 0.02 is right
Inherited. Never varied.

---

## The endgame

### measured - won endgames are not reliably converted
Found by watching a game, not by a gate. Over 1,884 games of the current
self-play SPRT, **80 ended in a draw with one side a rook or more ahead** -
59 by the fifty-move rule, 21 by repetition. A further 33 were cut by our own
300-ply cap, which is a harness artifact and counted separately.

Reproduced directly, engine against itself at 500 ms a move:

| forced win | result |
|---|---|
| KQ v K | mated in 15 plies |
| KR v K | mated in 59 plies (optimal is 31) |
| KQ v KN | **drawn, fifty-move** |
| KBB v K | **drawn, fifty-move** |

The pattern is that it converts when mate is inside the search horizon and
fails when the win needs a plan with no material change - driving a king to a
corner, or winning the knight before mating.

**It is not a search bug.** From KQ v K at depth 18 it finds mate in 9. **It is
not corpus coverage** either: 701,505 positions have four pieces or fewer and a
queen-or-more edge. It is the absence of any evaluation gradient inside a won
position, from two causes that compound:

1. **The training target saturates.** With scale 150 the target is
   `sigmoid(score/150)`: +700 gives 0.9907, +1500 gives 0.99995, a clamped mate
   gives 1.0. The MSE gradient between "a queen up and shuffling" and "mate in
   three" is about 0.00009, so the network is never asked to tell them apart.
   Measured: it evaluates KQ v K at **+551** and KR v K at **+373**, and those
   barely move between depth 4 and depth 14.
2. **There is no classical fallback.** `eval.mach` is material, piece-square
   and pawn terms - no corner or edge-driving term, no mate-distance pruning -
   and with a network loaded the classical evaluation is not consulted anyway.

Worth roughly 4.2% of games at stake, so on the order of 15 Elo in a balanced
field and more against weaker opponents, where winning endgames arrive often.

Two independent fixes, one per side of the handoff:

* **Data (harness).** `gen.py` adjudicates at +/-1500, so a game *stops* once it
  is decisively won. Conversion technique is therefore absent from the corpus
  by construction - the positions exist, but the sequences where a king is
  driven to the edge do not. Generating from won endgame positions with
  adjudication off would put them there.
* **Evaluation (Mach).** The classical answer: a corner and edge-driving term
  plus king proximity, active when the material is a known win, and
  mate-distance pruning in the search.

### open - whether a less saturated target costs middlegame Elo
Scale 400 to 150 measured +68 +/- 35 on the old 12M corpus. If the endgame
failure above is the cost of that gain, the tradeoff has never been measured as
a tradeoff - only the middlegame half of it was.

---

## The search

### measured - continuation history does not earn its place
SPRT-01 against bounds [0, 10] accepted H0 over 1,884 games: 500-852-532,
**-6 +/- 16**. It also searches 4.5% more nodes to reach depth 8 (165,161
against 158,026). Removing it is ROADMAP_3500.md S-01; `fixtures/bench.expected`
returns to 158,026 in the same commit.

A first SPRT had been stopped at 1,060 games for the machine rather than for
its data, at -5.6 +/- 21 with the LLR walking back from -2.16 - the signature
of a true value inside the bounds. The second, run to a verdict, is the one
that counts. Its predecessor's commit had also left the bench fixture stale,
so the gate meant to notice a search change was silent until it was found.

### open - the corpus rebalance
Measured +23 +/- 34. SPRT-02 is queued in `harness/longqueue.sh`.

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
