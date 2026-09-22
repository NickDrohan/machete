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

import chess.engine


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
