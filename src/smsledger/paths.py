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
EXAMPLES = PKG.parent.parent / "config"
