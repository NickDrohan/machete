machete 0.3
===========

A UCI chess engine written in Mach (https://github.com/briar-systems/mach),
a low-level, explicitly typed systems language. Windows x86-64.

  machete.exe     the engine (no runtime or installer needed)
  machete.nnue    its evaluation network; keep it in the same folder


Using it in Arena (or any UCI GUI)
----------------------------------
1. Put both files in one folder, e.g. Arena\Engines\machete\.
2. Engines > Install New Engine > choose machete.exe; type UCI.
3. That's it. The engine loads machete.nnue from its own folder on start-up;
   the EvalFile option shows the path it loaded. If it shows <empty>, the
   network was not found and the engine is playing on its much weaker
   fallback evaluation - check the file is beside machete.exe.

Options:
  Threads   1 to 32 (default 1). Lazy SMP.
  Hash      fixed at 128 MB in this version; the option is accepted and ignored.
  EvalFile  path to a network file; defaults to machete.nnue beside the exe.
            0.3 reads network format 3 only; a 0.2 network will not load.
  Ponder    supported: go ponder, ponderhit and stop.

Not supported yet: opening books, endgame tablebases, Chess960.


How strong
----------
Against machete 0.2, head to head, one thread each, balanced openings, no
books, real clocks:
  +54 +/- 34 Elo over 200 games at 10+0.1 (66 wins, 99 draws, 35 losses)
  +60 +/- 41 Elo over 100 games at 60+0.6 (27 wins, 63 draws, 10 losses)
Against Koivisto 9.0 (CCRL 40/15 about 3300) at 60+0.6, 40 games:
  0 wins, 8 draws, 32 losses (0.2 scored 0 wins, 7 draws, 33 losses in the
  same match): roughly 380 Elo below it, and no wins yet against an engine
  of that class.
On an external scale: about 3000-3100 on the CCRL Blitz scale (2'+1", one
CPU), from 140 games against seven listed engines (Rybka 2.3.2a, Spike 1.4,
Koivisto 9.0, Ruffian 1.05, Hermann 2.8, SOS 5.1, AnMon 5.75) with their
published ratings held fixed. The anchors disagree among themselves by
several hundred Elo on this hardware, so take the range, not a point; the
three releases are within tens of Elo of each other on that scale, and the
head-to-head gains above overstate the external ones. ASSESSMENT.md in the
repository has the games and the arithmetic.


What changed since 0.2
----------------------
Evaluation: king buckets. Each side reads the board through one of 8 zones
chosen by where its own king stands, after mirroring the board so that king
is on files a-d. A king move into another zone rebuilds that side's half of
the network's first layer, only when the position is actually evaluated;
every other move stays incremental.

Network: C7 - 8 king buckets x 768 inputs -> 256 -> 8 output layers chosen by
the number of pieces left, int16, format 3. Trained on 153.7 million
positions: 0.2's 118.6 million plus 35.1 million quiet positions from the
theoden8 corpus (Lichess analysis at depth 18-22, mapped to our teachers'
centipawn scale).

The search is 0.2's, unchanged. Built with Mach 6.0.0, 2.6% faster than the
same code under 5.11.


Credits
-------
Built with the Mach compiler 6.0.0 and mach-std 9.0.0. The network's training
positions were labelled by Stockfish, Berserk, Alexandria, Obsidian, Caissa,
PlentyChess and Reckless, and by the theoden8 corpus; no engine's code is used.
