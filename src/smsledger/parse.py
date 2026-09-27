#!/usr/bin/env python3
"""Parse: run collected bodies through the registered parsers, one row each.

This is not where you add a bank -- that is ``locales/<cc>/``. Nothing here
branches on kind; ``registry.parse_row`` looks it up.

If a ledger (``data/transactions.csv``) is present, rows are joined on date and
amount to set ``matched``. Without one the join is skipped and parsing still
works.
"""
from __future__ import annotations

import argparse
import csv
import json
import re

from .registry import parse_row
from .paths import DATA, STREAM

IN_PATH = STREAM / "notifications.jsonl"
OUT_PATH = STREAM / "parsed.jsonl"
MAP_PATH = DATA / "notify_acct_map.json"


def load_txs() -> list[dict]:
    path = DATA / "transactions.csv"
    if not path.exists():
        return []
    out = []
    for r in csv.DictReader(path.open(encoding="utf-8")):
        try:
            amt = int(round(float(r.get("out") or 0) or float(r.get("in") or 0)))
        except ValueError:
            amt = 0
        out.append(
            {
                "date": (r.get("date") or "")[:10],
                "amount": amt,
                "desc": r.get("desc") or "",
                "source": r.get("source") or "",
                "out": r.get("out"),
                "in": r.get("in"),
            }
        )
    return out


def match_tx(txs: list[dict], *, date: str = "", amount: int | None = None, desc: str = "", source: str = "") -> list[dict]:
    """Generic join. Deliberately does not branch on kind."""
    hits = txs
    if date:
        hits = [t for t in hits if t["date"] == date]
    if amount is not None:
        hits = [t for t in hits if t["amount"] == amount]
    if source:
        hits = [t for t in hits if t["source"] == source]
    if desc:
        hits = [t for t in hits if desc[:8] in (t["desc"] or "")]
    return hits


def _load_map() -> dict:
    if not MAP_PATH.exists():
        return {}
    try:
        return json.loads(MAP_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_map(mapping: dict) -> None:
    clean = {}
    for k, v in mapping.items():
        if not re.fullmatch(r"\d{3,6}", str(k)):
            continue
        if not str((v or {}).get("source") or "").startswith(("hana_", "kb_")):
            continue
        clean[str(k)] = v
    MAP_PATH.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")


def _record_map(mapping: dict, acct_tail: str, source: str, day: str) -> None:
    if not acct_tail or not source:
        return
    rec = mapping.get(acct_tail) or {"source": source, "hits": 0, "first": day or ""}
    if rec.get("source") != source and rec.get("hits", 0) > 0:
        rec["conflict"] = source
    else:
        rec["source"] = source
    rec["hits"] = int(rec.get("hits") or 0) + 1
    if not rec.get("first") and day:
        rec["first"] = day
    rec["last"] = day or rec.get("last") or ""
    mapping[acct_tail] = rec


def run() -> dict:
    txs = load_txs()
    mapping = _load_map()
    added = 0
    skipped = 0
    matched_n = 0
    STREAM.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as out:
        if not IN_PATH.exists():
            print("no notifications.jsonl")
            return {"added": 0}
        for line in IN_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            parsed = parse_row(row)
            if parsed is None:
                skipped += 1
                continue
            if parsed.get("skip"):
                skipped += 1
                continue
            hits = []
            if parsed.get("date") and parsed.get("amount") is not None:
                hits = match_tx(
                    txs,
                    date=parsed.get("date") or "",
                    amount=parsed.get("amount"),
                    desc="",
                    source="" if parsed.get("source") in ("hana_alert", "kb_alert") else (parsed.get("source") or ""),
                )
            rec = {
                "hash": row.get("hash"),
                "channel": row.get("channel"),
                "sender": row.get("sender"),
                "ts": row.get("ts"),
                "matched": bool(hits),
                **parsed,
            }
            if hits:
                rec["match_source"] = hits[0]["source"]
                rec["match_desc"] = hits[0]["desc"]
                matched_n += 1
                src = hits[0]["source"]
                if rec.get("acct_tail") and rec.get("date") and src.startswith(("hana_", "kb_")):
                    _record_map(mapping, rec["acct_tail"], src, rec.get("date") or "")
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            added += 1
    _save_map(mapping)
    print(f"wrote {OUT_PATH} parsed {added} matched {matched_n} skipped {skipped}")
    return {"added": added, "matched": matched_n, "skipped": skipped}



def _main() -> None:
    argparse.ArgumentParser(description="알림 원문을 파싱해 parsed.jsonl 로 낸다").parse_args()
    run()


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


main = _guarded(_main, "smsledger-parse")


if __name__ == "__main__":
    main()
