machete 0.1
===========

A UCI chess engine written in Mach (https://github.com/briar-systems/mach),
a low-level, explicitly typed systems language. Windows x86-64.

  machete.exe     the engine (220 KB, no runtime or installer needed)
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
  Threads   1 to 32 (default 1). Lazy SMP; 8 threads measured +144 Elo over 1.
  Hash      fixed at 128 MB in this version; the option is accepted and ignored.
  EvalFile  path to a network file; defaults to machete.nnue beside the exe.

Not supported yet: pondering (leave "ponder" off in the GUI), opening books,
endgame tablebases, Chess960.


How strong
----------
Roughly 3100-3200 on the CCRL 40/15 scale, single thread, at 3 minutes + 2
seconds - measured against Spike 1.4 and Rybka 2.3.2a (40 games each, openings
chosen by the engines themselves, no books). That is an estimate with a wide
error bar, not a rating list entry. It loses clearly to modern top engines
(0 wins in 40 games against Koivisto 9.0). It still converts some won endings
slowly: queen against knight, queen against rook and two bishops against a
lone king are sometimes drawn by the fifty-move rule.


Under the hood
--------------
Search: iterative deepening principal variation search with a transposition
table, null-move pruning, late-move reductions, futility and reverse futility
pruning, aspiration windows, and quiescence with check evasions. Magic
bitboards, hardware bit scans.

Evaluation: a 768 -> 256 -> 1 NNUE, int16, trained on 63.6 million positions
from self-play games of five engines - Stockfish, Berserk, Alexandria,
Obsidian and Caissa - each position scored by that engine's own search at
1,500 nodes.


Credits
-------
Built with the Mach compiler 5.11.0 and mach-std 7.1. The network's training
positions were labelled by the engines named above; no engine's code is used.
