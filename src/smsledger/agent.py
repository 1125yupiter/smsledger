#!/usr/bin/env python3
"""Keep the report up to date without anyone opening a terminal again.

Installs a macOS LaunchAgent that runs ``smsledger refresh`` on a schedule. After
this, using the tool is opening one bookmarked file -- which is the difference
between something a person keeps using and something they tried once.

The agent is a plain plist in ~/Library/LaunchAgents. Nothing is installed
system-wide, nothing needs an administrator password, and removing it is one
command (or deleting the file).
"""
from __future__ import annotations

import argparse
import plistlib
import subprocess
import sys
import time
from pathlib import Path

from .i18n import t as _
from .paths import HOME

LABEL = "com.smsledger.refresh"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG = HOME / "agent.log"


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def install(hours: int = 6, days: int = 180, redact: bool = False) -> int:
    exe = Path(sys.executable)
    cmd = [str(exe), "-m", "smsledger.refresh", "--days", str(days)]
    if redact:
        cmd.append("--redact")

    LOG.parent.mkdir(parents=True, exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": LABEL,
        "ProgramArguments": cmd,
        "StartInterval": hours * 3600,
        # Run once right after loading, and catch up if the Mac was asleep at the
        # scheduled moment -- otherwise a laptop that sleeps nightly never runs.
        "RunAtLoad": True,
        "EnvironmentVariables": {"SMSLEDGER_HOME": str(HOME)},
        "StandardOutPath": str(LOG),
        "StandardErrorPath": str(LOG),
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "Nice": 5,
    }
    PLIST.write_bytes(plistlib.dumps(plist))

    _launchctl("bootout", f"gui/{_uid()}/{LABEL}")
    r = _launchctl("bootstrap", f"gui/{_uid()}", str(PLIST))
    if r.returncode != 0:
        r = _launchctl("load", "-w", str(PLIST))
    if r.returncode != 0:
        print(f"could not load the agent: {r.stderr.strip()}", file=sys.stderr)
        return 1
    print(_("agent.installed", hours=hours))
    print("  " + _("agent.report", path=HOME / "report.html"))
    print("  " + _("agent.log", path=LOG))
    print("  " + _("agent.remove.hint"))
    return 0 if _verify_first_run() else 2


DENIED = "No permission"


def _verify_first_run(timeout: int = 40) -> bool:
    """Watch the first scheduled run finish, and say so if it could not read.

    Permission on macOS is granted per executable. The app you ran the installer
    from has it; the agent is launched by launchd, which is a different parent, and
    it can silently read nothing at all. An agent that runs on time and collects
    nothing looks exactly like an agent that is working, which is the worst
    possible failure for someone who will not go looking in a log file.
    """
    before = LOG.stat().st_size if LOG.exists() else 0
    print("\n  " + _("agent.verify"))
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(2)
        if not LOG.exists() or LOG.stat().st_size <= before:
            continue
        text = LOG.read_text(encoding="utf-8", errors="ignore")[before:]
        if DENIED in text:
            print("  " + _("agent.verify.blocked"))
            print()
            print("  " + _("agent.verify.blocked.why"))
            print("  " + _("agent.verify.blocked.why2"))
            print("    " + _("agent.verify.blocked.how1"))
            print("    " + _("agent.verify.blocked.how2"))
            print(f"      {sys.executable}")
            print("    " + _("agent.verify.blocked.how3"))
            return False
        if "collected" in text or "FAILED" in text:
            print("  " + _("agent.verify.ok"))
            return True
    print("  " + _("agent.verify.timeout", seconds=timeout))
    print("    smsledger-agent status")
    return True


def _uid() -> str:
    import os

    return str(os.getuid())


def remove() -> int:
    _launchctl("bootout", f"gui/{_uid()}/{LABEL}")
    _launchctl("unload", str(PLIST))
    if PLIST.exists():
        PLIST.unlink()
    print(_("agent.removed"))
    return 0


def status() -> int:
    if not PLIST.exists():
        print(_("agent.notinstalled"))
        return 1
    r = _launchctl("list", LABEL)
    print(f"plist:  {PLIST}")
    print(_("agent.loaded", state=_("yes") if r.returncode == 0 else _("no")))
    if not LOG.exists():
        print(_("agent.nolog"))
        return 0
    text = LOG.read_text(encoding="utf-8", errors="ignore")
    print(_("agent.log", path=LOG))
    for line in text.strip().splitlines()[-5:]:
        print(f"  {line}")
    if DENIED in text.splitlines()[-40:] and DENIED in text:
        print()
        print("  " + _("agent.blocked.short"))
        print("  " + _("agent.verify.blocked.how1"))
        print("  " + _("agent.verify.blocked.how2"))
        print(f"    {sys.executable}")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Schedule smsledger to keep itself up to date")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("install", help="install and start the scheduled refresh")
    p.add_argument("--hours", type=int, default=6, help="how often to run (default 6)")
    p.add_argument("--days", type=int, default=180, help="report window (default 180)")
    p.add_argument("--redact", action="store_true", help="hide counterparty names")
    sub.add_parser("remove", help="stop and remove it")
    sub.add_parser("status", help="show whether it is running")
    a = ap.parse_args()

    if a.cmd == "install":
        raise SystemExit(install(a.hours, a.days, a.redact))
    if a.cmd == "remove":
        raise SystemExit(remove())
    raise SystemExit(status())


if __name__ == "__main__":
    main()
