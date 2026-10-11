# What makes a good training game: a research plan (2026-10-05)

Nothing in this plan is queued. It is a plan for the owner to cut, reorder and approve batch by batch.

## Why this plan exists

The goal is rating on lichess against a field that is mostly stronger than machete. The chunk catalog says where the last month's data work went: the foundation corpus matters (removing or halving it costs 28 to 54 Elo), and nearly everything added since is inside the noise of one training run (about ±6 Elo). We have been adding chunks without knowing which property of a chunk moves strength. This plan is to find out.

Two things I proposed this week were wrong by the project's own records, and this plan corrects them:

- **Self-play by machete as the data source.** The owner's objection is right: games by a weak player teach weak play. Every chunk that helped was played and labelled by engines far stronger than machete.
- **A 0.7 search / 0.3 result target in the league.** `ASSUMPTIONS.md` records this as measured twice: pure search score beats any blend with the game result (blend 0.9: −10 ± 34; 0.8: −43 ± 34; 0.7 lost by 108). I set 0.7 without checking.

## Why 1,500 nodes? Nobody knows

`ASSUMPTIONS.md` lists it as **open: "that 1500 nodes per label is enough teacher depth. Never swept."** It was inherited from the first generator and kept because it was cheap. The only evidence near it is indirect and confounded: the theoden8 positions (labels at depth 18 and more, from human games) lost to the 1,500-node generator positions, which could be depth, or the positions, or the mix of teachers.

What the number trades:

| nodes per label | positions per worker-second (PC, Stockfish) | what it buys |
|---|---|---|
| 500 | about 300 | 3× the positions; labels that miss three-move tactics |
| **1,500** | about 110 | where we are |
| 5,000 | about 35 | labels about 2 plies deeper |
| 15,000 | about 12 | labels about 4 plies deeper; a tenth of the positions |

The rates for 500, 5,000 and 15,000 are scaled from the measured 1,500 figure, not measured. Two different questions hide in "the right number", and the sweep must ask both: at **equal positions**, do deeper labels make a stronger network (label quality)? At **equal compute**, is it better to have 10M deep labels or 100M shallow ones (the question that decides what the farm does)?

## The levers on a chunk

A chunk is the result of nine decisions. The table says what each is set to today and what the records say about it.

| # | lever | today | what is known |
|---|---|---|---|
| 1 | **Who plays the moves** | Stockfish 19 against itself (recent chunks); five engines in turn (the foundation) | five teachers beat one by +37 ± 32 on 8M-position networks; equalising their shares added nothing. Suggestive, not settled |
| 2 | **Who scores the positions** | whoever played | never separated from lever 1 |
| 3 | **How deep the score is** | 1,500 nodes | never swept |
| 4 | **Where games start** | a broad book; repertoire, attack, Kalashnikov and Fischer Random books in single chunks | broad +16 once then nothing; repertoire +10 ± 8; narrow opening and attack: no gain |
| 5 | **How games vary** | 5% of moves are a near-best alternative; 2% random earlier | "four random opening plies give enough variety" is measured; the rest is inherited |
| 6 | **When games stop** | adjudicated at ±1,500 for six plies; 300-ply cap | known to remove conversion technique from the data by construction (won endgames: 4.2% of games at stake) |
| 7 | **Which positions are kept** | every position not in check, first occurrence | "breadth beats every slice": score-band and phase subsets all lost to uniform, by up to 600 Elo |
| 8 | **How the target is built** | sigmoid(score/150), no result term | result term: measured, pure score wins. Scale 150: measured on a 12M corpus, carried forward untested through two corpus changes |
| 9 | **How much, and at what weight** | whatever was generated, listed once | attack games at 6.5% of the mix cost 18 Elo; at 2% undecided |

Training itself has two more that are tangled together (epochs and learning-rate decay) and one that caps everything (width). They are in batch 4, after the data levers, because a data result measured on an undertrained network is still a fair comparison.

## The teachers on this machine

| engine | kind | role proposed |
|---|---|---|
| Stockfish 19 | alpha-beta, NNUE; the strongest here | the reference labeller; plays in every mix |
| Leela 0.32.1 (network 791556) | MCTS, runs on the GPU | the different voice: positional, long-term compensation. Its nodes are not comparable to the others' |
| Alexandria 9.0, Obsidian 16, PlentyChess, Reckless 0.9, Berserk, Caissa | alpha-beta, NNUE, all far above machete | the mix: different evaluations of the same positions |
| Seer, BlackMarlin, Koivisto | alpha-beta, NNUE, a tier down | reserve, for a weaker-defender arm (below) |
| Dragon | commercial | not proposed without the owner's say |

