"""Shutting a UCI engine down so that it actually goes away.

Eight places in this harness used to end an engine with

    try:
        engine.quit()
    except Exception:
        pass

which leaks the process whenever the engine is not reading its input. The
reason is worth writing down, because the failure is silent and the code looks
careful:

`SimpleEngine.quit()` sends `quit` and waits for the engine to exit, under a
ten second timeout. An engine stuck in a search is not reading stdin, so the
`quit` is never seen, the wait times out, and `asyncio.TimeoutError` comes back
- which `except Exception` swallows. The engine is then still running, its
parent exits, and it is reparented and left behind. Nothing anywhere calls
`close()`, which is the part that actually closes the transport and terminates
the subprocess.

One such process outlived its parent by 63 hours on this machine, burning 46
CPU-hours, and could not be killed from another session because it was
attached to a different console. That is the bug this module exists to stop.

Asking politely first is still right: an engine given `quit` writes out
whatever it wants to write and exits cleanly. `close()` is the guarantee that
it goes away regardless.
"""

import os

import chess.engine

# Where the built engine lands, mirroring mach.toml's
#   out = "out/{target.name}/{profile.name}"  +  out = "bin/machete{suffix}"
#
# Four files used to spell this out independently, which is the same shape of
# duplication as the Arena path and fails the same way: change the target or
# the out layout and they break one at a time. MACHETE_BIN overrides it, which
# is also how an A/B run points at a renamed copy.
#
# For running the engine by hand, prefer `mach run . --profile release -- bench`
# over any path at all - it resolves the artifact from the manifest. This
# constant exists because python-chess needs a real path to popen, and because
# an A/B match points at two renamed binaries that no manifest describes.
HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)


def built(target="windows-x86_64", profile="release", name="machete.exe"):
    """The path a `mach build` of this product leaves behind."""
    return os.path.join(PRODUCT, "out", target, profile, "bin", name)


MACHETE = os.environ.get("MACHETE_BIN", built())

# what engines call their thread count, in the order they are tried
THREAD_OPTIONS = ("Threads", "Max CPUs", "Cores", "CPUs")


def pin(engine, hash_mb=128):
    """One search thread, a fixed hash and no opening book of its own.

    A rating is only a rating of the engine if its resources are fixed, not
    whatever its defaults happen to be. AnMon, SOS, Hermann and Spike ship with
    OwnBook on, so until this turned it off they played their openings from a
    book - instantly - while machete and Rybka searched theirs. Returns the thread option that was set,
    or None when the engine has none - which the caller must report, since that
    engine is then single-threaded only by assumption. The hash is clamped to
    the range the engine declares.
    """
    chosen = None
    for name in THREAD_OPTIONS:
        if name in engine.options:
            engine.configure({name: 1})
            chosen = name
            break
    if "OwnBook" in engine.options:
        engine.configure({"OwnBook": False})
    if "Hash" in engine.options:
        option = engine.options["Hash"]
        size = hash_mb
        if option.max is not None:
            size = min(size, option.max)
        if option.min is not None:
            size = max(size, option.min)
        engine.configure({"Hash": size})
    return chosen


def shutdown(engine):
    """End an engine, politely if it will and forcibly if it will not.

    Safe to call on an engine that has already gone, and safe to call twice.
    Returns True if `quit` was accepted, False if it had to be closed out -
    which callers generally ignore, but a soak test can assert on.
    """
    if engine is None:
        return True
    clean = False
    try:
        engine.quit()
        clean = True
    except Exception:
        # timed out, already dead, or the pipe is gone: close() handles all three
        pass
    try:
        engine.close()
    except Exception:
        pass
    return clean
