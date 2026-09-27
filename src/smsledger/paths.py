"""Working directory: keep data out of the code tree.

    SMSLEDGER_HOME=~/krsms python -m smsledger.collect

Defaults to ``~/smsledger``: **one ledger, in one place, whatever directory you
happen to be standing in.** It used to default to ``./.smsledger``, and that is
the same sentence as "wherever you happen to be standing" -- which meant `setup`
filled one ledger, the next command read an empty second one and said so, and a
third appeared in every folder anyone ran a command from. Each copy held real
financial data.

Either way, **keep it outside the repository**: financial data committed by
accident cannot be removed from history.
"""
from __future__ import annotations

import os
from pathlib import Path

# The single source of truth for where data lives. `setup` must not carry its own
# idea of this -- two defaults is how the ledger splits in half.
DEFAULT_HOME = Path.home() / "smsledger"

HOME = Path(os.environ.get("SMSLEDGER_HOME") or DEFAULT_HOME).expanduser()
DATA = HOME / "data"
CONFIG = HOME / "config"
STREAM = DATA / "stream"

PKG = Path(__file__).resolve().parent

# Inside the package on purpose. These shipped defaults are what `setup` copies, so if
# they live next to the source tree instead they simply are not there after a
# `pip3 install` -- setup writes an empty configuration and the tool recognises nothing.
EXAMPLES = PKG / "examples"
