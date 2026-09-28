# Search advantage under a frozen NNUE

*A research design, 2026-09-27. Prior art checked against Stockfish `master` (`search.cpp`, `timeman.cpp`, `thread.cpp`) on the day of writing; where a claim rests on memory rather than a source it says so.*

## 0. What a search can and cannot add

With identical leaf evaluation, a tree adds exactly one kind of information: the values of leaves deeper than the opponent's. Every mechanism below is therefore one of three things - **allocation** (which leaves get looked at), **termination** (when to stop looking), or the **decision rule** (how the root picks among what it saw). Two consequences frame the whole design:

- A monotone transform of scores (centipawns to expected score, say) changes no decision: max and min commute with monotone functions. Any advantage from a "better objective" has to come from *asymmetry* - valuing our draws differently from theirs - which is a bet about the opponent, not about chess.
- Nothing a search concludes is a proof unless it terminates in a mate, a tablebase position or an exhaustive enumeration. Alpha-beta values under pruning are heuristic; full-width values are minimax values *of the shared evaluation*, which is still not truth. The document says "bound" or "proof" only where a mechanism earns it.

**Established evidence that search matters even with a shared net.** In 2020, engines that adopted Stockfish-derived NNUE files (Igel, Nemorino) gained 200-300 Elo at once and still finished well below Stockfish on the same lists - search and implementation, not the net, made up the gap. Stockfish's own history is thousands of search patches worth 1-3 Elo each, punctuated by speed work worth more per change. Our engine's record this week is the same story in miniature: 0.2's +200 over 0.1 was a quarter speed; the round-2 search stack cost 26% of nodes per second and every one of its measured features came out level or worse (RESULTS.tsv, SPRT-S01/S02, MATCH-DEEP5); the single largest gain (+55) came from evaluation data, which this brief forbids.

**Where the budget goes today.** Iterative deepening spends most of its final nodes re-confirming a principal variation it already believes. Stockfish keeps deepening only while `elapsed <= 0.5 * totalTime`, so it routinely starts an iteration it cannot finish; the tail of that iteration is the least valuable computation in the move, and it is the budget every design below draws on.

## 1. Thesis

