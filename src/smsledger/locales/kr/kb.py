"""KB Bank deposit/withdrawal notices. Keeps the case where a description slot holds an account number."""
from __future__ import annotations

import re

from ...registry import register
from ...util import MMDD_HM, _won, year_for
from .patterns import BAL, _plain


@register("kb_alert")
def parse_kb(text: str, ts: str) -> dict | None:
    if "등록되었습니다" in text or "통지서비스" in text or "부과예정" in text:
        return {"skip": "service"}
    lines = [ln.strip() for ln in _plain(text).splitlines() if ln.strip()]
    blob = " ".join(lines)
    hm = MMDD_HM.search(blob)
    mmdd = hhmm = day = ""
    if hm:
        mmdd = f"{int(hm.group(1)):02d}/{int(hm.group(2)):02d}"
        hhmm = f"{int(hm.group(3)):02d}:{int(hm.group(4)):02d}"
        y = year_for(ts, int(hm.group(1)), int(hm.group(2)))
        day = f"{y:04d}-{int(hm.group(1)):02d}-{int(hm.group(2)):02d}"
    acct = ""
    for ln in lines:
        if re.search(r"\d+\*{2,}\d+", ln):
            m2 = re.search(r"\*+(\d+)", ln)
            acct = m2.group(1) if m2 else re.sub(r"\D", "", ln)[-4:]
            break
    direction = "출금" if "출금" in blob else ("입금" if "입금" in blob else "")
    nums = [int(x.replace(",", "")) for x in re.findall(r"([0-9,]{4,})", blob)]
    # The amount line sits immediately before the balance line. Account numbers are
    # also runs of digits, so position -- not pattern -- is what tells them apart.
    amount = None
    bal_idx = next((i for i, ln in enumerate(lines) if BAL.search(ln)), None)
    if bal_idx is not None:
        for ln in reversed(lines[:bal_idx]):
            if re.fullmatch(r"[0-9,]+", ln):
                amount = _won(ln)
                break
    if amount is None:
        amount = nums[-2] if len(nums) >= 2 else (nums[-1] if nums else None)
    bal_m = BAL.search(blob)
    counterparty = ""
    for ln in lines:
        if "[KB]" in ln or "*" in ln or "잔액" in ln:
            continue
        if "출금" in ln or "입금" in ln:
            continue
        if re.fullmatch(r"[0-9,]+", ln):
            # KB prints the counterparty's account number on its own line where a
            # description would go. Ten or more digits with no grouping comma is that
            # number, not an amount or a balance. Drop it and a loan-interest
            # withdrawal becomes a row with no description, which later gets
            # classified as a fee instead of debt (found by measurement). Matched
            # against the loan tail in config it lands correctly, so pass it through.
            if "," not in ln and len(ln) >= 10:
                counterparty = ln
                break
            continue
        counterparty = ln
        break
    if amount is None:
        return None
    return {
        "kind": "bank_tx",
        "acct_tail": acct,
        "dir": direction,
        "amount": amount,
        "counterparty": counterparty,
        "desc": counterparty,
        "balance": _won(bal_m.group(1)) if bal_m else (nums[-1] if nums else None),
        "mmdd": mmdd,
        "hhmm": hhmm,
        "date": day,
        "source": "kb_alert",
    }
