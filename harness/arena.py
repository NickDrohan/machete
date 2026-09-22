"""Where the external engines live.

Four files used to carry this path independently, each with one machine's
username baked into it, so a second machine had to edit four files and a
shared repository advertised whose desktop the work was done on.

`MACHETE_ARENA` overrides it. The default assumes Arena's own default install
under the current user's Desktop, which is where its installer puts it, so the
common case needs no environment at all and no file names a person.

Nothing here checks that the engines exist. The callers do, because what they
should do about a missing engine differs: the rating ladder skips an opponent
it cannot find and says so, while the data generator has nothing to do without
one and should stop.
"""

import os

DEFAULT = os.path.join(os.path.expanduser("~"), "Desktop", "Games", "Chess",
                       "arena_3.5.1")

ROOT = os.environ.get("MACHETE_ARENA", DEFAULT)
ENGINES = os.path.join(ROOT, "Engines")


def engine(*parts):
    """A path under the Arena engine folder, from its components."""
    return os.path.join(ENGINES, *parts)


def installed():
    return os.path.isdir(ENGINES)


def explain():
    """What to tell someone whose engines are not where we looked."""
    return ("no Arena engine folder at {}\n"
            "set MACHETE_ARENA to the folder holding Arena's Engines "
            "directory".format(ENGINES))
