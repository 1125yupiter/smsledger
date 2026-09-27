"""Hana Bank deposit/withdrawal notices. The masked tail identifies the account."""
from __future__ import annotations

import re

from ...registry import register
from ...util import ACCT_MASK, _won, year_for
from .patterns import AMT, BAL, _plain


@register("hana_alert")
def parse_hana(text: str, ts: str) -> dict | None:
    lines = [ln.strip() for ln in _plain(text).replace("\r\n", "\n").splitlines() if ln.strip()]
    blob = " ".join(lines)
    acct = ""
    for ln in lines:
        m = ACCT_MASK.search(ln.replace("-", ""))
        if m and "*" in ln:
            acct = re.sub(r"\D", "", ln)[-5:] or m.group(1)[-5:]
            break
    if not acct:
        m = re.search(r"(\d{3}\*{2,}\d{5}|\d+\*{2,}\d+)", blob)
        if m:
            acct = re.sub(r"\D", "", m.group(1))[-5:]
    direction = "출금" if "출금" in blob else ("입금" if "입금" in blob else "")
    amount = None
    m = re.search(r"(?:출금|입금)\s*([0-9,]+)\s*원", blob)
    if m:
        amount = _won(m.group(1))
    if amount is None:
        m = AMT.search(blob)
        amount = _won(m.group(1)) if m else None
    bal_m = BAL.search(blob)
    desc = ""
    for ln in lines:
        if "하나" in ln or "****" in ln or "출금" in ln or "입금" in ln or "잔액" in ln:
            continue
        desc = ln
        break
    hm = re.search(r"하나,(\d{1,2})/(\d{1,2})[,\s]+(\d{1,2}):(\d{2})", blob)
    mmdd = hhmm = ""
    day = ""
    if hm:
        mmdd = f"{int(hm.group(1)):02d}/{int(hm.group(2)):02d}"
        hhmm = f"{int(hm.group(3)):02d}:{int(hm.group(4)):02d}"
        y = year_for(ts, int(hm.group(1)), int(hm.group(2)))
        day = f"{y:04d}-{int(hm.group(1)):02d}-{int(hm.group(2)):02d}"
    if amount is None:
        return None
    return {
        "kind": "bank_tx",
        "acct_tail": acct,
        "dir": direction,
        "amount": amount,
        "desc": desc,
        "balance": _won(bal_m.group(1)) if bal_m else None,
        "mmdd": mmdd,
        "hhmm": hhmm,
        "date": day,
        "source": "hana_alert",
    }
