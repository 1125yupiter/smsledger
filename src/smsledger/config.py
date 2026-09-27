"""Configuration loader.

Lookup order is ``$SMSLEDGER_HOME/config/<name>.json``, then the repository's
``config/<name>.example.json``, then the code defaults. Missing files are fine;
present ones override shallowly, per top-level key.

What goes into config is decided by one question -- **"does the buyer have to
supply their own value?"** -- not by whether something looks private. A
landlord's name moves out because yours is different, not because it is secret.
"""
from __future__ import annotations

import json
from functools import lru_cache

from .paths import CONFIG, EXAMPLES

DEFAULTS: dict[str, dict] = {
    "sources": {"sms": [], "mail": []},
    "profile": {
        "accounts": [],
        "loans": [],
        "self_patterns": [],
        "spend_tiers": [500_000, 1_000_000, 2_000_000],
        # Card-network fee ~1% plus issuer ~0.2%. Adjust the rate here when it moves.
        "fx": {"rates": {"USD": 1410.0}, "fee_rate": 1.012},
    },
}


@lru_cache(maxsize=None)
def load(name: str) -> dict:
    out = dict(DEFAULTS.get(name) or {})
    for path in (EXAMPLES / f"{name}.example.json", CONFIG / f"{name}.json"):
        if not path.exists():
            continue
        try:
            out.update(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"could not read config: {path} -- {exc}") from exc
    return out


def sources() -> dict:
    return load("sources")


def profile() -> dict:
    return load("profile")


def account_tails() -> set[str]:
    """Your own account/card tails, from config rather than hardcoded."""
    p = profile()
    return {
        str(a["tail"])
        for a in list(p.get("accounts") or []) + list(p.get("loans") or [])
        if a.get("tail")
    }


def fx_settings() -> dict:
    fx = dict(DEFAULTS["profile"]["fx"])
    fx.update(profile().get("fx") or {})
    return fx