The most promising advantage is **decision-relevant allocation at the end of a move**: instead of spending the last fraction of the budget on another uniform iteration, measure whether the root decision is actually contested (the margin between the best two moves, in the same iteration and window), and if it is, spend that fraction resolving the specific facts the decision rests on - the true score of the runner-up, and whether the chosen move survives a search that prunes differently near the root. *Established:* Stockfish already converts several signals about decision stability into time (best-move changes, falling eval, the best move's share of nodes - our T-01 is its `nodesEffort`), and singular extensions already ask "is the table move the only one that works" one node at a time; there is no verification of the chosen root move under a different search policy, and no mechanism that spends time on the runner-up rather than on the whole tree. *Hypothesis:* at elite depth the decision flips that cost games are concentrated in moves where the margin is small and the loser of the comparison was searched under heavier reductions; a directed audit finds a useful fraction of those flips at the same wall-clock, where uniform deepening finds them only at the next iteration, which it cannot afford. This matters against elite engines because they are the opponents who punish exactly those flips; it is not a mechanism for beating weaker engines. The main risk is that the audit is correlated with the search it audits (same evaluation, same transposition table, same ordering) and confirms its errors at extra cost; the designs below spend most of their care on that.

## 2. Baseline checklist

Everything here is table stakes and worth more than any single mechanism below; none of it is the research question.

- Nodes per second: SIMD inference of the shared net, incremental accumulators with a per-thread refresh cache (Finny tables), one-pass move generation, staged move picking, prefetch of the transposition entry before make. Ten percent of speed is worth roughly what a good search patch is worth; a 26% loss erases a season of them.
- The transposition table: bucketed, aged, lockless; a `ttPv` bit; storing the static evaluation.
- Ordering: TT move, captures by SEE and capture history, killers, counter-move, main and continuation history with gravity; capture history.
- Selectivity, each with a measured margin: reverse futility, razoring, null move with verification at depth, ProbCut (with the table short-cut), futility, late-move pruning, SEE pruning of captures and quiets, history pruning; late-move reductions with the usual adjustments (PV, cut node, improving, history, TT capture, check) and a full re-search on fail-high.
- Extensions: singular with multi-cut and negative extension, check extensions where measured.
- Correction history in the static evaluation (pawn, non-pawn, minor/major, continuation), and its magnitude in futility margins, LMR and the singular margin - all of which Stockfish does today (see §9).
- Time management: optimum and maximum from the clock; scaling by falling evaluation, best-move stability over depths, best-move instability across the search, the best move's node share, and the opponent's clock; stop at the optimum, deepen only while half of it is unspent.
- Lazy SMP with a shared table and a depth-and-score-weighted vote for the final move.
- Draw handling: repetition and fifty-move awareness in the search; rule-50 scaling of the evaluation output (a decision-rule change, allowed).

## 3. Ten mechanisms, ranked

Labels: **E** established practice, **X** proposed extension of something established, **S** speculative research. No Elo numbers: a mechanism's value is what its experiment (§6) measures.

| # | Mechanism | Failure it targets | Observable signal | Intervention | Cost | Closest predecessor | Most likely reason to fail | Label |
|---|---|---|---|---|---|---|---|---|
| 1 | **Root decision audit** (design A) | The last iteration re-confirms a PV instead of resolving a close decision; the runner-up's score is only a bound | Margin between best and runner-up in the same iteration; time left short of another iteration | Open the runner-up with a full window at the current depth; if the margin is small, test the chosen move under a refutation policy (no null move, lighter reductions, no history pruning near the root); switch only if the runner-up survives the same test | 10-30% of one iteration, taken from the iteration that would not have finished | Stockfish's time scaling by `bestMoveChanges`, `nodesEffort`; MultiPV; singular extensions at non-root nodes | The audit shares the table and the ordering, so it confirms the same errors; switches on noise | X |
| 2 | **Refutation policy search** (part of A, usable alone) | A move chosen because its refutation was pruned or reduced away | The chosen move fails low under a search that prunes less in the first plies | A fail-low test of the chosen move against `score - W` with different pruning for the first K plies, private or tagged table entries | Bounded, 5-15% of the remaining budget | Verified null-move (Tabibi & Netanyahu 2002); ProbCut's verification search; multi-cut | Different pruning finds different noise, not different truth; the private table costs the shared one its work | X |
| 3 | **Pruned-branch ledger** (design B) | Pruning is persistent: a branch pruned at depth d is pruned again at d+1, so no iteration ever looks | Record of near-root prunes with their slack to the threshold | Reopen the few with least slack and most PV proximity, through the table, when the root is contested or the score drops | Recording is confined to plies <= 6; reopening capped at a few percent of an iteration | Conspiracy numbers (McAllester 1988), singular extensions, LMR re-search | Slack does not predict which prunes mattered; the flips that cost games come from deep discoveries, not near-root prunes | S |
| 4 | **Disagreement-aware pruning** (design C) | The static evaluation's error is unpredictable in some structures, and pruning margins assume it is not | Disagreement between the correction tables (pawn vs non-pawn vs continuation), separate from their magnitude | Scale futility, reverse-futility and razoring margins and the LMR by the disagreement, budget-neutral around the baseline | Negligible: the tables exist | Stockfish's use of `abs(correctionValue)` in futility, LMR and the singular margin | Magnitude already carries the information; the extra term is noise and its tuning overfits | X |
| 5 | **Defence-narrowness tie-break** (computational asymmetry) | Among near-equal moves, the engine picks arbitrarily rather than for the problems it sets | For each candidate: how many opponent replies hold within a margin, and how late or reduced the holding reply was found | Among root moves within epsilon of the best, prefer the one whose holding replies are few and were hard for our own search to find; never trade evaluation for it beyond epsilon | The reply statistics fall out of the root search; the counting needs the runner-up replies' scores, a MultiPV-like cost at ply 2 | Trappy Minimax (Gordon & Reda 2006); contempt and swindle modes | An elite opponent finds the narrow defence; "hard for us" only predicts "hard for them" if their search resembles ours | S |
| 6 | **Bounded local solvers** | The evaluation cannot see a fortress or a decided race; the search shuffles or misjudges a pawn race by a tempo | No progress in the PV over many plies at a large advantage; a race where both sides queen within the horizon | A progress test (the defender may pass twice; if we still cannot improve, scale the score toward a draw) and a node-capped proof-number search for "promotes / mates within N" reused through the table | Rare triggers, capped nodes | Rule-50 scaling; null-move fortress heuristics; df-pn (Nagai 2002); mate solvers in shogi | False fortresses; triggers too rare to matter at elite level where tablebases cover most of it | S |
| 7 | **Role-differentiated helper threads** | Lazy SMP helpers duplicate the main search's questions | The main thread's margin and refutation status | One helper deepens the runner-up, one runs the refutation policy on the chosen move; they report at the root; their table writes carry a policy tag | Costs the helpers' contribution to depth (Lazy SMP's diversity is real) | Lazy SMP; thread voting; YBWC | Fewer conventional helpers lose more depth than the roles gain; tagged entries fragment the table | X |
| 8 | **Game-level clock policy** | Time is allocated per move; the value of a second depends on how many contested decisions are still to come | Margin history, phase, the opponent's clock, the count of recent contested moves | Bank time when margins are large; spend when the audit reports a contest; model the remaining number of contested decisions rather than a fixed moves-to-go | None | Stockfish `timeman.cpp` (mtg, `timeAdvantage`), `nodesEffort`, `bestMoveInstability` | Stockfish's scalings already capture most of it; a game-level model overfits the time control it was tuned at | X |
| 9 | **Speed as the lever** (challenger) | Everything above assumes allocation beats raw depth | Nodes per second, identical tree | Profile; remove overhead; SIMD; cache | Engineering time only | Every engine's history | It is everyone's lever, so it is not an *advantage* - but it is the one that never loses | E |
| 10 | **Random diversity instead of directed audits** (challenger) | Directed audits may be no better than jitter | The same flip suites | Jitter reductions and margins across iterations or helper threads (an old Lazy SMP trick) and compare with the directed audit at equal nodes | None | Lazy SMP depth skipping; randomized restarts | If it matches the audit, the audit's machinery is not worth its complexity; if it loses, diversity is not the explanation | E/S |

