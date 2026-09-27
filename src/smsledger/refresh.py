#!/usr/bin/env python3
"""Collect, parse and rebuild the report in one step.

This is what the scheduled agent runs, and what you run by hand if you do not want
an agent. Keeping it one command means the agent's job description is a single
line rather than a shell script that can drift from what the tool actually does.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import sys
import traceback
from datetime import datetime

from .paths import HOME


def run(days: int = 180, redact: bool = False, rescan: bool = False,
        quiet: bool = False) -> dict:
    """Returns a summary dict. ``quiet`` swallows the step-by-step machine output,
    which is noise to anyone who did not write it."""
    from . import collect, parse
    from .report import build
    from .summary import load

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sink = io.StringIO()
    try:
        with contextlib.redirect_stdout(sink) if quiet else contextlib.nullcontext():
            got = collect.run(rescan=rescan)
            parsed = parse.run()
        rows = load()
        from datetime import date, timedelta

        until = date.today().isoformat()
        since = (date.today() - timedelta(days=days)).isoformat()
        out = HOME / "report.html"
        out.write_text(build(rows, since, until, redact), encoding="utf-8")
        if not quiet:
            print(f"{stamp}  collected {got.get('added', 0)} · "
                  f"parsed {parsed.get('added', 0)} · {out}")
        return {"ok": True, "collected": got.get("added", 0),
                "parsed": parsed.get("added", 0), "rows": len(rows), "report": out}
    except Exception:
        # The agent runs unattended; a stack trace in the log is the only way to
        # find out why a week of silence happened.
        print(f"{stamp}  FAILED", file=sys.stderr)
        traceback.print_exc()
        return {"ok": False}


def main() -> None:
    ap = argparse.ArgumentParser(description="Collect, parse and rebuild the report")
    ap.add_argument("--days", type=int, default=180, help="report window (default 180)")
    ap.add_argument("--redact", action="store_true", help="hide counterparty names in the report")
    ap.add_argument("--rescan", action="store_true", help="ignore the cursor and sweep everything")
    a = ap.parse_args()
    raise SystemExit(0 if run(a.days, a.redact, a.rescan).get("ok") else 1)


if __name__ == "__main__":
    main()
