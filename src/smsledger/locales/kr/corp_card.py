"""Corporate card notices. Not personal spending, so its ``kind`` is kept separate."""
from __future__ import annotations

import re

from ...registry import register
from ...util import MMDD_HM, _won, year_for
from .patterns import AMT, CORP_CARD_TAIL, REMAIN, _plain


@register("corp_card")
def parse_corp_card(text: str, ts: str) -> dict | None:
    """Corporate card notice (marked "NNNN(기업)").

    This is not personal spending. The kind is prefixed corp_card_* so a ledger or
    spend analysis built from these rows leaves it out. The "잔여" figure is the
    remaining monthly limit, so the gap between two consecutive notices should equal
    what was spent in between -- a cheap way to detect a missed message.
    """
    lines = [ln.strip() for ln in _plain(text).splitlines() if ln.strip()]
    blob = " ".join(lines)
    tail_m = CORP_CARD_TAIL.search(blob)
    if not tail_m:
        return None
    remain_m = REMAIN.search(blob)
    mmdd = hhmm = day = ""
    hm = MMDD_HM.search(blob)
    if hm:
        mo, da = int(hm.group(1)), int(hm.group(2))
        mmdd = f"{mo:02d}/{da:02d}"
        hhmm = f"{int(hm.group(3)):02d}:{int(hm.group(4)):02d}"
        day = f"{year_for(ts, mo, da):04d}-{mo:02d}-{da:02d}"
    amount = None
    amt_idx = None
    for i, ln in enumerate(lines):
        if "잔여" in ln:
            continue
        m = re.fullmatch(r"([0-9,]+)\s*원", ln)
        if m:
            amount = _won(m.group(1))
            amt_idx = i
            break
    if amount is None:
        for ln in lines:
            if "잔여" in ln:
                continue
            m = AMT.search(ln)
            if m:
                amount = _won(m.group(1))
                break
    merchant = ""
    if amt_idx is not None:
        for ln in lines[amt_idx + 1:]:
            if "잔여" in ln or re.fullmatch(r"[0-9,]+\s*원?", ln):
                continue
            merchant = ln
            break
    if amount is None:
        return None
    cancelled = "취소" in blob
    return {
        "kind": "corp_card_cancel" if cancelled else "corp_card_approve",
        "amount": amount,
        "card_tail": tail_m.group(1),
        "merchant": merchant,
        "remaining": _won(remain_m.group(1)) if remain_m else None,
        "mmdd": mmdd,
        "hhmm": hhmm,
        "date": day,
        "desc": merchant,
        "source": "kb_corp_card",
    }
