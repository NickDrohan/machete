# Team claude, round 2: what the entry holds and what measured it

For the v0.3.1 synthesis (COMPETITION_ROUND2.md, rule 6): every change in the
entry, its commit, and the ledger line that measured it on its own. A change
without its own measurement is marked so, and is not synthesis material.

Base: `round2-fork` (cf83efc), machete 0.2.0 on mach 6.0.0, network C2.

| change | commit | what it does | measured by | result |
|---|---|---|---|---|
| U-01 tunables | 7c7998e | fifteen search constants become UCI spin options, defaults unchanged | bench 154591 unchanged; unit test | tree identical; no strength claim |
| U-02 SPSA runner | 42ddc79 | tunes the fifteen together in bounded chunks | tool | - |
| SPSA-tuned constants | - | the tune's values as the new defaults | parked after 4,411 steps: the search below changed under it | not in the entry |
| S-01 continuation history | dd329e0 | quiet ordering and LMR read how a move fared after the last move and the move before it | SPRT-S01 vs claude2/main | **rejected: -3 +/- 19** (1248 games, 214-808-226) |
| S-02 SEE and history pruning | b536d5f | losing captures, hanging quiets and poor-history quiets skipped near the horizon | SPRT-S02 vs S-01 | **rejected: -7 +/- 24** (831 games, 130-554-147) |
| S-03 TT eval, singular +2/-1 | 90a042c | pruning judges by the table's score where its bound disagrees with the eval; double and negative singular extensions | not measured (SPRT-STACK1 parked) | not in the entry |
| S-04 capture history | 401c45c | captures of equal gain ordered by their record | not measured (SPRT-STACK1 parked) | not in the entry |
| S-05 ProbCut | 48379be | a capture holding beta + 200 through a shallower search cuts | not measured (SPRT-STACK1 parked) | not in the entry |
| S-06 LMP/LMR refinements | f9c6124 | LMP halves when not improving; checks reduced less; quiets after a capturing TT move more | not measured (SPRT-STACK1 parked) | not in the entry |
| E-01 fifty-move fade | df9e44f | eval * (200 - halfmove) / 200 | not measured (SPRT-STACK1 parked) | not in the entry |
| E-02 non-pawn correction | 8569a05 | correction history by each colour's non-pawn pieces | not measured (SPRT-STACK1 parked) | not in the entry |
| X-01 deep moves (owner's idea) | dd6d0c9 | every 5th move at 2.5x time and +1 LMR, the others at 62.5% (options, off by default) | MATCH-DEEP5, options on vs off | **rejected: -28 +/- 37** (343 games, 37-241-65); stays off |
| network C9 | - | C2 data + 30M Leela (148.6M positions) | not measured (parked) | not in the entry |

## The entry

`claude2/main` with `id name machete claude`: machete 0.2.0 on mach 6.0.0 (2.6%
faster than on 5.11, same tree), network C2, and the fifteen search constants as
UCI options at their 0.2.0 defaults. It plays as 0.2.0 does: bench 154591.

Nothing from the search branch is in it. Of what was measured, S-01 (-3 +/- 19),
S-02 (-7 +/- 24) and the deep moves (-28 +/- 37) were rejected; S-03 to E-02, T-01
and network C9 were built and gated (tests, mate suites) but never played a
measured game, since the owner stopped new jobs at 19:10, and are not shipped
unmeasured. The 200-game anchor against v0.2.0 (rule 5) was not run for the
same reason; with bench identical to 0.2.0's the entry is 0.2.0 by construction.

Synthesis material from team claude: none measured positive this round. The
tunables (U-01, U-03) and the SPSA runner (U-02) are tools for the next one.
