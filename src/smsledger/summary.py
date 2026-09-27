#!/usr/bin/env python3
"""What the collected notices say about your money -- read from parsed rows alone.

This is the honest half of the picture: **what already happened.** Totals, per
account movement, the last balance each account reported, where the money went.

It deliberately does not try to tell you what is *left* or what is *coming*. Doing
that means carrying a balance forward past the last notice, reconciling pending
card charges against a statement, and classifying every row -- each of which needs
configuration and judgement this module does not have. See "not shown" at the end
of the output.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from .i18n import cells, pad
from .i18n import t as _
from .i18n import wrap
from .paths import STREAM

PARSED = STREAM / "parsed.jsonl"

# Amounts are right-aligned in a 15-cell column (see ``money``); the label column
# in front of them is this wide in every language.
LABEL = 22
# Terminal width the closing caveats are wrapped to.
PROSE = 78

# Corporate-card rows are prefixed so a personal ledger skips them.
PERSONAL = ("card_approve", "card_cancel", "bank_tx")
OUTBOUND = "출금"

# Some issuers print the counterparty's account number where a description goes.
# Parsers keep it (it is how a loan payment gets identified), but it must never be
# echoed to a screen in full.
LONG_DIGITS = re.compile(r"\b\d{8,}\b")
# A balance older than this is history, not a useful snapshot.
STALE_DAYS = 90


def load(path: Path | None = None) -> list[dict]:
    p = path or PARSED
    if not p.exists():
        raise SystemExit(f"{_('summary.empty', path=p)}\n{_('summary.empty.fix')}")
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def window(rows: list[dict], since: str, until: str) -> list[dict]:
    return [r for r in rows if r.get("date") and since <= r["date"] <= until]


def money(n: int | float | None) -> str:
    return f"{int(n or 0):>15,}"


def mask_digits(s: str) -> str:
    """Never print a full account number, even when a parser carried one through."""
    return LONG_DIGITS.sub(lambda m: "\u2026" + m.group(0)[-4:], s or "")


def label(name: str, index: int, redact: bool) -> str:
    """Counterparty label. With ``redact`` these become positional, for sharing.

    Payee names are the one field here that is unavoidably personal -- a landlord, a
    family member, your own transfers. `--redact` exists so a screenshot can be
    handed to someone without editing it by hand, which is the point at which people
    leak things.
    """
    return _("report.payee", n=index) if redact else mask_digits(name)


def card_flow(rows: list[dict]) -> tuple[int, int]:
    """Card spending, with cancellations subtracted. Not netting them double-counts."""
    approve = sum(r.get("amount") or 0 for r in rows if r.get("kind") == "card_approve")
    cancel = sum(r.get("amount") or 0 for r in rows if r.get("kind") == "card_cancel")
    return approve, cancel


def bank_flow(rows: list[dict]) -> tuple[int, int]:
    out = sum(r.get("amount") or 0 for r in rows
              if r.get("kind") == "bank_tx" and r.get("dir") == OUTBOUND)
    inn = sum(r.get("amount") or 0 for r in rows
              if r.get("kind") == "bank_tx" and r.get("dir") and r.get("dir") != OUTBOUND)
    return out, inn


def last_balances(rows: list[dict]) -> dict[str, tuple[str, int]]:
    """The most recent balance each account actually reported.

    This is a snapshot as of that message -- not a current balance. Anything spent
    after it is not reflected here.
    """
    best: dict[str, tuple[str, int]] = {}
    for r in rows:
        tail, bal = r.get("acct_tail"), r.get("balance")
        stamp = r.get("ts") or r.get("date") or ""
        if not tail or bal is None or not stamp:
            continue
        if tail not in best or stamp > best[tail][0]:
            best[tail] = (stamp, bal)
    return best


def top_counterparties(rows: list[dict], n: int = 10) -> list[tuple[str, int, int]]:
    agg: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        if r.get("kind") == "card_approve":
            key = r.get("merchant") or r.get("desc") or ""
        elif r.get("kind") == "bank_tx" and r.get("dir") == OUTBOUND:
            key = r.get("desc") or ""
        else:
            continue
        key = (key or "").strip()
        if not key:
            continue
        agg[key][0] += r.get("amount") or 0
        agg[key][1] += 1
    ranked = sorted(agg.items(), key=lambda kv: -kv[1][0])[:n]
    return [(k, v[0], v[1]) for k, v in ranked]


def monthly(rows: list[dict], months: int = 6) -> list[tuple[str, int]]:
    agg: Counter = Counter()
    for r in rows:
        if not r.get("date"):
            continue
        if r.get("kind") == "card_approve":
            agg[r["date"][:7]] += r.get("amount") or 0
        elif r.get("kind") == "card_cancel":
            agg[r["date"][:7]] -= r.get("amount") or 0
        elif r.get("kind") == "bank_tx" and r.get("dir") == OUTBOUND:
            agg[r["date"][:7]] += r.get("amount") or 0
    return sorted(agg.items())[-months:]


def report(rows: list[dict], since: str, until: str, redact: bool = False) -> None:
    personal = [r for r in rows if r.get("kind") in PERSONAL]
    period = window(personal, since, until)

    print(f"\n{_('summary.title')}   {since} .. {until}")
    print(f"{'':2}{_('summary.counts', shown=len(period), total=len(rows))}\n")

    approve, cancel = card_flow(period)
    out, inn = bank_flow(period)
    print("  " + _("summary.out.h"))
    print(f"    {pad(_('summary.out.card'), LABEL)}{money(approve)}")
    if cancel:
        print(f"    {pad(_('summary.out.cancel'), LABEL)}{money(-cancel)}")
    print(f"    {pad(_('summary.out.bank'), LABEL)}{money(out)}")
    print(f"    {'':22}{'-' * 15}")
    print(f"    {pad(_('summary.out.total'), LABEL)}{money(approve - cancel + out)}")
    print("\n  " + _("summary.in.h"))
    print(f"    {pad(_('summary.in.bank'), LABEL)}{money(inn)}")

    corp = [r for r in window(rows, since, until) if str(r.get("kind")).startswith("corp_card")]
    if corp:
        c_ap = sum(r.get("amount") or 0 for r in corp if r["kind"] == "corp_card_approve")
        c_cx = sum(r.get("amount") or 0 for r in corp if r["kind"] == "corp_card_cancel")
        print("\n  " + _("summary.corp.h"))
        print(f"    {pad(_('summary.corp.card'), LABEL)}{money(c_ap - c_cx)}"
              f"   {_('summary.corp.rows', count=len(corp))}")

    bals = last_balances(personal)
    if bals:
        print(f"\n  {_('summary.bal.h')}   {_('summary.bal.note')}")
        today = date.today()
        for tail, (stamp, bal) in sorted(bals.items(), key=lambda kv: kv[1][0], reverse=True):
            try:
                age = (today - date.fromisoformat(stamp[:10])).days
            except ValueError:
                age = 0
            flag = f"   {_('summary.bal.stale', months=age // 30)}" if age > STALE_DAYS else ""
            print(f"    \u2026{tail:<8} {money(bal)}"
                  f"   {_('summary.bal.asof', stamp=stamp[:16])}{flag}")

    tops = top_counterparties(period)
    if tops:
        print("\n  " + _("summary.where.h"))
        shown = [(label(k, i + 1, redact), v, c) for i, (k, v, c) in enumerate(tops)]
        width = max(cells(k) for k, _v, _c in shown)
        for name, total, count in shown:
            print(f"    {pad(name, width)} {money(total)}"
                  f"   {_('summary.where.count', count=count)}")

    series = monthly(personal)
    if len(series) > 1:
        print("\n  " + _("summary.monthly.h"))
        for month, total in series:
            print(f"    {month}   {money(total)}")

    print("\n  " + _("summary.notshown.h"))
    for lead, body in (("report.caveat.transfers.b", "report.caveat.transfers"),
                       ("report.caveat.left.b", "report.caveat.left"),
                       ("report.caveat.coming.b", "report.caveat.coming"),
                       ("report.caveat.cat.b", "report.caveat.cat")):
        for line in wrap(f"{_(lead)} {_(body)}", PROSE, first="    - ", rest="      "):
            print(line)
    print()


def _main() -> None:
    ap = argparse.ArgumentParser(description="Summarise parsed notices")
    ap.add_argument("--days", type=int, default=30, help="window length (default 30)")
    ap.add_argument("--since", help="start date YYYY-MM-DD (overrides --days)")
    ap.add_argument("--until", help="end date YYYY-MM-DD (default today)")
    ap.add_argument("--month", help="a single month, YYYY-MM")
    ap.add_argument("--redact", action="store_true",
                    help="replace counterparty names with positions, for sharing")
    a = ap.parse_args()

    until = a.until or date.today().isoformat()
    if a.month:
        since, until = f"{a.month}-01", f"{a.month}-31"
    elif a.since:
        since = a.since
    else:
        since = (date.fromisoformat(until) - timedelta(days=a.days)).isoformat()
    report(load(), since, until, a.redact)


def _guarded(fn, name):
    """Wrap a CLI entry point so a failure is still findable tomorrow.

    An unhandled traceback goes to a terminal that gets closed. Support requests
    arrive days later, by which time the only question that matters -- what actually
    went wrong -- has no answer anywhere on disk.
    """
    def wrapper():
        try:
            fn()
        except SystemExit:
            raise
        except BaseException as exc:
            import sys as _sys

            from .support import ERRORS, SUPPORT_EMAIL, record_error

            record_error(name, exc)
            print(f"\n{type(exc).__name__}: {exc}", file=_sys.stderr)
            try:
                from .i18n import t as _t

                print(_t("error.recorded", path=ERRORS), file=_sys.stderr)
                print(_t("error.hint", email=SUPPORT_EMAIL), file=_sys.stderr)
            except BaseException:
                # The error path must never raise an error of its own.
                print(f"recorded in {ERRORS}", file=_sys.stderr)
                print(f"python3 -m smsledger support -> {SUPPORT_EMAIL}", file=_sys.stderr)
            raise SystemExit(1)
    return wrapper


main = _guarded(_main, "smsledger-summary")


if __name__ == "__main__":
    main()
