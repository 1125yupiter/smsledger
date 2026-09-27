"""Working directory: keep data out of the code tree.

    SMSLEDGER_HOME=~/smsledger python -m smsledger.collect

Defaults to ``./.smsledger``. Either way, **keep it outside the repository**.
``.gitignore`` covers the default, but financial data committed by accident
cannot be removed from history.
"""
from __future__ import annotations

import os
from pathlib import Path

HOME = Path(os.environ.get("SMSLEDGER_HOME") or (Path.cwd() / ".smsledger")).expanduser()
DATA = HOME / "data"
CONFIG = HOME / "config"
STREAM = DATA / "stream"

PKG = Path(__file__).resolve().parent

# Inside the package on purpose. These shipped defaults are what `setup` copies, so if
# they live next to the source tree instead they simply are not there after a
# `pip3 install` -- setup writes an empty configuration and the tool recognises nothing.
EXAMPLES = PKG / "examples"
