<div align="center">

# ♞ machete 0.3.4

**A UCI chess engine written in [Mach](https://github.com/briar-systems/mach)**
*named for what it does to a variation tree*

![version](https://img.shields.io/badge/version-0.3.4-2ea44f?style=for-the-badge)
![platform](https://img.shields.io/badge/windows-x86--64-0078D6?style=for-the-badge&logo=windows)
![language](https://img.shields.io/badge/written%20in-Mach%206.5-8a2be2?style=for-the-badge)
![protocol](https://img.shields.io/badge/protocol-UCI-f39c12?style=for-the-badge)

![against 0.3.3](https://img.shields.io/badge/against%200.3.3-%2B24%20%C2%B1%2024-blue)
![positions](https://img.shields.io/badge/training%20positions-353M-blue)
![gates](https://img.shields.io/badge/acceptance%20gates-35%20passing-brightgreen)
![changes](https://img.shields.io/badge/changes-exactly%20one-lightgrey)

</div>

---

## 🎯 One change: network C30

0.3.4 changes **one thing**: the network. The search, the repertoire and every option are 0.3.3's.

C30 is trained on 0.3.3's positions plus **40 million new ones** from the two Raspberry Pis of the data farm. The Pis played Stockfish 19 against itself, 1,500 nodes a move, from a broad book of opening positions. That makes 353 million positions in all, at the same 768-wide shape.

| test | games | result |
|---|---|---|
| **machete 0.3.3 with C30 against 0.3.3 as released**, 10+0.1 | 824 | **+24 ± 24** (204 wins, 474 draws, 146 losses) |
| C30 against C28 (the same recipe without the Pis' positions), 10+0.1 | 1,301 | +16 ± 19 |

Both tests are sequential (SPRT, 0 to 10 Elo), and both crossed their upper bound.

## 🧪 What didn't make it

The **attack games** from engine miniatures, mixed into the training three times over, were measured as their own step on top of C30. They came out **−18 ± 27** against C30 (626 games), so they're out. Attack knowledge is coming back in a form that only applies where an attack is on the board, rather than spread over every position. Two search changes, continuation history and capture history, also measured below zero and stayed out.

## 📦 What's in the box

The **`-complete.zip`** holds `machete.exe`, `machete.nnue` (C30), `README.txt` and `SHA256SUMS.txt`. The other archives are CI's builds for Windows, Linux and macOS; they need `machete.nnue` beside them. 0.3.2's and 0.3.3's networks load in 0.3.4, and C30 loads in both of them.

<details>
<summary><b>🧪 How it was tested</b></summary>

The 35 gates in `check.sh` pass, among them the node-count signature (154,591, unchanged: bench doesn't load a network). The two tests above were played by the Mach match runner, game for game identical to the Python one it replaced.

</details>

---

<div align="center">

Built with **Mach 6.5.0** and **mach-std 9.2.0** · training positions labelled by Stockfish 19 and 16, Berserk, Alexandria, Obsidian, Caissa, PlentyChess and Reckless, and by the theoden8 corpus; no engine's code is used

</div>
