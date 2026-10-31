<div align="center">

# ♞ machete 0.5.3

**A UCI chess engine written in [Mach](https://github.com/briar-systems/mach)**
*named for what it does to a variation tree*

![version](https://img.shields.io/badge/version-0.5.3-2ea44f?style=for-the-badge)
![platform](https://img.shields.io/badge/windows-x86--64-0078D6?style=for-the-badge&logo=windows)
![language](https://img.shields.io/badge/written%20in-Mach%206.10-8a2be2?style=for-the-badge)
![protocol](https://img.shields.io/badge/protocol-UCI-f39c12?style=for-the-badge)

</div>

---

## 🎯 What changed

**It stops losing the same game twice.** The lichess bot's 2,959 games held one line played to move 25 and lost 15 times out of 15: machete repeats itself, and its opponents can walk the same path. The bot now keeps a record of every position it has played, how each move there turned out against what the opponents' ratings predicted, and a list of moves not to repeat, updated minutes after each game. When the search picks a listed move, the bot searches again without it and plays the replacement, unless the replacement looks more than a pawn worse. A repeated line is left at its earliest sound alternative.

The list was tested on games it never saw: moves flagged from the older 1,479 games scored 8.6% ± 3.7 below their rating expectation in the newer 1,480, against 2.9% ± 1.6 above it for all the others. If flagged moves did as well as the rest it would be worth about 11 Elo; that is an estimate, and only the bot's results can confirm it.

**`searchmoves` works.** The engine ignored this standard UCI command until now. It is what lets the bot leave a move out.

**The search and the network are 0.5.2's.** Search without `searchmoves` is node for node the same (209,573).

## 🧪 What was tried and left out

| change | at fixed nodes | on the clock (10+0.1) | |
|---|---|---|---|
| seven pruning changes together | +27 ± 9 | **−10 ± 7** (3,000 games) | out: 13% slower a node, three plies deeper and still worse |
| network with 99M imbalanced 15k positions | | +6 ± 12 (3,000 games) | out: not shown |
| that network with reduced search of checks | +13 ± 12 for the search change | −6 over 2,378 games | abandoned |
| contempt 20 | | −5 ± 12 | off |

Each pruning change is being measured alone on the clock for the next release. The lesson is the release's other result: depth bought with pruning is not strength, and a fixed-node win does not survive the clock by itself.

## 📦 What's in the box

The **`-complete.zip`** holds `machete.exe`, `machete.nnue` (0.5.1's network, unchanged), `README.txt` and `SHA256SUMS.txt`. The other archives are CI's builds for Windows, Linux and macOS; they need `machete.nnue` beside them.

`bot/` in the repository has the lichess-bot changes machete runs on: reconnecting a game's stream, not starting a game twice when the event stream reconnects, avoiding listed moves, the options sent each game. `harness/experience_build.py` builds the record and the list.

<details>
<summary><b>🧪 How it was tested</b></summary>

`check.sh` passes; the node-count signature is unchanged (209,573). A new test holds the root to a `searchmoves` list and checks a search with no list is free again. Against the real engine at 8 threads, the bot's check switched a listed move for another, kept a mate in one when it was listed, did nothing for a move not listed, with the list missing, or with every legal move listed.

</details>

---

<div align="center">

Built with **Mach 6.10.1** and **mach-std 9.5.0** · network C33F280P3ALL, unchanged from 0.5.1 · no engine's code is used

</div>
