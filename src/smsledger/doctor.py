#!/usr/bin/env python3
"""Check whether this tool can work on this machine -- before you rely on it.

Run this first. It answers the three questions that decide everything:

1. Can it read your messages and mail at all? (permissions, phone sync)
2. Is anything arriving that it does not yet understand? (a bank with no parser)
3. Is anything being missed that it should have caught? (cursor gaps, truncation)

Question 2 matters most. "My bank isn't supported" should be something you find
out in thirty seconds, not after committing to a workflow -- and the answer comes
with the exact config line to add.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from .collect import CHAT_DB, MAIL_ROOT, match_sender, scratch_copy
from .config import sources as load_cfg
from .i18n import cells
from .i18n import t as _
from .i18n import wrap
from .paths import HOME, STREAM
from .registry import kinds

# A money-shaped token in any locale we know of: grouped digits next to a currency
# word or symbol. Deliberately loose -- this is for spotting candidates, not parsing.
MONEY = re.compile(
    r"([0-9]{1,3}(?:,[0-9]{2,3})+|[0-9]{4,})\s*(?:원|円|元|USD|EUR|GBP|INR|Rs\.?|₩|¥|\$|€|£)"
    r"|(?:USD|EUR|GBP|INR|Rs\.?|₩|¥|\$|€|£)\s*([0-9]{1,3}(?:,[0-9]{2,3})+|[0-9]+\.[0-9]{2})"
)
# Promotional messages quote prices too, so a money shape alone is not enough.
# These markers are how senders label marketing in the locales we have seen.
PROMO = re.compile(
    r"\(광고\)|\[광고\]|광고\s*문자|무료수신거부|수신거부|"
    r"\(AD\)|\bunsubscribe\b|\bopt.?out\b|\bpromo(tion)?\b|\bsale\b|\bcoupon\b",
    re.I,
)
# One stray match is noise. A real unsupported bank sends steadily.
MIN_HITS = 3

OK, WARN, BAD = "✓", "!", "✗"


def _line(mark: str, text: str) -> None:
    print(f"  {mark} {text}")


def check_paths() -> bool:
    print("\n" + _("doctor.access.h"))
    ok = True
    if not CHAT_DB.exists():
        _line(BAD, _("doctor.access.nodb", path=CHAT_DB))
        ok = False
    else:
        with scratch_copy(CHAT_DB) as tmp:
            if tmp is None:
                _line(BAD, _("doctor.access.blocked"))
                ok = False
            else:
                _line(OK, _("doctor.access.ok"))
    try:
        list(MAIL_ROOT.iterdir())
        _line(OK, _("doctor.access.mail.ok", path=MAIL_ROOT))
    except PermissionError:
        _line(BAD, _("doctor.access.mail.blocked"))
        ok = False
    except OSError:
        _line(WARN, _("doctor.access.mail.none", path=MAIL_ROOT))
    return ok


def scan_messages(cfg: dict, days: int) -> dict:
    """Group recent inbound messages by sender, flagging the money-shaped ones."""
    with scratch_copy(CHAT_DB) as tmp:
        if tmp is None:
            return {}
        return _group_senders(tmp, cfg, days)


def _group_senders(tmp: Path, cfg: dict, days: int) -> dict:
    senders = {s["sender"]: s for s in cfg.get("sms") or []}
    known: Counter = Counter()
    unknown: dict[str, dict] = defaultdict(lambda: {"total": 0, "money": 0, "sample": ""})
    newest = ""
    try:
        con = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
        q = """
        select h.id,
               datetime(m.date/1000000000 + strftime('%s','2001-01-01'),'unixepoch','localtime') as ts,
               m.text
        from message m join handle h on m.handle_id = h.ROWID
        where m.is_from_me = 0
          and datetime(m.date/1000000000 + strftime('%s','2001-01-01'),'unixepoch','localtime')
              > datetime('now','localtime',?)
        """
        for sender, ts, text in con.execute(q, (f"-{days} days",)):
            newest = max(newest, ts or "")
            src = match_sender(sender or "", senders)
            body = text or ""
            if src:
                known[src["kind"]] += 1
                continue
            if not MONEY.search(body) or PROMO.search(body):
                continue
            rec = unknown[sender or "(unknown)"]
            rec["total"] += 1
            rec["money"] += 1
            if not rec["sample"]:
                rec["sample"] = re.sub(r"\s+", " ", body)[:60]
    except sqlite3.Error as exc:
        _line(WARN, _("doctor.scan.failed", error=exc))
    return {"known": known, "unknown": unknown, "newest": newest}


def check_sync(newest: str) -> None:
    print("\n" + _("doctor.sync.h"))
    if not newest:
        _line(BAD, _("doctor.sync.none"))
        # The same instruction setup gives; there is only one place to turn this on.
        _line("", _("arrivals.none.a2"))
    else:
        _line(OK, _("doctor.sync.newest", stamp=newest))


def check_coverage(scan: dict, days: int) -> None:
    print("\n" + _("doctor.coverage.h", days=days))
    known = scan.get("known") or Counter()
    if not known:
        _line(WARN, _("doctor.coverage.none"))
    for kind, n in sorted(known.items(), key=lambda kv: -kv[1]):
        _line(OK, f"{kind}: {_('doctor.coverage.count', count=n)}")
    missing = set(kinds()) - set(known)
    for kind in sorted(missing):
        _line(WARN, f"{kind}: {_('doctor.coverage.idle')}")


def check_unknown(scan: dict, days: int, min_hits: int = MIN_HITS) -> int:
    """The important one: money-shaped messages from senders with no parser."""
    print("\n" + _("doctor.unknown.h", days=days))
    noisy = scan.get("unknown") or {}
    unknown = {k: v for k, v in noisy.items() if v["money"] >= min_hits}
    dropped = sum(v["money"] for k, v in noisy.items() if k not in unknown)
    if not unknown:
        _line(OK, _("doctor.unknown.none"))
        if dropped:
            _line("", "  " + _("doctor.unknown.noise", count=dropped))
        return 0
    total = sum(v["money"] for v in unknown.values())
    lines = wrap(_("doctor.unknown.found", count=total, senders=len(unknown)),
                 76, first=f"  {WARN} ", rest="    ")
    for line in lines:
        print(line)
    print()
    for sender, v in sorted(unknown.items(), key=lambda kv: -kv[1]["money"]):
        print(f"      {sender}   {_('doctor.unknown.count', count=v['money'])}")
        # your own message -- redact before sharing
        print(f"      {_('doctor.unknown.sample', text=v['sample'])}")
        snippet = '{ "id": "...", "sender": "%s", "kind": "..." }' % sender
        print(f"      {_('doctor.unknown.add', snippet=snippet)}")
        print(f"      {_('doctor.unknown.write')}")
        print()
    return total


def _count_behind(senders: dict, since: str) -> int | None:
    """How many recognised messages sit behind the cursor. ``None`` if unreadable."""
    with scratch_copy(CHAT_DB) as tmp:
        if tmp is None:
            return None
        behind = 0
        try:
            con = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
            q = """
            select h.id,
                   datetime(m.date/1000000000 + strftime('%s','2001-01-01'),'unixepoch','localtime') as ts
            from message m join handle h on m.handle_id = h.ROWID
            where m.is_from_me = 0
              and datetime(m.date/1000000000 + strftime('%s','2001-01-01'),'unixepoch','localtime') <= ?
            """
            for sender, ts in con.execute(q, (since,)):
                if match_sender(sender or "", senders):
                    behind += 1
        except sqlite3.Error:
            return None
        return behind


def check_gaps(cfg: dict, days: int) -> None:
    """Cursor only moves forward, so messages synced late are never collected."""
    print("\n" + _("doctor.gaps.h"))
    cursor_path = STREAM / "cursor.json"
    out = STREAM / "notifications.jsonl"
    if not cursor_path.exists() or not out.exists():
        _line(WARN, _("doctor.gaps.nothing"))
        return
    cur = json.loads(cursor_path.read_text(encoding="utf-8"))
    since = cur.get("sms") or ""
    senders = {s["sender"]: s for s in cfg.get("sms") or []}
    collected = set()
    for line in out.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                collected.add(json.loads(line).get("hash"))
            except json.JSONDecodeError:
                continue
    behind = _count_behind(senders, since)
    if behind is None:
        return
    if behind > len(collected):
        for line in wrap(_("doctor.gaps.behind", count=behind - len(collected)),
                         76, first=f"  {WARN} ", rest="    "):
            print(line)
        _line("", "  " + _("doctor.gaps.fix"))
    else:
        _line(OK, _("doctor.gaps.ok"))


def check_mail_truncation() -> None:
    print("\n" + _("doctor.mail.h"))
    out = STREAM / "notifications.jsonl"
    if not out.exists():
        # Printing the heading and then nothing looked like the check had crashed.
        _line(OK, _("doctor.mail.empty"))
        return
    from .collect import body_limit

    limit = body_limit()
    hit = total = 0
    for line in out.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("channel") != "mail":
            continue
        total += 1
        if len(row.get("text") or "") >= limit:
            hit += 1
    if not total:
        _line(OK, _("doctor.mail.empty"))
    elif hit:
        for line in wrap(_("doctor.mail.truncated", hit=hit, total=total, limit=limit),
                         76, first=f"  {WARN} ", rest="    "):
            print(line)
    else:
        _line(OK, _("doctor.mail.intact", total=total, limit=limit))


def run(days: int = 90, min_hits: int = MIN_HITS) -> int:
    title = _("doctor.title")
    print(f"{title}   {_('doctor.home', path=HOME)}")
    loaded = ", ".join(kinds()) or _("doctor.parsers.none")
    print(f"{'':{cells(title) + 3}}{_('doctor.parsers', list=loaded)}")
    if not check_paths():
        print("\n" + _("doctor.stop"))
        return 1
    cfg = load_cfg()
    scan = scan_messages(cfg, days)
    check_sync(scan.get("newest") or "")
    check_coverage(scan, days)
    unknown = check_unknown(scan, days, min_hits)
    check_gaps(cfg, days)
    check_mail_truncation()
    print()
    if unknown:
        # Hanging-indenting under "Verdict: " would sit in the wrong place once the
        # word is translated, so the follow-up gets its own indented line.
        print(_("doctor.verdict.unread", count=unknown))
        print("  " + _("doctor.verdict.parser"))
    else:
        print(_("doctor.verdict.ok"))
    return 0


def _main() -> None:
    ap = argparse.ArgumentParser(description="Check whether smsledger can work here")
    ap.add_argument("--days", type=int, default=90, help="how far back to scan (default 90)")
    ap.add_argument("--min-hits", type=int, default=MIN_HITS,
                    help=f"report an unknown sender after this many hits (default {MIN_HITS})")
    args = ap.parse_args()
    raise SystemExit(run(args.days, args.min_hits))


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


main = _guarded(_main, "smsledger-doctor")


if __name__ == "__main__":
    main()