Two findings already in the corpus shape the mix. Leela's 60M positions are 73% within a pawn of level and 54% drawn games; the foundation is 31% within a pawn and 31% decided by six pawns or more. "A corpus of only close positions is the worst of all" (−368 Elo for the balanced-only cut): **Leela's games alone would starve the network of decided positions**, so Leela belongs in a mix as a minority, or as a labeller of positions other engines reached.

The arms worth testing (batch 2):

- **A. Stockfish 19 alone**, self-play: the control, what recent chunks are.
- **B. Six alpha-beta teachers, each against itself**, equal shares: the foundation's recipe with current engines.
- **C. The same six, playing each other** (round robin, not self-play): more decisive games, positions where two different evaluations disagreed.
- **D. C's games, every position re-scored by Stockfish 19**: separates lever 1 from lever 2. If D beats C, one consistent scorer matters more than diverse scorers.
- **E. C plus 15% Leela games** (Leela against the alpha-beta engines): does the different voice add anything.
- **F. A strong teacher against a weaker defender** (Stockfish against Koivisto-class), played to mate: games where one side wins and shows how. This is the conversion and attack data we tried to get with special books, obtained from who plays instead of where the game starts.

Arm F is the one aimed at lichess: machete's draws against weaker bots are level games it never unbalanced, and its losses are slow middlegame defeats. Neither is in the data when two equal engines draw each other.

## The instrument: small networks, many arms, a duplicated control

A full network (364M positions, 3.5 GPU-hours, then a 2-hour SPRT) can test one idea a day and cannot resolve less than about 10 Elo. `ASSUMPTIONS.md` already holds a better instrument, used once: **seven networks of 8M positions each, trained identically, 4,200 games all-play-all, with one network entered twice** to measure the noise floor (11 Elo there, against a 600-Elo spread).

The plan is to make that the standard:

- an arm is a **10M-position chunk** made with one lever changed;
- every arm trains a network alone, from scratch, same seed, same recipe (a 768-wide network on 10M positions trains in about 15 minutes);
- the arms and a duplicated control play all-play-all, plus the full-Stockfish gauntlet and the Stockfish-approval yardstick;
- **a winner is then confirmed at full scale**: added to the current recipe, SPRT against C33, packaged head-to-head, two seeds. Small-network results do not always transfer, and the confirmation is where that is caught.

Each arm is a chunk in the catalog with its nine lever settings recorded, and each tournament is rows in the chunk ledger.

## The batches

| batch | question | arms | generation, in PC-core-hours |
|---|---|---|---|
| **0. Instrument** | does the small-network tournament reproduce on today's stack, and what is its noise floor? How fast are Leela and the other teachers? What does a cloud core do? | control ×2 from an existing chunk; timing runs | about 40, mostly existing data |
| **1. Depth** | lever 3: is 1,500 nodes right? | 500 / 1,500 / 5,000 / 15,000 nodes at equal positions (10M each); and 30M at 500 against 10M at 1,500 against 3M at 5,000 at equal compute | about 600 |
| **2. Teachers** | levers 1 and 2: who plays, who scores | arms A to F above, 10M each | about 300, plus Leela on the PC's GPU |
| **3. Game shape** | levers 5, 6, 7 | adjudication off (play to mate) against ±1,500; variety 0 / 5% / 15%; one position in three kept against all | about 240 |
| **4. Target and training** | lever 8 and the training tangle | scale 100 / 150 / 220; a win-draw-loss-aware target; epochs and decay varied separately | none; GPU only |
| **5. Scale-up** | does the best recipe, at 2 million games, beat C33? | one chunk of about 240M positions; SPRT, packaged match, two seeds, then lichess | about 600 at 1,500 nodes; 3× that at 5,000 |

A PC-core-hour is one generator worker on the PC for an hour: about 400,000 Stockfish positions at 1,500 nodes (measured: 110 a second).

Batches 1 and 2 are independent and can run in either order; 3 should use the depth and teachers they choose; 5 uses everything. Batch 4 needs no generation and can fill GPU time between the others. Where starts (lever 4) and weights (lever 9) are deliberately not in this round: the catalog already has several readings on them, and they interact with the repertoire decision.

## Compute: where each part runs

