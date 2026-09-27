"""User-facing strings, in the reader's language.

Code, comments and documentation stay in English so anyone can contribute. What a
person actually reads on screen does not: the first people to use this are not
developers, and an English-only prompt is a wall before the tool has done anything.

Adding a language is **one JSON file** in ``messages/``, the same size of
contribution as adding a bank parser. Missing keys fall back to English rather
than failing, so a partial translation is useful immediately.

    from .i18n import t
    print(t("setup.title"))
"""
from __future__ import annotations

import json
import os
import subprocess
from functools import lru_cache
from pathlib import Path

MESSAGES = Path(__file__).resolve().parent / "messages"
FALLBACK = "en"


def available() -> list[str]:
    return sorted(p.stem for p in MESSAGES.glob("*.json"))


def _from_macos() -> str:
    """macOS leaves LANG unset in Terminal and in launchd, so ask the OS directly.

    Without this a Korean Mac reports no locale at all and everyone gets English --
    which is precisely the reader this exists for.
    """
    try:
        out = subprocess.run(
            ["defaults", "read", "-g", "AppleLocale"],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


def detect() -> str:
    """Explicit choice, then config, then the OS. English if nothing matches."""
    have = set(available())

    env = (os.environ.get("SMSLEDGER_LANG") or "").strip()
    if env:
        return env if env in have else FALLBACK

    try:
        from .config import load

        want = (load("profile").get("language") or "").strip()
        if want:
            return want if want in have else FALLBACK
    except Exception:
        pass

    for raw in (_from_macos(), os.environ.get("LC_ALL", ""), os.environ.get("LANG", "")):
        code = raw.replace("-", "_").split(".")[0].split("_")[0].lower()
        if code and code in have:
            return code
    return FALLBACK


@lru_cache(maxsize=None)
def _catalog(lang: str) -> dict:
    path = MESSAGES / f"{lang}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


_current: list[str] = []


def set_language(lang: str | None) -> str:
    _current.clear()
    _current.append(lang or detect())
    return _current[0]


def language() -> str:
    if not _current:
        _current.append(detect())
    return _current[0]


def t(key: str, **kw) -> str:
    """Look up a string. Falls back to English, then to the key itself.

    A missing key must never crash or blank the screen -- a half-finished
    translation should still leave a usable tool.
    """
    text = _catalog(language()).get(key) or _catalog(FALLBACK).get(key) or key
    if kw:
        try:
            return text.format(**kw)
        except (KeyError, IndexError, ValueError):
            return text
    return text
