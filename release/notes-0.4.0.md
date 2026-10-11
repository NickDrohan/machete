<div align="center">

# ♞ machete 0.4.0

**A UCI chess engine written in [Mach](https://github.com/briar-systems/mach)**
*named for what it does to a variation tree*

![version](https://img.shields.io/badge/version-0.4.0-2ea44f?style=for-the-badge)
![platform](https://img.shields.io/badge/windows-x86--64-0078D6?style=for-the-badge&logo=windows)
![language](https://img.shields.io/badge/written%20in-Mach%206.10-8a2be2?style=for-the-badge)
![protocol](https://img.shields.io/badge/protocol-UCI-f39c12?style=for-the-badge)

![against 0.3.6](https://img.shields.io/badge/against%200.3.6-%2B20%20%C2%B1%2022-blue)
![positions](https://img.shields.io/badge/training%20positions-504M-blue)
![gates](https://img.shields.io/badge/acceptance%20gates-35%20passing-brightgreen)
![changes](https://img.shields.io/badge/changes-exactly%20one-lightgrey)

</div>

---

## 🎯 One change: a network that has played from behind

0.4.0 changes **one thing**: the network. The search, the repertoire and every option are 0.3.6's.

The new network is 0.3.6's recipe, 364 million positions, plus **140 million of a new kind**: games Stockfish 19 played against itself from **Fischer Random (Chess960) starting positions in which one side begins worse off**. Not by a fixed handicap: two dozen kinds of trade (a pawn or two, the exchange with or without a pawn back, a queen for a rook and a minor piece, two minors for a rook, the bishop pair for a knight and a pawn), each kept only if Stockfish called the deficit real but not decisive, 60 to 350 centipawns. 20 million of the 140 come from trades that left the position balanced. 504 million positions in all, the same 768-wide shape.

Three more networks stacked on 0.3.6's data had gained nothing (C34 −3 ± 17, C35 +1 ± 14, the 0.4.0 match's C36 −11 ± 18). This is the first to pass.

| test against 0.3.6's network, same engine | games | result |
|---|---|---|
| 40,000 nodes a move | 600 | +27 ± 28 (163 wins, 320 draws, 117 losses) |
| **10+0.1** | 988 | **+20 ± 22** (226 wins, 592 draws, 170 losses) |
| **60+0.6** | 409 | **+32 ± 34** (81 wins, 285 draws, 43 losses) |
| **0.4.0 as packaged against 0.3.6 as released, 10+0.1** | 853 | **+22 ± 23** (211 wins, 484 draws, 158 losses) |

The three timed tests are sequential (SPRT, 0 to 10 Elo) and each crossed the upper bound.

## 🔬 What the data taught

The Fischer Random positions do not stand on their own. A network trained on 200 million of them and nothing else lost to one trained on 60 million ordinary positions (−54 ± 28) and to 0.3.6's by 144. Added to ordinary data they gain: +47 ± 28 on a 60-million-position network, and this release on the full recipe. What was missing from 364 million positions of strong self-play was not more of them but a different kind: positions where one side has to make something of less.

How much less matters. Varied small deficits helped more than balanced Fischer Random starts did (+83 against +44 for the same 20 million positions). A clean knight down did not help at all: a network trained only on classical positions played a knight down was 400 Elo weaker than one trained on level ones.

## 🧪 What didn't make it

A week of measuring how deep the teacher should search found that the label's depth hardly matters between 500 and 1,500 nodes (the same positions scored at either depth train the same network, +10 ± 28), that deep self-play is a narrow diet (at 15,000 nodes two positions in three come from drawn games), and that shallow data's early lead disappears with size (500 nodes ahead of 1,500 by 79 at 10 million positions, level at 30 million). None of it is in this network; all of it shapes the next.

## 📦 What's in the box

The **`-complete.zip`** holds `machete.exe`, `machete.nnue`, `README.txt` and `SHA256SUMS.txt`. The other archives are CI's builds for Windows, Linux and macOS; they need `machete.nnue` beside them. Every network since 0.3.2 loads in 0.4.0, and this one loads in them.

<details>
<summary><b>🧪 How it was tested</b></summary>

The 35 gates in `check.sh` pass, among them the node-count signature (154,921, unchanged: bench doesn't load a network, and the search is 0.3.6's). The engine is built with Mach 6.10.1 and mach-std 9.4.1, which play the same moves as 0.3.6's build a few percent faster; the network tests above were played on 0.3.6's own executable, and the packaged test on this one.

</details>

---

<div align="center">

Built with **Mach 6.10.1** and **mach-std 9.4.1** · training positions labelled by Stockfish 19 and 16, Berserk, Alexandria, Obsidian, Caissa, PlentyChess and Reckless, and by the theoden8 corpus; no engine's code is used

</div>
