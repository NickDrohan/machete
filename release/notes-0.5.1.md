<div align="center">

# ♞ machete 0.5.1

**A UCI chess engine written in [Mach](https://github.com/briar-systems/mach)**
*named for what it does to a variation tree*

![version](https://img.shields.io/badge/version-0.5.1-2ea44f?style=for-the-badge)
![platform](https://img.shields.io/badge/windows-x86--64-0078D6?style=for-the-badge&logo=windows)
![language](https://img.shields.io/badge/written%20in-Mach%206.10-8a2be2?style=for-the-badge)
![protocol](https://img.shields.io/badge/protocol-UCI-f39c12?style=for-the-badge)

![against 0.5.0](https://img.shields.io/badge/against%200.5.0-%2B19%20%C2%B1%2012-blue)
![against Koivisto](https://img.shields.io/badge/against%20Koivisto%209.0-%2B27%20over%200.5.0-blue)

</div>

---

## 🎯 What changed

0.5.1 is a bundle: two search changes and a network, each measured on its own first, and the package measured as a whole.

| | on its own, against 0.5.0, 10+0.1, 3,000 games |
|---|---|
| **Razoring**: in the last two plies, a node whose evaluation is far below alpha is checked by the capture search alone | +15 ± 12 |
| **Losing captures searched after the quiet moves.** A capture that loses material had been scored above every quiet move but the killers and the counter move, against the comment beside it (found by an outside review of the code) | +10 ± 12 |
| both together | +16 ± 12 |
| **The network C33F280P3ALL**: 0.5.0's recipe plus 22.7M rook endings, 60M more ordinary positions and 100M deep (15,000-node) self-play positions | +13 ± 12 |

| the 0.5.1 package | games | result |
|---|---|---|
| **against 0.5.0 as released**, 10+0.1, no early stop | 3,000 | **+19 ± 12** (634 wins, 1,896 draws, 470 losses) |
| **against Koivisto 9.0**, 10+0.1 | 1,200 | **−228 ± 24**, where 0.5.0 scored −255 ± 25 |

## ⏱️ The clock

Three changes to how time is spent, none of which changes a move in a 10+0.1 match:

- **Premoves.** When the opponent plays the move the engine was pondering, the time already spent pondering now counts toward the reply. A reply that has had its whole share is played at once: 0.12 s from `ponderhit` to `bestmove` where 0.5.0 searched another 1.8 to 6.2 s. Three such replies in a row at most; the fourth correctly predicted move gets a fresh search. On lichess 56% of the bot's moves were ponder hits. Options `PonderCredit` (1) and `PremoveChain` (3).
- **A reserve for lag in games without increment.** Every move still to come costs the GUI's and the network's lag, so without an increment that covers it the share comes from the clock less 100 moves of `MoveOverhead` (new option, default 20 ms), at most a third of it. With 130 ms of lag a 5+0 game now lasts to about move 130-155 where it ran out at 106-127; at 60+0 it measured −5 ± 22, i.e. nothing lost.
- **`EndgameTime` and `EndgameMen`**: a larger share of time for positions of few men, off by default. 2.5 times the time at 7 men measured +0 ± 12 at 10+0.1; a test of 4 times at 12 men in longer games is running.

What was tried and is *not* in it: spending an even share over 50 assumed moves instead of a twenty-fifth of the clock. It cost 36 ± 17 Elo at 10+0.1: time spent early is worth more than time kept.

## 📦 What's in the box

The **`-complete.zip`** holds `machete.exe`, `machete.nnue`, `README.txt` and `SHA256SUMS.txt`. The other archives are CI's builds for Windows, Linux and macOS; they need `machete.nnue` beside them. Like 0.5.0, 0.5.1 reads three-layer networks only.

<details>
<summary><b>🧪 How it was tested</b></summary>

`check.sh` passes; the node-count signature moves from 197,209 to 209,573 because the search changed. With the repertoire and variety off, the packaged engine searches exactly the tree of the build the matches above were played with. New unit tests: losing captures order after every quiet move (fails with the old constant); a 5+0 game with 130 ms of lag a move keeps its clock for 120 moves (fails without the reserve); three credited ponder hits answer at once and the fourth searches afresh (fails without the credit).

</details>

---

<div align="center">

Built with **Mach 6.10.1** and **mach-std 9.5.0** · network C33F280P3ALL · trained on positions labelled by Stockfish and other engines; no engine's code is used

</div>
