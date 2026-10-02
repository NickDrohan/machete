<div align="center">

# ♞ machete 0.3.5

**A UCI chess engine written in [Mach](https://github.com/briar-systems/mach)**
*named for what it does to a variation tree*

![version](https://img.shields.io/badge/version-0.3.5-2ea44f?style=for-the-badge)
![platform](https://img.shields.io/badge/windows-x86--64-0078D6?style=for-the-badge&logo=windows)
![language](https://img.shields.io/badge/written%20in-Mach%206.5-8a2be2?style=for-the-badge)
![protocol](https://img.shields.io/badge/protocol-UCI-f39c12?style=for-the-badge)

![against 0.3.4](https://img.shields.io/badge/against%200.3.4-%2B18%20%C2%B1%2021-blue)
![positions](https://img.shields.io/badge/training%20positions-364M-blue)
![gates](https://img.shields.io/badge/acceptance%20gates-35%20passing-brightgreen)
![changes](https://img.shields.io/badge/changes-exactly%20one-lightgrey)

</div>

---

## 🎯 One change: network C33

0.3.5 changes **one thing**: the network. The search, the repertoire and every option are 0.3.4's.

C33 is C30's recipe plus **10.5 million more positions** from the data farm: the first half of pi-01's fourth run, Stockfish 19 against itself at 1,500 nodes a move from the broad opening book. 364 million positions in all, the same 768-wide shape.

| test | games | result |
|---|---|---|
| **C33 against C30** (0.3.4's network), same engine, 10+0.1 | 1,096 | **+18 ± 21** (258 wins, 638 draws, 200 losses) |

The test is sequential (SPRT, 0 to 10 Elo) and crossed its upper bound. It is the second step in a row where more of the farm's positions paid: 40 million gave C30 +16 over C28, and 10.5 million more give this.

## 🧪 What didn't make it

The **attack games mixed in once** (C32) ran 3,980 games against C30 without a verdict, slightly positive at most; three times over they had measured −18. They stay out of the main training. On the 3,114-position attack suite 0.3.4 finds 74.5% of the winning moves and 0.3.3 found 74.4%: more general data hasn't changed how machete attacks, which is the next thing to work on.

## 📦 What's in the box

The **`-complete.zip`** holds `machete.exe`, `machete.nnue` (C33), `README.txt` and `SHA256SUMS.txt`. The other archives are CI's builds for Windows, Linux and macOS; they need `machete.nnue` beside them. Every network since 0.3.2 loads in 0.3.5, and C33 loads in them.

<details>
<summary><b>🧪 How it was tested</b></summary>

The 35 gates in `check.sh` pass, among them the node-count signature (154,591, unchanged: bench doesn't load a network). The test above was played by the Mach match runner, game for game identical to the Python one it replaced.

</details>

---

<div align="center">

Built with **Mach 6.5.0** and **mach-std 9.2.0** · training positions labelled by Stockfish 19 and 16, Berserk, Alexandria, Obsidian, Caissa, PlentyChess and Reckless, and by the theoden8 corpus; no engine's code is used

</div>
