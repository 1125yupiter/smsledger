"""Parser registry.

Adding support for a bank takes **one file in a locale package** plus one line
of config. This module is never edited: ``_load_all()`` walks the locale
packages and imports whatever it finds.

    # locales/in/hdfc.py
    from ...registry import register

    @register("hdfc_alert")
    def parse_hdfc(text: str, ts: str) -> dict | None:
        ...

Parser contract:

- Signature is ``(text: str, ts: str) -> dict | None``. ``ts`` is the time the
  message was received; pass it to ``util.year_for`` when the text omits a year.
- Return ``None`` if the message is not yours. Return ``{"skip": "<reason>"}``
  if it is yours but is not a transaction (a points notice, a signup receipt).
  Keeping these apart matters: the first means the sender config is wrong, the
  second is normal. Conflate them and you can never find what went missing.
- Return ``None`` when the amount could not be read. Never 0, never a guess.
- Required keys: ``kind``, ``amount``, ``date``, ``desc``, ``source``.
  ``kind`` is one of ``card_approve``, ``card_cancel``, ``bank_tx``. Anything
  that must not count as personal spending gets a prefix, e.g.
  ``corp_card_approve``, so a ledger built from these rows skips it.
"""
from __future__ import annotations

import importlib
import pkgutil
from typing import Callable

Parser = Callable[[str, str], "dict | None"]

REGISTRY: dict[str, Parser] = {}


def register(kind: str) -> Callable[[Parser], Parser]:
    """Bind a config ``kind`` to a parser. Registering a kind twice raises."""

    def wrap(fn: Parser) -> Parser:
        if kind in REGISTRY:
            raise RuntimeError(f"duplicate kind: {kind} ({fn.__name__})")
        REGISTRY[kind] = fn
        return fn

    return wrap


def _load_all() -> None:
    from . import locales

    for mod in pkgutil.iter_modules(locales.__path__):
        if mod.name.startswith("_"):
            continue
        pkg = importlib.import_module(f"{locales.__name__}.{mod.name}")
        for sub in pkgutil.iter_modules(pkg.__path__):
            if not sub.name.startswith("_"):
                importlib.import_module(f"{pkg.__name__}.{sub.name}")


def parse_row(row: dict) -> dict | None:
    """Route one collected row to the parser registered for its ``kind``."""
    kind = row.get("kind") or ""
    fn = REGISTRY.get(kind)
    if fn is None:
        return {"skip": "kind"}
    return fn(row.get("text") or "", row.get("ts") or "")


def kinds() -> list[str]:
    return sorted(REGISTRY)


_load_all()
