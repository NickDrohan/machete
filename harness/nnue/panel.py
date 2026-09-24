"""The engines that stand in for "strong play", and how to open one.

Every engine here is a top-tier modern program. That matters more than it
sounds: the point of a panel is that no single program's judgement becomes the
ground truth, so the members have to be close enough in strength that none of
them is obviously the one to believe.

Engines are opened in their own directory. Several read a config file from the
working directory and, when it is missing, answer with blank lines rather than
saying so, which the UCI layer then turns into an assertion on every line.

Every path here names a build this machine can actually run. An engine shipped
as several binaries will happily include an avx512 one, and on a Zen+ chip that
dies with an illegal instruction the moment it is asked to think - which looks
like a flaky engine rather than the wrong file. Seer was dropped for being the
weakest evaluator the gold set measured (rmse 0.095 against 0.064); its avx2
build runs fine if it is ever wanted back.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import arena
import engine as engines

ARENA = arena.ENGINES

# name -> path relative to the Arena engine folder
PANEL = {
    "Stockfish":   r"Stockfish\stockfish\stockfish-windows-x86-64-avx2.exe",
    "Berserk":     r"berserk\berserk-13-ssse3.exe",
    "Alexandria":  r"Alexandria 8.1.12\Alexandria-8.1.12-avx2.exe",
    "Obsidian":    r"Obsidian160-avx2.exe",
    "Caissa":      r"Caissa\caissa-1.23-x64-sse2.exe",
    "PlentyChess": r"Plenty\PlentyChess-7.0.0-windows-ssse3.exe",
    "Dragon":      r"Dragon\dragon_05e2a7\Windows\dragon-64bit-avx2.exe",
    "Reckless":    r"Reckless 0.9.0 dev-2a847427\reckless-windows-avx2.exe",
    "Koivisto":    r"Koi\Koivisto_9.0-windows-sse2-pgo.exe",
    # jnlt3/blackmarlin release 9.0, x86-64-v3 (AVX2) build; sha256 9fbc60c2...a756748
    "BlackMarlin": r"BlackMarlinlackmarlin-windows-x86-64-v3.exe",
}


# MACHETE_PANEL names a JSON file mapping panel names to absolute paths, which
# replaces the Arena layout above. It is how a Linux machine, which has no
# Arena folder and builds its teachers from source, points the same code at its
# own binaries. harness/cloud/teacher_check.py proves those binaries score
# positions exactly as the ones above do before any of their labels are used.
OVERRIDE = {}
if os.environ.get("MACHETE_PANEL"):
    import json
    with open(os.environ["MACHETE_PANEL"]) as handle:
        OVERRIDE = json.load(handle)


def path_of(name):
    if OVERRIDE:
        if name not in OVERRIDE:
            raise KeyError("{} is not in the MACHETE_PANEL file {}".format(
                name, os.environ["MACHETE_PANEL"]))
        return OVERRIDE[name]
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
    # Dragon ships with OwnBook on; a teacher answering from a book gives no score
    if "OwnBook" in engine.options:
        engine.configure({"OwnBook": False})
    return engine


def quiet_quit(engine):
    return engines.shutdown(engine)
