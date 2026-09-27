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
import sys
from pathlib import Path

from .paths import EXAMPLES

DEFAULT_HOME = Path.home() / "smsledger"


def ask(question: str, default: str = "y") -> bool:
    hint = "Y/n" if default == "y" else "y/N"
    try:
        got = input(f"  {question} [{hint}] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return (got or default) in ("y", "yes")


def step(n: int, title: str) -> None:
    print(f"\n{n}. {title}")


def check_access() -> bool:
    """Full Disk Access is the one thing nobody can work around for you."""
    from .collect import CHAT_DB, copy_sqlite

    tmp = Path("/tmp/smsledger-setup.db")
    if not CHAT_DB.exists():
        print("  Could not find the Messages database.")
        print("  This tool reads messages already on this Mac, so there is nothing to read.")
        return False
    if copy_sqlite(CHAT_DB, tmp) is None:
        print("  macOS is blocking access to your messages.")
        print()
        print("  Open System Settings > Privacy & Security > Full Disk Access,")
        print("  add Terminal (or whichever app you are running this in), then")
        print("  quit that app completely and run this again.")
        print()
        print("  Nothing leaves your Mac either way -- this permission is what lets")
        print("  the tool read the notices your bank already sent you.")
        return False
    tmp.unlink(missing_ok=True)
    print("  Messages are readable.")
    return True


def pick_home() -> Path:
    env = os.environ.get("SMSLEDGER_HOME")
    if env:
        print(f"  Using SMSLEDGER_HOME={env}")
        return Path(env).expanduser()
    print(f"  Your data will be kept in {DEFAULT_HOME}")
    print("  (on this Mac only -- nothing is uploaded)")
    return DEFAULT_HOME


def write_config(home: Path) -> int:
    """Install the shipped sender list. No hand-editing."""
    cfg = home / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    written = 0
    for src in sorted(EXAMPLES.glob("*.example.json")):
        dest = cfg / src.name.replace(".example", "")
        if dest.exists():
            print(f"  Keeping your existing {dest.name}")
            continue
        shutil.copyfile(src, dest)
        written += 1
    known = json.loads((cfg / "sources.json").read_text(encoding="utf-8"))
    n = len(known.get("sms") or []) + len(known.get("mail") or [])
    print(f"  Wrote config for {n} known senders.")
    return written


def report_unknown(home: Path) -> None:
    """Tell them plainly if a bank of theirs has no parser yet."""
    os.environ["SMSLEDGER_HOME"] = str(home)
    from . import doctor

    cfg = json.loads((home / "config" / "sources.json").read_text(encoding="utf-8"))
    scan = doctor.scan_messages(cfg, 90)
    known = sum((scan.get("known") or {}).values())
    unknown = {k: v for k, v in (scan.get("unknown") or {}).items()
               if v["money"] >= doctor.MIN_HITS}
    print(f"  Recognised {known} messages in the last 90 days.")
    if unknown:
        total = sum(v["money"] for v in unknown.values())
        print()
        print(f"  {total} message(s) look like transactions but are not understood yet:")
        for sender in unknown:
            print(f"    {sender}")
        print()
        print("  That means a bank of yours is not supported yet. Everything else")
        print("  still works; those messages are simply skipped. Reporting the")
        print("  sender above is what gets it added.")
    elif not known:
        print()
        print("  Nothing recognised. Two usual reasons:")
        print("    - your phone's messages are not forwarded to this Mac")
        print("      (on the phone: Settings > Messages > Text Message Forwarding)")
        print("    - your bank is not supported yet")


def open_file(path: Path) -> None:
    try:
        subprocess.run(["open", str(path)], check=False)
    except OSError:
        pass


def main() -> None:
    print("smsledger setup")
    print("Reads the bank notices already on this Mac. No login, nothing uploaded.")

    step(1, "Checking access")
    if not check_access():
        raise SystemExit(1)

    step(2, "Choosing where your data lives")
    home = pick_home()
    os.environ["SMSLEDGER_HOME"] = str(home)
    home.mkdir(parents=True, exist_ok=True)

    step(3, "Writing configuration")
    write_config(home)

    step(4, "Looking at what arrives")
    report_unknown(home)

    step(5, "Reading your messages")
    print("  The first run goes through everything, so give it a minute.")
    print()
    if not ask("Start now?"):
        print("\nStopped. Run `smsledger-setup` again when you are ready.")
        raise SystemExit(0)

    # Import after SMSLEDGER_HOME is set: paths are resolved at import time.
    for mod in [m for m in list(sys.modules) if m.startswith("smsledger.")]:
        del sys.modules[mod]
    from smsledger.refresh import run as refresh

    print("  working...")
    result = refresh(days=180, quiet=True)
    if not result.get("ok"):
        print("\n  Something went wrong above. Nothing was damaged -- run it again,")
        print("  or `smsledger-doctor` to see what it found.")
        raise SystemExit(1)
    print(f"  Read {result['collected']:,} notices and found "
          f"{result['parsed']:,} transactions.")

    out = result["report"]
    step(6, "Your report")
    print(f"  {out}")
    print("  Bookmark it. It is a plain file -- it works offline and always will.")
    print()
    if ask("Open it now?"):
        open_file(out)

    step(7, "Keeping it up to date")
    print("  A background task can refresh this a few times a day, so the report")
    print("  is current whenever you open it. It uses no network and can be removed")
    print("  at any time with `smsledger-agent remove`.")
    print()
    if ask("Set that up?"):
        from smsledger.agent import install

        if install(hours=6, days=180) == 2:
            print("\n  Until that is done, run `smsledger-refresh` yourself to update.")
    else:
        print("  Skipped. Run `smsledger-refresh` yourself whenever you want an update.")

    print("\nDone. From here on, opening the report is the whole workflow.")


if __name__ == "__main__":
    main()
