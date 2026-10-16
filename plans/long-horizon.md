# Long horizon: ideas to remember, not to act on

Things worth coming back to once the current work (`training-data-science.md`) has answers. Nothing here is scheduled. An idea moves out of this file only when the owner says so.

## From the transformer bot (2026-10-05)

The owner played the lichess bot **wadakaoru**, described as a 7M-parameter transformer with MCTS search, rated 2597 blitz over 519 games that day. machete was 2790 blitz with a 4.73M-parameter network, so machete is about 190 points higher on fewer parameters. The comparison that matters is not size but how each spends it:

| | machete (NNUE and alpha-beta) | a transformer with MCTS |
|---|---|---|
| parameters used for one position | about 32 rows of the first layer, updated incrementally | all of them |
| positions searched a second | about 500,000 on a core | hundreds on a CPU, thousands on a GPU |
| strength comes from | a cheap evaluation searched deep | a smart evaluation searched little |
| knows which moves to look at first | no: hand-written ordering | yes: a policy output |

It gets within 200 points of machete on perhaps a thousandth of the search. Three things in that are worth keeping:

1. **A learned move prior.** A policy output is why such an engine can search a small tree. machete has no learned idea of which moves matter, and its known weak spots point the same way: 68% of quiet attacking moves found on the attack suite, and 22 of its 80 costliest lichess moves were ones it finds with more depth. A small policy signal for move ordering (or for which moves to reduce less) is a search experiment that does not wait on any data question.
2. **More computation per evaluation.** machete's network is one layer: features into 768 units and straight out to one of eight outputs. Current alpha-beta networks put two or three small dense layers after the first, so the evaluation can combine features, not only sum them. Never tried here. It costs speed, so it belongs with the faster-evaluation work on Mach 6.10 (256-bit vectors).
3. **The teacher's move as a training target.** Engines of that kind usually learn the outcome (win, draw, loss) and the move a strong engine chose. Our generator records the teacher's score and discards its move. **Recording the move costs nothing at generation time and cannot be recovered afterwards**, so when cloud generation starts, the record format should carry it even though nothing uses it yet. This is the one item here with a deadline attached to someone else's decision.

Not worth taking: the architecture itself. A transformer needs a GPU at play time to compete, and the bot runs on CPU threads.

How wadakaoru was trained is not known to us; the points above are about the class of engine, not a claim about that one.

## Carried over from earlier work

- **Exploit mode**: search quiet attacking moves deeper after the opponent's mistake (`attack-plan.md`, step 2).
- **An attack output in the network**, read only when a gate fires (`attack-plan.md`, step 3).
- **The opening clock**: untested against a booked opponent (`feat/opening-clock`).
- **The Mach GPU trainer**, and AVX2 kernels as plain 256-bit vector code.
- **The Pi self-play league** (`harness/rl/league.py`): built, shelved as a data source because machete's own games are games by a weak player; possibly useful as a judge.
- **The Black repertoire against 1.e4**: no Sicilian beat the Marshall in testing; after 2...Nc6 the field plays the Rossolimo, after 2...d6 the Open Sicilian.
