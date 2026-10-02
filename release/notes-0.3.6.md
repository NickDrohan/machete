<div align="center">

# ♞ machete 0.3.6

**A UCI chess engine written in [Mach](https://github.com/briar-systems/mach)**
*named for what it does to a variation tree*

![version](https://img.shields.io/badge/version-0.3.6-2ea44f?style=for-the-badge)
![platform](https://img.shields.io/badge/windows-x86--64-0078D6?style=for-the-badge&logo=windows)
![language](https://img.shields.io/badge/written%20in-Mach%206.5-8a2be2?style=for-the-badge)
![protocol](https://img.shields.io/badge/protocol-UCI-f39c12?style=for-the-badge)

![against 0.3.5](https://img.shields.io/badge/against%200.3.4-%2B2%20%C2%B1%2017-blue)
![positions](https://img.shields.io/badge/training%20positions-364M-blue)
![gates](https://img.shields.io/badge/acceptance%20gates-35%20passing-brightgreen)
![changes](https://img.shields.io/badge/changes-exactly%20one-lightgrey)

</div>

---

## 🎯 One change: the search stops pruning an attack on its own king

0.3.6 changes **one thing**: the search. The network is 0.3.5's (C33), and so is everything else.

On lichess 0.3.3 took a pawn with 19.Nxc7 and was mated in five: 19...Re5 20.Nd5 Bf3 21.exf3 exf3 and Qg2# follows. Black's queen was already on h3. The mating moves are quiet ones, a rook lift and a bishop offered, by a side that was behind in material, and those are exactly the moves the search prunes near the horizon and reduces everywhere else. 0.3.4 needed depth 22 to see it.

Now, when the side to move has its queen within two squares of the enemy king, its quiet moves are not pruned by futility or late-move pruning, and are reduced one ply less.

| test | result |
|---|---|
| the position before 19.Nxc7 | 19.Bxc7 found from **depth 18** (0.3.4: depth 22); at depth 22, 26 s instead of 91 s |
| against 0.3.4, same network, 10+0.1, 1,673 games | **+2 ± 17**: no cost (SPRT, −10 to 0, upper bound) |
| **0.3.6 as packaged against 0.3.5 as released**, 10+0.1, 3,253 games | **−1 ± 12** (524 wins, 2,193 draws, 536 losses): no cost (SPRT, −10 to 0, upper bound) |
| nodes at a fixed depth (bench) | 154,591 → 154,921, +0.2% |

It is a safety fix. Equal engines rarely attack each other's kings the way a stronger opponent does, so self-play shows that it is free, and the game shows what it is for.

## 🧪 What didn't make it

**A faster clock in the opening** (the first ten moves on 46% to 100% of the usual budget): lichess opponents play their first ten moves in 2.9 s each from book and machete took 6.6 s, but from the start position against itself the change measured nothing after 3,820 games, so it waits for a test against booked opponents. **More of the same data** (C34, all 19.3M positions of the Pi's run): −3 ± 17 against C33. The farm's self-play positions have stopped paying; the next network needs a different kind of data.

## 📦 What's in the box

The **`-complete.zip`** holds `machete.exe`, `machete.nnue` (C33, 0.3.6's own), `README.txt` and `SHA256SUMS.txt`. The other archives are CI's builds for Windows, Linux and macOS; they need `machete.nnue` beside them. Every network since 0.3.2 loads in 0.3.6.

<details>
<summary><b>🧪 How it was tested</b></summary>

The 35 gates in `check.sh` pass, among them the node-count signature (154,921, updated for this change). The test above was played by the Mach match runner, game for game identical to the Python one it replaced.

</details>

---

<div align="center">

Built with **Mach 6.5.0** and **mach-std 9.2.0** · training positions labelled by Stockfish 19 and 16, Berserk, Alexandria, Obsidian, Caissa, PlentyChess and Reckless, and by the theoden8 corpus; no engine's code is used

</div>
