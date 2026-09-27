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

from .collect import CHAT_DB, MAIL_ROOT, copy_sqlite, match_sender
from .config import sources as load_cfg
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


SCRATCH = Path("/tmp/smsledger-doctor.db")


def _discard(tmp: Path) -> None:
    """Delete the working copy *and its journal*.

    ``copy_sqlite`` brings the ``-wal`` and ``-shm`` sidecars across, because
    without them the newest messages are invisible. Deleting only the ``.db``
    left a two-megabyte write-ahead log -- containing message text -- lying in
    ``/tmp`` after every run, and the next read paired a fresh database with that
    stale journal and reported it as malformed.
    """
    for suffix in ("", "-wal", "-shm"):
        Path(str(tmp) + suffix).unlink(missing_ok=True)


def _line(mark: str, text: str) -> None:
    print(f"  {mark} {text}")


def check_paths() -> bool:
    print("\nAccess")
    ok = True
    if not CHAT_DB.exists():
        _line(BAD, f"no Messages database at {CHAT_DB}")
        ok = False
    else:
        tmp = SCRATCH
        if copy_sqlite(CHAT_DB, tmp) is None:
            _line(BAD, "Messages database is not readable -- grant Full Disk Access")
            ok = False
        else:
            _line(OK, "Messages database readable")
            _discard(tmp)
    try:
        list(MAIL_ROOT.iterdir())
        _line(OK, f"Apple Mail readable at {MAIL_ROOT}")
    except PermissionError:
        _line(BAD, "Apple Mail is not readable -- grant Full Disk Access")
        ok = False
    except OSError:
        _line(WARN, f"no Apple Mail data at {MAIL_ROOT} -- mail sources will find nothing")
    return ok


def scan_messages(cfg: dict, days: int) -> dict:
    """Group recent inbound messages by sender, flagging the money-shaped ones."""
    tmp = SCRATCH
    if copy_sqlite(CHAT_DB, tmp) is None:
        return {}
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
        _line(WARN, f"could not scan messages: {exc}")
    finally:
        _discard(tmp)
    return {"known": known, "unknown": unknown, "newest": newest}


def check_sync(newest: str) -> None:
    print("\nPhone sync")
    if not newest:
        _line(BAD, "no inbound messages at all -- is Text Message Forwarding on?")
        _line("", "  Settings > Messages > Text Message Forwarding, on your phone")
    else:
        _line(OK, f"most recent inbound message: {newest}")


def check_coverage(scan: dict, days: int) -> None:
    print(f"\nRecognised senders (last {days} days)")
    known = scan.get("known") or Counter()
    if not known:
        _line(WARN, "nothing matched your configured senders")
    for kind, n in sorted(known.items(), key=lambda kv: -kv[1]):
        _line(OK, f"{kind}: {n} messages")
    missing = set(kinds()) - set(known)
    for kind in sorted(missing):
        _line(WARN, f"{kind}: parser loaded, nothing arrived")


def check_unknown(scan: dict, days: int, min_hits: int = MIN_HITS) -> int:
    """The important one: money-shaped messages from senders with no parser."""
    print(f"\nUnrecognised money messages (last {days} days)")
    noisy = scan.get("unknown") or {}
    unknown = {k: v for k, v in noisy.items() if v["money"] >= min_hits}
    dropped = sum(v["money"] for k, v in noisy.items() if k not in unknown)
    if not unknown:
        _line(OK, "none -- every money-shaped message has a parser")
        if dropped:
            _line("", f"  ({dropped} one-off match(es) ignored as noise; "
                      f"--min-hits 1 to see them)")
        return 0
    total = sum(v["money"] for v in unknown.values())
    _line(WARN, f"{total} messages from {len(unknown)} sender(s) look like transactions "
                f"but have no parser:")
    print()
    for sender, v in sorted(unknown.items(), key=lambda kv: -kv[1]["money"]):
        print(f"      {sender}   {v['money']} messages")
        print(f"      sample: {v['sample']}")   # your own message -- redact before sharing
        print(f'      add to config/sources.json -> "sms": '
              f'{{ "id": "...", "sender": "{sender}", "kind": "..." }}')
        print("      then write locales/<cc>/<bank>.py -- see CONTRIBUTING.md")
        print()
    return total


def check_gaps(cfg: dict, days: int) -> None:
    """Cursor only moves forward, so messages synced late are never collected."""
    print("\nCollection gaps")
    cursor_path = STREAM / "cursor.json"
    out = STREAM / "notifications.jsonl"
    if not cursor_path.exists() or not out.exists():
        _line(WARN, "nothing collected yet -- run python3 -m smsledger collect")
        return
    cur = json.loads(cursor_path.read_text(encoding="utf-8"))
    since = cur.get("sms") or ""
    tmp = SCRATCH
    if copy_sqlite(CHAT_DB, tmp) is None:
        return
    senders = {s["sender"]: s for s in cfg.get("sms") or []}
    collected = set()
    for line in out.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                collected.add(json.loads(line).get("hash"))
            except json.JSONDecodeError:
                continue
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
        return
    finally:
        _discard(tmp)
    if behind > len(collected):
        _line(WARN, f"{behind - len(collected)} message(s) sit before the cursor but were "
                    f"never collected. Phones sync old messages late, and the cursor only "
                    f"moves forward.")
        _line("", "  fix: python3 -m smsledger collect --rescan")
    else:
        _line(OK, "no messages stranded behind the cursor")


def check_mail_truncation() -> None:
    print("\nMail bodies")
    out = STREAM / "notifications.jsonl"
    if not out.exists():
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
        _line(OK, "no mail collected yet")
    elif hit:
        _line(WARN, f"{hit}/{total} mail bodies hit the {limit}-character limit. If a parser "
                    f"is missing amounts, raise mail_body_limit in config.")
    else:
        _line(OK, f"{total} mail bodies, none truncated at {limit} characters")


def run(days: int = 90, min_hits: int = MIN_HITS) -> int:
    print(f"smsledger doctor   home={HOME}")
    print(f"                   locales loaded: {', '.join(kinds()) or 'none'}")
    if not check_paths():
        print("\nStop here: without read access nothing else can be checked.")
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
        print(f"Verdict: works, but {unknown} transaction message(s) are going unread.")
        print("         Adding a parser is one file -- see CONTRIBUTING.md.")
    else:
        print("Verdict: everything arriving is understood.")
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
