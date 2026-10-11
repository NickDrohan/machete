# Attack plan: exploit mistakes when they arise

2026-10-01. The goal: when an opponent errs, machete converts like the stronger engine does, instead of drifting into a draw. The attack data has to apply where an attack is on, not everywhere.

## What we know

| fact | number | source |
|---|---|---|
| attack games mixed into all training, ×3 | **−18 ± 27** vs C30 | SPRT-NET-C31, 626 games |
| attack suite | 3,114 positions where the winner's move was the only one keeping the attack | TCEC + 2026_Debut miniatures |
| attack book | 15,257 build-up positions (winner +30 to +250 before it passes +300) | same |
| attack games generated | about 8.2M (snapshot) + 12M (PC run 4) + pi-02 gen4 (attack book, 20M target) | gen-mach / Pis |
| winning attacking moves that are quiet | 48% (captures 32%, king zone 16%, sacrifices 5%) | attack_patterns.py |
| machete finds the winner's move in the Debut miniatures | 13 of 14 | debut analysis |
| a static king-danger detector | fires on 50% of attack positions and 20% of ordinary ones (2.6× selective); at 4× it catches only 15–24% | attack_detector.py |

The static detector is too blunt to gate on, because half of all attacking moves are quiet build-up, not pieces on the king.

## The gate: a mistake, not a king zone

The sharpest signal is the one you named: **the opponent just made a mistake**. Two plies ago the root score was S; after their move it is S + J, with a jump J ≥ about 80 cp. That costs nothing to compute, and it fires exactly when there's something to exploit. Attack positions in the suite are the winner at +30 to +250 before the win: that is what a fresh mistake looks like.

## Three steps, each one change, each measured

1. **Measure first (CPU, no code):** run 0.3.4 on the 3,114-position attack suite at fixed nodes, and record the find rate per motif (quiet / capture / king zone / sacrifice). This becomes the yardstick every later step must improve. The same run on 0.3.3 shows whether C30 already moved it.
2. **Search: exploit mode after a mistake.** When the root score jumps by ≥ J in our favour, for the rest of that search:
   - reduce less on quiet moves that increase pressure on the enemy king zone;
   - extend checks one ply more;
   - turn on contempt against a stronger opponent too, because a fresh mistake means the draw is no longer the best realistic result.

   Measure two ways: the find rate on the suite must rise, and an SPRT against 0.3.4 must hold at least 0. Mistakes are rare between equal engines, so the SPRT is a no-regression check, and the suite and lichess are the gain measures.
3. **Network: an attack output, used only under the gate.** The net already picks one of 8 outputs by piece count. One more, trained only on the attack games, would be read when the mistake gate fires. Ordinary positions never see it, which is the fix for C31's −18. This needs trainer and engine changes and a new file format, so it comes after step 2 shows the gate is right.

## Data, meanwhile

- Keep generating attack games from the full 15,257-position book: double the 7,037-position interim book C31's data came from.
- pi-02 is on the attack book (gen4, 20M target).
- The **lichess games** are the real test set: every non-win against a weaker bot (the review queued as REVIEW-LICHESS-033) lists the moves where machete had a win and didn't take it. Those positions join the suite as "conversion" positions.
