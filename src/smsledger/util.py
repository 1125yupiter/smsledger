"""Country-neutral helpers shared by every locale.

Nothing here knows about a particular country's wording. Locale packages keep
their own patterns (see ``locales/kr/patterns.py``); this module only holds the
pieces that are the same everywhere.
"""
from __future__ import annotations

import re
from datetime import datetime

# Digit shapes are the same in every locale we have seen so far.
MMDD_HM = re.compile(r"(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})")
MMDD = re.compile(r"(\d{1,2})/(\d{1,2})")
ACCT_MASK = re.compile(r"(\d[\d*]{3,})")
AMT_BARE = re.compile(r"([0-9,]{3,})")

# Foreign-currency approvals carry an ISO code instead of a local amount.
# "USD 99.00" and the trailing "25.00(USD)" form both show up.
FX_AMT = re.compile(r"\b([A-Z]{3})\s+([0-9,]+(?:\.[0-9]+)?)\b")
FX_AMT_TRAIL = re.compile(r"([0-9,]+(?:\.[0-9]+)?)\s*\(\s*([A-Z]{3})\s*\)")


def won(s: str | None) -> int | None:
    """Parse a grouped integer, or None.

    Returns None rather than 0 on failure. In a ledger a zero-amount row is
    worse than a missing one: it looks settled.
    """
    if not s:
        return None
    try:
        return int(str(s).replace(",", ""))
    except ValueError:
        return None


def year_for(ts: str, month: int, day: int) -> int:
    """Infer the year for a month/day that arrived without one.

    Transaction texts routinely omit the year. Use the year the message was
    received, and subtract one when the month/day would land in the future --
    a notice cannot describe something that has not happened yet. This single
    rule is what keeps the new-year boundary from silently shifting a whole
    December into the wrong year.
    """
    try:
        rec = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return datetime.now().year
    y = rec.year
    try:
        cand = rec.replace(year=y, month=month, day=day)
    except ValueError:  # e.g. Feb 30 -- keep the received year
        return y
    return y - 1 if cand > rec else y


# Short aliases; locale parsers use these names.
_won = won
