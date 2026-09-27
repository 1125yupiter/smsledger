"""South Korean wording. Everything country-specific lives here.

These are the words Korean banks and card issuers put in their notices. A new
locale writes its own file like this one rather than extending these.
"""
from __future__ import annotations

import re

AMT = re.compile(r"([0-9,]+)\s*원")               # amount, "12,300원"
BAL = re.compile(r"잔액\s*([0-9,]+)")              # balance
DIR = re.compile(r"(출금|입금)")                   # withdrawal / deposit
REMAIN = re.compile(r"잔여\s*([0-9,]+)")           # remaining monthly limit
CORP_CARD_TAIL = re.compile(r"(\d{4})\s*\(\s*기업\s*\)")   # "1234(기업)" = corporate
# Cancellations arrive as a single line: "09/18 <merchant> 사용 3,500원 취소처리"
CARD_CANCEL = re.compile(r"(\d{1,2})/(\d{1,2})\s+(.+?)\s+사용\s+([0-9,]+)\s*원\s*취소처리")

WEB_PREFIX = "[Web발신]"   # Korean carriers prepend this to forwarded SMS


def plain(text: str) -> str:
    return (text or "").replace(WEB_PREFIX, "").strip()


_plain = plain