Two directions from the brief are folded rather than ranked: *persistent structural knowledge* is what correction histories already are (keyed by pawn structure, material, and move pairs; invalidated by their keys changing), and any richer "fact table" runs straight into the validity problem the brief names - one pawn move changes which facts hold, and checking that costs what the fact saves. *Exact solving* appears only as bounded local solvers (#6): it is the one source of information the shared net lacks, but its triggers are rare in engine games.

## 4. Designs for the best three

### A. Root decision audit

**What it obtains that the baseline does not:** the runner-up's true score at the current depth (the baseline knows only that it failed low against the best), and whether the chosen move survives a search that reduces and prunes differently in the plies just below the root. The baseline obtains the first only by finishing another iteration, and the second never.

**Required state.** Per root move: score from the last completed iteration, whether that score is exact or a bound, nodes spent under it (`effort`), and the depth at which it was last searched. Per search: `margin`, `audit_state` in {none, runnerup_open, refuting_best, refuting_runnerup, done}, the audit's node budget and nodes spent, and the iteration time estimate.

**Trigger.** After iteration `d` completes (d >= 10), estimate the next iteration's cost as `t_d * max(EBF, 1.6)` from the last two iterations. If it fits inside the soft limit, deepen as usual. Otherwise, instead of starting an iteration that will be cut off, enter the audit if `remaining_soft >= audit_min` (say 8% of optimum); if not, stop.

**Steps.**
1. *Open the runner-up.* Search root move `m2` with a full window `(-inf, +inf)` at depth `d` (it was searched with a null window `(-s1-1, -s1)`), respecting the same reductions the root applies. Cost is one root subtree; cap it at 30% of the last iteration's nodes. Result `s2`. Margin `delta = s1 - s2`.
2. *Decide whether the decision is contested.* `tau(d) = tau0 + kappa * uncertainty`, where `uncertainty` is the absolute correction value at the root (already computed) - a first use of the same signal Stockfish puts into futility margins. If `delta > tau`: the decision is robust; **stop now** and bank the time (this is the "easy move" case, and here it is decided on the margin, not on node share).
3. *Refute the best.* Search `m1` at depth `d - 1` against the window `(s1 - W - 1, s1 - W)` under policy R for the first K = 4 plies below the root move: no null move; LMR reduction lowered by one and never applied to the TT move's siblings at ply 1; futility and history pruning off; SEE pruning kept. Beyond K plies the search is the normal one. Table access under R at plies <= K: reads for ordering only, no cutoffs from entries written by the normal search; writes tagged `policy=R`. Cap: 40% of the audit budget. If `m1` holds (`>= s1 - W`): the move stands; stop.
4. *Refute the runner-up.* If `m1` failed low with value `v1`, search `m2` the same way against `(s2 - W - 1, s2 - W)`. If `m2` holds and `v1 < s2 - W`: **switch to m2**. Otherwise keep `m1`, and if time remains, resume normal deepening: the audit has found instability, and Stockfish's own evidence says instability deserves time.

`W` is the tolerance below which a fail-low is treated as noise: start at 25 cp at d = 10, growing with depth as `W = 25 + 3 * (d - 10)`.

**Where the budget comes from.** Steps 1-4 are paid from the iteration the baseline would have started and abandoned; step 2 returns budget to the clock more often than it spends it. The audit never runs when an iteration would fit.

**Pseudocode.**

```
after_iteration(d):
    next_cost = t[d] * max(ebf(t[d], t[d-1]), 1.6)
    if elapsed + next_cost <= soft: return DEEPEN
    if soft - elapsed < 0.08 * optimum: return STOP
    s2 = root_search(m2, window=(-INF, INF), depth=d, cap=0.30 * nodes[d])
    if s1 - s2 > tau(d): return STOP                       # robust: bank the time
    v1 = root_search(m1, window=(s1-W-1, s1-W), depth=d-1, policy=R, cap=0.40 * audit_budget)
    if v1 >= s1 - W: return STOP                            # survives a different search
    v2 = root_search(m2, window=(s2-W-1, s2-W), depth=d-1, policy=R, cap=remaining_audit)
    if v2 >= s2 - W and v1 < s2 - W: best = m2; return STOP
    return DEEPEN_IF_TIME                                   # unstable: keep looking
```

**Integration points.** The iterative-deepening loop (the stop decision); the root move loop (a per-move search entry with a chosen window and policy); the search's pruning and reduction sites, which read `policy` and `ply_below_root` from the stack; the table's store and probe (one policy bit, taken from the generation field's range - 32 generations instead of 64 cost nothing measurable).

**Fallback.** Any cap reached: keep the iteration's best move and stop. Mate scores at the root: no audit. Multi-threaded: only the main thread audits; helpers keep deepening, and the audit's result overrides the vote only when it switched.

**What it displaces.** The unfinished iteration; nothing else. Multi-threaded, the helpers' last iteration is unaffected.

### B. Pruned-branch ledger with selective reopening

**What it obtains:** the values of specific branches the search decided not to look at, near the root, chosen by how close the pruning decision was. The baseline re-prunes them at every depth; only a change in the threshold (deeper depth, a different static evaluation) ever reopens them, and singular extensions cover only the table move.

**Required state.** A ring of N = 256 entries per thread: `{key, move, ply, depth, kind, slack, iteration}`. `kind` in {futility, reverse_futility, lmp, history, see}; `slack` in centipawn-equivalent units: for futility and reverse futility the distance from the margin; for SEE the loss beyond the threshold; for LMP the number of moves past the limit; for history the distance below the threshold divided by the history scale that buys one ply of reduction (so all kinds are comparable). Recording only at `ply <= 6` and `depth >= 4`: those nodes are a tiny fraction of the tree, so the cost is a few stores per node there and nothing elsewhere.

**Importance without searching.** `importance = a / (1 + slack / sigma) + b * (6 - ply) / 6 + c * [kind in {history, lmp}]`, with `sigma` = 30 cp; history and LMP prunes score higher because they rest on ordering statistics rather than material. Entries on the current PV's path (the node key matches a PV node) get `+ p`. Everything here is a heuristic; the experiment in §6 measures whether it predicts anything.

**Trigger.** The same audit window as design A (the iteration that would not finish), or a score drop of more than 40 cp between iterations (a "surprise"). Reopen the top k = 8 entries by importance from the last two iterations.

**Reopen.** For each: set up the position by key (the ledger stores the path from the root as a move list of at most 6 moves, so the position is reconstructed by making them), search the pruned move at `depth - 1` with the window `(alpha_node - 1, alpha_node)` where `alpha_node` is the node's current table bound; store the result in the table normally. A fail-high there changes the parent's table entry, and the next iteration - or the audit's step 1 - picks it up through ordering and bounds. Node cap: 5% of the last iteration in total.

**Pseudocode.**

```
at a pruning site with ply <= 6 and depth >= 4:
    ledger.push(key, move, ply, depth, kind, slack_cp, iteration, path)

audit_reopen():
    for e in top_k(ledger, importance):
        pos = root.replay(e.path)
        alpha = tt.bound(e.key) or pos.static_eval()
        v = -search(pos.make(e.move), depth=e.depth-1, window=(-alpha, -alpha+1))
        if v >= alpha: tt.store(e.key, e.move, v, e.depth, LOWER)   # the branch mattered
        log(e, v >= alpha)
```

**Integration points.** Each pruning site (one call); the audit scheduler from design A; the table.

**Budget and fallback.** Empty ledger or all slack above 3 sigma: skip. Multi-threaded: each thread keeps its own ledger; only the main thread reopens.

**What it displaces.** The same unfinished iteration as A; when both run, B's reopened branches feed A's step 1 (a runner-up whose refutation was reopened now has a real score).

### C. Disagreement-aware pruning

**What it obtains:** an estimate of *how unpredictable* the shared evaluation's error is at this node, separate from *how large* the correction is. Stockfish's `abs(correctionValue)` measures the second; the hypothesis is that positions where the pawn-structure table, the non-pawn table and the continuation table disagree about the correction are positions where none of them has captured the error, and there the search should look rather than prune.

**Required state.** None new: the correction tables exist. At each node where the corrected evaluation is computed, keep the components `c_pawn`, `c_nonpawn`, `c_cont` on the stack.

**Update rule.** `u = |c_pawn - c_nonpawn| + |c_pawn - c_cont| + |c_nonpawn - c_cont|`, in the same units as the correction. Maintain a running mean `u_bar` over the search (exponential, alpha = 1/4096) so the adjustment is relative, and clamp `g = u / u_bar` to [0.5, 2].

**Intervention, budget-neutral.** `futility_margin *= g`; `reverse_futility_margin *= g`; `razoring` off when `g > 1.5`; `lmr_reduction -= (g > 1.5)`; `singular_margin` widened by `(g - 1) * 20`. Because `g` is centred on 1 by construction, the tree at fixed depth is about the same size as the baseline's: nodes move from certain structures to uncertain ones instead of being added. The non-neutral variant (`g` clamped to `[1, 2]`) is the ablation that separates "reallocation" from "caution".

**Pseudocode.**

```
at node: c = corrections(pos); u = |c.pawn - c.nonpawn| + |c.pawn - c.cont| + |c.nonpawn - c.cont|
         u_bar += (u - u_bar) / 4096; g = clamp(u / u_bar, 0.5, 2.0)
         futility = base_futility(depth) * g; rfp = base_rfp(depth) * g
         razor_allowed = g <= 1.5; lmr_extra = -(g > 1.5)
```

**Integration points.** The static-evaluation site and four pruning sites. **Fallback:** `g = 1` when fewer than 4096 nodes have been seen.

**What it displaces.** Nothing; it moves nodes. Its cost is three subtractions per node.

## 5. Adversarial critique

**A, decision audit.**
- *Correlated searches.* Step 1 shares everything with the search it audits: the same net, ordering and table. Its only independence is the window. Step 3's independence comes from policy R, and it is partial: beyond K plies the normal search and its table take over, so a refutation that lives at ply 6 is as invisible to R as to the baseline. If K is raised to buy independence, the cost grows exponentially. The honest description is "a second opinion in the first four plies", not a verification.
- *Misleading confidence.* "`m1` holds under R" is not a bound on `m1`'s value; it is a heuristic value under a second heuristic policy. Treating it as confirmation and stopping early is the mechanism's main bet, and if R is too similar to the normal search it stops early on exactly the moves that needed the next iteration. The stop-on-robust rule (step 2) has the same exposure: a large margin between two wrong scores is still wrong.
- *Excessive caution.* The switch rule can move to a runner-up that is worse: `m1` fails low by noise, `m2` holds by noise. Requiring `v1 < s2 - W` and `m2` to hold under R limits this; the suite in §6 measures how often the switch is right.
- *Overhead.* Step 1 costs 10-30% of an iteration on every contested move. At long time controls the unfinished iteration is a smaller fraction of the budget and the audit takes a larger share of real search; the gain, if any, should shrink with time. Test at LTC before believing STC.
- *Table contamination.* R's entries carry a policy bit; the normal search ignores their bounds. If the bit is dropped for storage economy, R's optimistic and pessimistic bounds leak into the next search's cutoffs. Losing one generation bit is the price.
- *Opponent overfitting:* none; nothing depends on the opponent's implementation.

**B, pruned-branch ledger.**
- The importance proxy is the whole idea, and it is untested. Slack measures how close the pruning decision was, not how much the branch matters; the branches that decide games are often pruned with large slack because the evaluation was wrong about them - and then the ledger never reopens them.
- Recording near the root is cheap, but "near the root" is also where pruning is rarest and least consequential: most prunes happen deep, where recording would cost. The mechanism may be looking under the lamp post.
- Reopening writes deeper entries for audited branches into the table; later iterations then prefer them for ordering. That is the intended effect and also a bias: the audited branches receive attention the unaudited ones did not, regardless of merit.
- Correlation again: the reopened search prunes below the reopened node with the normal policy.

**C, disagreement-aware pruning.**
- Stockfish's magnitude term may already carry everything; disagreement is one more feature with tuned coefficients, and a tuning run will "find" a gain in noise if allowed enough variants. Pre-register the coefficients or the ablation is meaningless.
- Budget neutrality by a running mean makes the pruning depend on the order the search visits nodes: two searches of the same position with different tables prune differently. That is diversity, which Lazy SMP suggests is not bad, but it makes fixed-node reproduction harder; log `u_bar` at the root.
- `u` is undefined where a table has no entry (its correction is zero); early in a game every table is empty and `u` measures nothing. Fallback to `g = 1` for the first 4096 nodes handles the search, not the game; the first moves of every game run on an empty signal.

*Heuristic confidence versus a valid bound, for all three:* the only valid bounds in these designs are the ones alpha-beta produces relative to the shared evaluation at the searched depth under the policy used. No mechanism here proves a move is best; the tablebase-adjacent solver (#6) is the only place a proof is possible, and only for mates and promotions within its cap.

## 6. Minimal experiments

Position suites diagnose; matches decide. Every suite position must be a legal position from a real game with the claimed continuation verified by a deeper search of the same engine, not composed.

**A.** *Suite:* mine "late flips" from the engine's own games - positions where the move chosen at node budget N differs from the move chosen at 4N, with the 4N move confirmed at 16N. Two hundred positions, held out from tuning. *Metric:* at budget N plus the audit's actual nodes, the fraction of positions where the decision matches the 16N decision; the baseline is uniform deepening given the same total nodes. *Log:* margin, `tau`, which step ended the audit, `v1`, `v2`, switches and whether each switch was right, nodes per step. *Ablations:* step 1 only (no refutation policy); refutation policy without the margin gate; R with K = 2 and K = 6. *Abandon if:* at equal nodes the audit matches the 16N decision no more often than the baseline, or the switches it makes are wrong more than half the time. *Then:* the match protocol in §7.

**B.** *Prototype:* recording only, no reopening, for one week of ordinary matches; log every ledger entry with its slack and, from the next iteration's table, whether the pruned move's value ever exceeded the node's bound ("mattered"). *Metric:* precision of the importance ranking - the fraction of the top-8 that mattered, against the base rate. *Abandon if:* top-8 precision is within noise of the base rate, or recording costs more than 1% of nodes per second. *Then:* reopening, measured on the same late-flip suite as A at equal nodes; then matches.

**C.** *Study:* at nodes with depth >= 8 in a corpus of engine-game positions, log `u`, `|c|`, and the error `|search_value - corrected_static_eval|`. *Metric:* does `u` explain error variance beyond `|c|` (partial correlation)? *Abandon if:* not. *Then:* the budget-neutral variant against the baseline at STC, with the non-neutral variant as the ablation that separates reallocation from caution.

**For each finalist, the brief's questions.**

- *A.* Information: the runner-up's exact score at depth d and the chosen move's robustness to a different near-root policy. It changes the move only when the margin is small and R disagrees - rare, and those are the decision-relevant moves. Worth it because it is paid from an iteration that would have been thrown away. Independent of the opponent's implementation. Likely to shrink with thinking time: deeper searches flip less; the LTC test decides. Resolving experiment: the late-flip suite at equal nodes.
- *B.* Information: values of specific near-root branches the search will otherwise never look at. It changes the move when such a branch is the refutation of the chosen move or the resource that saves the runner-up. Worth it only if the importance proxy has precision; the recording-only prototype settles that before any search time is spent. Independent of the opponent. Persists with thinking time in principle (pruning is persistent at every depth), which is the strongest argument for it if the proxy works.
- *C.* Information: where the shared evaluation's error is unsystematic. It changes moves indirectly, by moving nodes toward those positions. Costs nothing, so it is worth it if it is not zero. Independent of the opponent; persists at all time controls since it is per node. Resolving experiment: the partial-correlation study.

## 7. Validation plan

- **Identical evaluation.** One network file, checked by hash at engine start and printed in the `uci` reply; a match aborts if the two sides' hashes differ. The baseline and the candidate are the same binary with the mechanism behind a UCI switch, so the inference code is byte-identical.
- **Games.** Paired openings, colours reversed, from a balanced book; results scored pentanomially (the pair is the unit). Opening families held out: split the book by ECO family into tuning and test halves; report both.
- **Resources.** One thread per engine, pinned; the same hash; a move overhead that is measured, not assumed; never more thinking engines than physical cores.
- **Opponents.** The baseline itself (the primary test, since it isolates the mechanism), the previous two releases, and at least two third-party engines at equal wall-clock to check that a gain over our own baseline is not a gain over our own habits. Opponent-specific gains (anything in mechanism #5) are reported separately and never pooled with general strength.
- **Primary comparison:** equal wall-clock, STC (10+0.1) then LTC (60+0.6), the candidate accepted only when both pass. Fixed-node matches diagnose search efficiency and are never the acceptance test.
- **Stopping rules,** predefined: SPRT with pentanomial statistics, bounds [0, 2] Elo at STC and [0.5, 2.5] at LTC (the fishtest convention for search patches), alpha = beta = 0.05, a hard cap of 40,000 games. A mechanism with tunable coefficients registers its variants before the first game; each variant is one test, and the family passes only if the LTC confirmation passes for the single variant chosen at STC - the two-stage rule is the multiple-comparison control.
- **Scaling checks.** Any accepted mechanism is re-run at 8 threads at LTC (Lazy SMP's diversity may already capture an audit's benefit) and at a longer control (180+2) with fewer games, reported with its interval even if inconclusive.
- **Instrumentation.** Every match logs the mechanism's trigger rate, the budget it consumed and returned, and the switch rate; a mechanism that "wins" without ever triggering has won by noise.

## 8. Decisive recommendation

**Implement first: design A, in its simplest form** - step 1 (open the runner-up) and the margin-gated stop, with the refutation policy added as the second variant. It is the cheapest to build on a competent search (a root entry with a chosen window, a policy flag read at a handful of pruning sites, one bit in the table), it has a clean diagnostic (the late-flip suite at equal nodes) before any match is played, and its budget is explicitly the computation the baseline wastes.

**Higher-risk idea worth exploring: #5, defence-narrowness as a tie-break.** It is the only mechanism that acts on *which problems the opponent must solve*, and the statistics it needs come free from a root search that already opens the runner-up. The risk is that it rewards our own difficulty rather than the opponent's; the test is a match against opponents with different search designs, reported separately, and the idea is abandoned if the gain does not appear against at least two of them.

**Attractive idea to reject: an expected-score or contempt-shaped decision rule.** Monotone transforms change no decision; asymmetric ones are a bet that the opponent misvalues draws, which elite opponents do not. Draw-aware behaviour belongs in the evaluation's scaling (rule 50, material) and the time policy, not in the root's objective. Likewise rejected: a persistent "fact table" beyond what correction histories already are - its validity conditions cost more than its facts.

**Two weeks.**

| Days | Work | Continue if | Cancel if |
|---|---|---|---|
| 1-2 | Instrument the baseline: margin, runner-up bound, audit-window frequency, `nodesEffort`; mine the late-flip suite (200 positions, verified at 16N) | The audit window exists on >= 20% of moves at STC | It is under 5%: there is no budget to redirect |
| 3-5 | Build A step 1 + margin gate; run the suite at equal nodes; ablate `tau` | Matches the 16N decision more often than the baseline at equal nodes | No difference at equal nodes |
| 6-7 | STC SPRT of A-step-1 vs baseline; in parallel, C's correlation study on the same games | STC passes or is inconclusive with positive trend; C shows partial correlation | STC fails: stop A; C shows none: drop C |
| 8-9 | Add the refutation policy (K = 4, policy bit); suite again; STC SPRT | Suite improves on step 1 alone | It does not: ship step 1 alone to LTC |
| 10-12 | LTC confirmation of the best A variant; 8-thread LTC; C's STC SPRT if its study passed | LTC passes | LTC fails: A is an STC artefact; record and stop |
| 13-14 | B's recording-only prototype riding on the LTC games; precision of the importance proxy | Precision beats the base rate | It does not: B is filed as measured-negative |

## 9. Prior art, verified on 2026-09-27 against Stockfish `master`

- **Correction history in pruning.** `search.cpp` adds `abs(correctionValue) / 198435` to the futility margin, subtracts `abs(correctionValue) / 26310` from the LMR reduction, and uses `abs(correctionValue) / 198368` in the singular double-extension margin. Design C differs by using the *disagreement between the component tables* rather than the magnitude of their sum, and by being budget-neutral.
- **Singular extensions.** Non-root only; conditions include `depth >= 6 + ss->ttPv`, a lower-bound table entry at `depth - 3` or more, `singularBeta = ttValue - (59 + 66 * (ttPv && !PvNode)) * depth / 63`; extension of 1, 2 or 3 by margins; multi-cut when the excluded search reaches beta; a negative extension of -3 when the table value is at least beta or at a cut node. Nothing verifies the chosen *root* move; design A's step 3 is the root-level analogue with a different policy rather than a different move.
- **Root moves.** Searched through the `Root` template without the non-root LMR; `bestMoveChanges` counts changes for time management; `iterValue` keeps four iterations of scores for the falling-eval term. There is no full-window search of the runner-up outside MultiPV.
- **Null-move verification** only at `depth >= 16`, guarded by `nmpMinPly`. **ProbCut** at `depth >= 3` with `probCutBeta = beta + 241 - 64 * improving` and a table short-cut when a lower bound at `depth - 4` already reaches it. `improving` and `opponentWorsening` are two-ply and one-ply static-evaluation comparisons.
- **Time management.** `totalTime = optimum * fallingEval * reduction * bestMoveInstability * highBestMoveEffort`, with `fallingEval` from the previous move's average score and the four-iteration buffer, `timeReduction` from how many iterations the best move has been stable, `bestMoveInstability = 1.077 + 2.229 * totBestMoveChanges / threads`, and `highBestMoveEffort` from the best move's share of nodes (our T-01). Deepening continues while `elapsed <= 0.5 * totalTime`. `timeman.cpp` scales optimum by `1 + 0.9 * min(timeAdvantage, 0)`: being behind on the clock reduces time, being ahead does not increase it. Design #8's game-level model would replace the fixed `mtg = 50` with a count of expected contested decisions; that is the only part not already present.
- **Threads.** No visible parameter differences between helpers and the main thread in `thread.cpp`; the final move is chosen by a vote weighted by `score - minScore + 14`, decisive scores first, ties to the longer PV. Design #7's roles are not present.
- **Trappy Minimax** (Gordon & Reda, IEEE CIG 2006) chooses slightly inferior moves when iterative-deepening scores suggest the opponent may err; it was validated against humans in Othello. Mechanism #5 keeps the choice within epsilon of the best score and estimates difficulty from search statistics rather than from score sequences, and its stated failure mode is that elite opponents do not err.
- Conspiracy numbers (McAllester 1988; Schaeffer 1990), B* (Berliner 1979), singular extensions (Anantharaman, Campbell and Hsu 1988), verified null move (Tabibi and Netanyahu 2002), df-pn (Nagai 2002), Komodo's MCTS mode (2018) and Lazy SMP are cited from memory of the literature, not re-read for this document.
- Our own ledger (`RESULTS.tsv`): SPRT-S01 (-3 +/- 19), SPRT-S02 (-7 +/- 24), MATCH-DEEP5 (-28 +/- 37), the 26% speed cost of the round-2 stack, and the round-2 final's +54/+60 from evaluation data.