The PC's 20 workers are not free: Cursor's generator holds them, the lichess bot takes 8 threads, and matches played on the loaded machine lost up to 73% of games on time on 2026-10-04. Kamatera has approved the owner's quota request (against a $450 prepayment, the owner's decision). The plan below uses cloud CPU for the two things it suits and keeps everything else at home.

| work | where | why |
|---|---|---|
| **Generation** (batches 1, 2, 3, 5) | cloud | CPU-bound, splits across machines, needs only public things: the generator, open-source engines, opening books. A search is a fixed node count, so a slower or noisier core changes the rate, not the data |
| **Arm tournaments and SPRTs** | cloud, on machines doing nothing else | the cleanest fix for the time-forfeit problem; needs a check that cloud cores keep steady time (below) |
| **Training, Leela** | the PC's GPU | the corpora (26 GB) and the card are here |
| **The lichess bot, the Pis, the mate search** | as now | unchanged |

**What goes on a cloud machine:** the generator and match-runner binaries (built here for linux-x86_64), teacher engines built there from their public sources, opening books, and a public ssh key. **What never does:** the lichess token, any GitHub credential, the Kamatera API keys, the training corpora. The PC pulls results over ssh; the cloud machines never reach into the PC. The owner creates and destroys the servers in Kamatera's console; I work on them over ssh with a key made for the purpose.

**Budget.** The whole programme is about 1,800 PC-core-hours of generation (batches 0 to 3 and 5 at 1,500 nodes), plus tournaments. What that costs depends on two numbers we do not have yet: Kamatera's price for a core-hour on the server type the quota allows, and how fast such a core is against the PC's. So the first cloud step is a one-hour pilot on one server: build Stockfish and the generator, run 1,500-node generation and a timed match, and record **positions per dollar** and **time forfeits per 100 games**. Then the batches are sized to the $450 with a reserve, rather than discovered to exceed it.

| if a cloud core is | and costs | then 1,800 PC-core-hours cost about |
|---|---|---|
| 0.6 of a PC core | $0.02 an hour | $60 |
| 0.6 of a PC core | $0.05 an hour | $150 |
| 0.4 of a PC core | $0.08 an hour | $360 |

These rows are arithmetic on assumed prices, not quotes. **Guard rails:** the email says usage past the prepaid amount is charged automatically, so every batch gets a spending line written before it starts, servers are destroyed (not just stopped) when their batch is pulled and verified, and a running ledger of server-hours is kept beside the chunk ledger.

**If batch 1 says deeper labels win**, the cloud is what makes that affordable: 5,000-node labels cost 3.3× and would put the 2-million-game chunk out of the PC's reach but inside the budget at the cheaper prices above.

## How a network is judged

Self-play Elo between machete's own networks overstates gains against other engines by three or four times (`ASSESSMENT.md`). Every arm and every confirmed network gets the same panel:

1. the arm tournament or SPRT (family Elo: for ranking arms, not for claims);
2. **score against full Stockfish 19** from the balanced book (16% today): the external yardstick the owner chose;
3. **Stockfish approval**: on a fixed set of positions from machete's lichess games, how often the network's move is Stockfish's first choice or in its top three, and what it gives up;
4. the attack suite (74.5% today; 68% of quiet moves);
5. the 80 costliest lichess positions: how many mistakes it repeats;
6. lichess itself, for anything that ships.

## What I need from the owner before any batch

These are the places where I may be misreading the intent:

1. **"Trainers in the mix"**: I read this as strong engines playing the games (arms B to F), with Stockfish 19 as the consistent scorer where an arm calls for one. Is machete meant to play in any of these games (for example machete against a teacher, so the positions are ones machete actually reaches)?
2. **The 2-million-game chunk**: I have put it last (batch 5), made with whatever recipe batches 1 to 3 choose, rather than first with today's untested settings. If the chunk is wanted sooner, batch 1 alone (depth) is the minimum to run before it.
3. **The Pi league**: with machete self-play ruled out as a data source, the league's remaining use is as a judge (two networks play, Stockfish scores the moves). Keep it for that, or shelve it?
4. **Dragon and Leela**: is Dragon allowed as a teacher? Leela needs the GPU, which training also needs.
5. **Kamatera**: what quota was approved (how many cores, which server types), and is the $450 the ceiling for this programme or a first instalment? I will not handle the account, its API keys or payment; I need servers created with an ssh public key I give you, and I need to know which data centre.
6. **Order of the batches**: depth first (my proposal, because it sizes everything after it), or teachers first?
