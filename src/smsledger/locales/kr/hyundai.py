"""Hyundai Card usage notices: cancellations, instalments, running total, FX."""
from __future__ import annotations

from datetime import datetime

from ...registry import register
from ...util import MMDD_HM, _won, year_for
from .patterns import AMT, CARD_CANCEL, _plain
from .fx import parse_fx_approve


@register("hyundai_card")
def parse_hyundai(text: str, ts: str) -> dict | None:
    if "M포인트" in text or "잔여" in text and "P" in text:
        return {"skip": "mpoint"}
    cancel = CARD_CANCEL.search(_plain(text).replace("\n", " "))
    if cancel:
        mo, da = int(cancel.group(1)), int(cancel.group(2))
        y = year_for(ts, mo, da)
        merchant = cancel.group(3).strip()
        return {
            "kind": "card_cancel",
            "amount": _won(cancel.group(4)),
            "mmdd": f"{mo:02d}/{da:02d}",
            "merchant": merchant,
            "date": f"{y:04d}-{mo:02d}-{da:02d}",
            "desc": merchant,
            "source": "hyundai_card",
        }
    if "승인" not in text:
        return None
    lines = [ln.strip() for ln in _plain(text).splitlines() if ln.strip()]
    if "해외승인" in text:
        return parse_fx_approve(lines, text, ts, "hyundai_card")
    amount = None
    installment = ""
    merchant = ""
    mmdd = ""
    hhmm = ""
    after_date = ""
    cumulative = None
    for i, ln in enumerate(lines):
        # Since 2026-09-14 a trailing line like "누적1,234,567원" is appended. It is
        # neither the charge nor the merchant -- it is the issuer's own running total
        # for this billing cycle, which beats any total we sum up from notices.
        if ln.startswith("누적"):
            m = AMT.search(ln)
            if m:
                cumulative = _won(m.group(1))
            continue
        m = AMT.search(ln)
        if m and "원" in ln:
            amount = _won(m.group(1))
            if "일시불" in ln:
                installment = "일시불"
            elif "할부" in ln:
                installment = ln
        hm = MMDD_HM.search(ln)
        if hm:
            mmdd = f"{int(hm.group(1)):02d}/{int(hm.group(2)):02d}"
            hhmm = f"{int(hm.group(3)):02d}:{int(hm.group(4)):02d}"
            rest = ln[hm.end():].strip()
            if rest:
                merchant = rest
            elif i + 1 < len(lines) and not lines[i + 1].startswith("누적"):
                after_date = lines[i + 1]
    if not merchant:
        merchant = after_date
    if not merchant and lines:
        merchant = lines[-1]
    if amount is None:
        return None
    mo, da = (int(x) for x in mmdd.split("/")) if mmdd else (0, 0)
    y = year_for(ts, mo, da) if mo else (int(ts[:4]) if ts else datetime.now().year)
    day = f"{y:04d}-{mo:02d}-{da:02d}" if mo else ""
    return {
        "kind": "card_approve",
        "amount": amount,
        "installment": installment,
        "cumulative": cumulative,
        "mmdd": mmdd,
        "hhmm": hhmm,
        "merchant": merchant,
        "date": day,
        "desc": merchant,
        "source": "hyundai_card",
    }
