"""The engines that stand in for "strong play", and how to open one.

Every engine here is a top-tier modern program. That matters more than it
sounds: the point of a panel is that no single program's judgement becomes the
ground truth, so the members have to be close enough in strength that none of
them is obviously the one to believe.

Engines are opened in their own directory. Several read a config file from the
working directory and, when it is missing, answer with blank lines rather than
saying so, which the UCI layer then turns into an assertion on every line.
"""

import os

ARENA = r"~\Desktop\Games\Chess\arena_3.5.1\Engines"

# name -> path relative to the Arena engine folder
PANEL = {
    "Stockfish":   r"Stockfish\stockfish\stockfish-windows-x86-64-avx2.exe",
    "Berserk":     r"berserk\berserk-13-ssse3.exe",
    "Alexandria":  r"Alexandria 8.1.12\Alexandria-8.1.12-avx2.exe",
    "Obsidian":    r"Obsidian160-avx2.exe",
    "Caissa":      r"Caissa\caissa-1.23-x64-sse2.exe",
    "Seer":        r"Seer\seer_v2.8_x64_avx2_popcnt.exe",
    "PlentyChess": r"Plenty\PlentyChess-7.0.0-windows-ssse3.exe",
    "Dragon":      r"Dragon\dragon_05e2a7\Windows\dragon-64bit-avx2.exe",
    "Reckless":    r"Reckless 0.9.0 dev-2a847427\reckless-windows-avx2.exe",
    "Koivisto":    r"Koi\Koivisto_9.0-windows-sse2-pgo.exe",
}


def path_of(name):
    return os.path.join(ARENA, PANEL[name])


def open_engine(name, hash_mb=64):
    import chess.engine
    path = path_of(name)
    engine = chess.engine.SimpleEngine.popen_uci(
        path, timeout=30, cwd=os.path.dirname(path))
    try:
        engine.configure({"Threads": 1, "Hash": hash_mb})
    except Exception:
        pass  # an engine without these options is still usable
    return engine


def quiet_quit(engine):
    try:
        engine.quit()
    except Exception:
        pass
