machete 0.3.1
=============

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
            0.3.1 reads 512-wide format 3 networks only; a 0.3.0 or 0.2
            network will not load.
  Ponder    supported: go ponder, ponderhit and stop.

Not supported yet: opening books, endgame tablebases, Chess960.


How strong
----------
Against machete 0.3.0, head to head at 10+0.1: +33 +/- 30 Elo over 596 games
(137 wins, 371 draws, 88 losses).
Against three outside engines at 2+1, on the same openings 0.3.0 played:
  Spike 1.4      49 wins,  9 draws,  2 losses   (0.3.0: 36, 19, 5)
  Rybka 2.3.2a   43 wins, 11 draws,  6 losses   (0.3.0: 40, 16, 4)
  Koivisto 9.0    1 win,  15 draws, 44 losses   (0.3.0:  0,  8, 52)
61% against them together where 0.3.0 scored 54%: roughly +50 Elo outside
machete's own family. On the CCRL Blitz scale (2+1, one CPU) that is somewhere
around 3050-3150; the reference engines disagree among themselves by hundreds
of Elo on modern hardware, so take the range, not a point. ASSESSMENT.md in
the repository has the games and the arithmetic.


What changed since 0.3.0
------------------------
Network: C20 - 8 king buckets x 768 inputs -> 512 -> 8 output layers, twice
0.3's width, trained on 262 million positions (C7's 154 million plus 10
million from the engine's own games labelled by Stockfish, and 98 million
Stockfish 16 depth 18-22 positions from the theoden8 corpus). The width alone
measured +29 +/- 28 at equal time against a 256-wide network on the same data.

Speed: the network's accumulator runs on AVX2 when the CPU has it, chosen at
start-up (the engine's first info line names the path): 13-20% more nodes
per second with this network, measured on AMD Zen 3, Zen 4 and Zen+ CPUs.
The move picker keeps its loop bounds in registers: +3.9%. The search is
0.3's, unchanged.

Built with Mach 6.5.0 and mach-std 9.2.0.


Credits
-------
Built with the Mach compiler 6.5.0 and mach-std 9.2.0. The network's training
positions were labelled by Stockfish, Berserk, Alexandria, Obsidian, Caissa,
PlentyChess and Reckless, and by the theoden8 corpus; no engine's code is used.
