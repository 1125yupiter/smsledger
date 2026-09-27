"""Foreign-currency approvals. No local amount in the text, so it is estimated."""
from __future__ import annotations


from ...config import fx_settings
from ...util import FX_AMT, FX_AMT_TRAIL, MMDD_HM, year_for


def parse_fx_approve(lines: list[str], text: str, ts: str, source: str) -> dict | None:
    """Foreign-currency approval: read the ISO code and amount, estimate the local one."""
    blob = " ".join(lines)
    m = FX_AMT.search(blob) or FX_AMT_TRAIL.search(blob)
    if not m:
        return None
    if m.re is FX_AMT:
        cur, raw = m.group(1), m.group(2)
    else:
        raw, cur = m.group(1), m.group(2)
    try:
        fx_amount = float(raw.replace(",", ""))
    except ValueError:
        return None

    mmdd = hhmm = ""
    day = ""
    for ln in lines:
        hm = MMDD_HM.search(ln)
        if hm:
            mo, da = int(hm.group(1)), int(hm.group(2))
            mmdd = f"{mo:02d}/{da:02d}"
            hhmm = f"{int(hm.group(3)):02d}:{int(hm.group(4)):02d}"
            day = f"{year_for(ts, mo, da):04d}-{mo:02d}-{da:02d}"
            break
    if not day and ts:
        day = ts[:10]

    # The merchant is the last line. If it collides with the amount or date line,
    # leave it empty rather than guessing.
    merchant = ""
    for ln in reversed(lines):
        if FX_AMT.search(ln) or FX_AMT_TRAIL.search(ln) or MMDD_HM.search(ln):
            continue
        if "해외승인" in ln or ln.endswith("님"):
            continue
        merchant = ln
        break

    # The billed local amount is fixed at the rate on the settlement date, so an
    # approval notice cannot know it. An estimate is still needed to reserve cash in
    # the settlement account, so convert at the configured rate and flag it
    # `estimated`. The statement, when it arrives, replaces this number.
    fx = fx_settings()
    rate = fx["rates"].get(cur)
    amount = round(fx_amount * rate * fx["fee_rate"]) if rate else None
    cancelled = "취소" in text
    return {
        "kind": "card_cancel" if cancelled else "card_approve",
        "amount": amount,
        "estimated": True,
        "currency": cur,
        "fx_amount": fx_amount,
        "fx_rate_used": rate,
        "installment": "",
        "mmdd": mmdd,
        "hhmm": hhmm,
        "merchant": merchant,
        "date": day,
        "desc": f"{merchant} ({cur} {fx_amount:,.2f})".strip(),
        "source": source,
    }
