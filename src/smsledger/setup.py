#!/usr/bin/env python3
"""One guided run that leaves a working setup behind.

The people this is for are not going to hand-edit JSON, and should not have to.
This asks a few plain questions, writes the config itself, does the first
collection, builds the report, opens it, and offers to keep it updated. After
that the tool is a bookmark.

Every step is also available on its own (doctor, collect, parse, report, agent) --
this only removes the need to know that.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from .i18n import t as _
from .paths import EXAMPLES
from .paths import HOME as WORKING_HOME


def ask(question: str, default: str = "y") -> bool:
    yes, no = _("yes"), _("no")
    hint = f"{yes.upper()}/{no}" if default == "y" else f"{yes}/{no.upper()}"
    try:
        got = input(f"  {question} [{hint}] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return (got or _("yes")) in (_("yes"), "y", "yes")


def step(n: int, title: str) -> None:
    print(f"\n{n}. {title}")


def check_access() -> bool:
    """Full Disk Access is the one thing nobody can work around for you."""
    from .collect import CHAT_DB, scratch_copy

    if not CHAT_DB.exists():
        print("  " + _("access.missing"))
        print("  " + _("access.missing.why"))
        return False
    with scratch_copy(CHAT_DB) as tmp:
        readable = tmp is not None
    if not readable:
        print("  " + _("access.blocked"))
        print()
        for k in ("access.blocked.how1", "access.blocked.how2", "access.blocked.how3"):
            print("  " + _(k))
        print()
        print("  " + _("access.blocked.why"))
        print("  " + _("access.blocked.why2"))
        return False
    print("  " + _("access.ok"))
    return True


def pick_home() -> Path:
    """Report where data lives. It does *not* decide -- ``paths`` already did.

    This used to choose a directory of its own and then set ``SMSLEDGER_HOME`` in
    the environment mid-run, expecting the already-imported modules to notice.
    They did not: ``collect`` had been imported by step 1, its output path was
    frozen, and deleting the package from ``sys.modules`` does not help because
    ``from . import collect`` finds the stale module still attached to the parent
    package. So the first run collected into one directory and built its report
    from another, and said "read 5 notices, found 0 transactions" on the one
    screen a new reader ever sees.

    A process decides where home is once, at import, from the environment. Nothing
    here may move it afterwards.
    """
    if os.environ.get("SMSLEDGER_HOME"):
        print("  " + _("home.env", path=WORKING_HOME))
    else:
        print("  " + _("home.default", path=WORKING_HOME))
        print("  " + _("home.local"))
    return WORKING_HOME


def write_config(home: Path) -> int:
    """Install the shipped sender list. No hand-editing."""
    cfg = home / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    written = 0
    for src in sorted(EXAMPLES.glob("*.example.json")):
        dest = cfg / src.name.replace(".example", "")
        if dest.exists():
            print("  " + _("config.kept", name=dest.name))
            continue
        shutil.copyfile(src, dest)
        written += 1
    known = json.loads((cfg / "sources.json").read_text(encoding="utf-8"))
    n = len(known.get("sms") or []) + len(known.get("mail") or [])
    print("  " + _("config.wrote", count=n))
    return written


def report_unknown(home: Path) -> None:
    """Tell them plainly if a bank of theirs has no parser yet."""
    from . import doctor

    cfg = json.loads((home / "config" / "sources.json").read_text(encoding="utf-8"))
    scan = doctor.scan_messages(cfg, 90)
    known = sum((scan.get("known") or {}).values())
    unknown, _quiet = doctor.unknown_senders(scan, cfg, 90)
    print("  " + _("arrivals.recognised", count=known))
    if unknown:
        total = sum(v["money"] for v in unknown.values())
        print()
        print("  " + _("arrivals.unknown", count=total))
        for sender in unknown:
            print(f"    {sender}")
        print()
        for k in ("arrivals.unknown.why1", "arrivals.unknown.why2", "arrivals.unknown.why3"):
            print("  " + _(k))
    elif not known:
        print()
        print("  " + _("arrivals.none"))
        print("    " + _("arrivals.none.a"))
        print("    " + _("arrivals.none.a2"))
        print("    " + _("arrivals.none.b"))


def open_file(path: Path) -> None:
    try:
        subprocess.run(["open", str(path)], check=False)
    except OSError:
        pass


def _main() -> None:
    print(_("setup.title"))
    print(_("setup.tagline"))

    step(1, _("setup.step.access"))
    if not check_access():
        raise SystemExit(1)

    step(2, _("setup.step.home"))
    home = pick_home()
    home.mkdir(parents=True, exist_ok=True)

    step(3, _("setup.step.config"))
    write_config(home)

    step(4, _("setup.step.arrivals"))
    report_unknown(home)

    step(5, _("setup.step.read"))
    print("  " + _("read.first"))
    print()
    if not ask(_("read.ask")):
        print("\n" + _("read.stopped"))
        raise SystemExit(0)

    from .refresh import run as refresh

    print("  " + _("read.working"))
    result = refresh(days=180, quiet=True)
    if not result.get("ok"):
        print("\n  " + _("read.failed"))
        print("  " + _("read.failed2"))
        raise SystemExit(1)
    print("  " + _("read.done", collected=result["collected"], parsed=result["parsed"]))

    out = result["report"]
    step(6, _("setup.step.report"))
    print(f"  {out}")
    print("  " + _("report.bookmark"))
    print()
    if ask(_("report.ask.open")):
        open_file(out)

    step(7, _("setup.step.schedule"))
    for k in ("schedule.what1", "schedule.what2", "schedule.what3"):
        print("  " + _(k))
    print()
    if ask(_("schedule.ask")):
        from .agent import install

        if install(hours=6, days=180) == 2:
            print("\n  " + _("schedule.blocked.later"))
    else:
        print("  " + _("schedule.skipped"))

    print("\n" + _("setup.done"))
    from .support import SUPPORT_EMAIL

    print(_("setup.trouble", email=SUPPORT_EMAIL))


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


main = _guarded(_main, "smsledger-setup")


if __name__ == "__main__":
    main()
