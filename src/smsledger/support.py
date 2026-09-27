#!/usr/bin/env python3
"""Produce one file that makes a problem diagnosable, without exposing anything.

When someone says "it doesn't work", the useful reply is not a questionnaire. This
writes a single text file they can read, then send.

**What decides the contents is a rule, not a judgement call: facts about the
environment go in, facts about money stay out.** Versions, permissions, counts,
error traces -- yes. Message bodies, amounts, merchants, account tails, names --
never, and a test enforces it.

The file is plain text and the first thing in it is a list of what it contains, so
nobody has to trust a claim on a web page about their own data.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

from . import __version__
from .i18n import language
from .i18n import t as _
from .paths import CONFIG, HOME, STREAM

# Where a user sends the diagnostic file. One place, so it cannot drift between
# the README, the setup wizard, an error message and the file's own header.
SUPPORT_EMAIL = "1125.yupiter@gmail.com"
ERRORS = HOME / "errors.log"


def tilde(text: str) -> str:
    """Replace the home directory with ~, so a username is not in the file."""
    return str(text).replace(str(Path.home()), "~")


def record_error(command: str, exc: BaseException) -> None:
    """Append a failure so it is still there when someone asks about it later.

    A traceback printed to a terminal that has since been closed helps nobody.
    """
    try:
        ERRORS.parent.mkdir(parents=True, exist_ok=True)
        with ERRORS.open("a", encoding="utf-8") as fh:
            fh.write(f"\n--- {datetime.now().isoformat(timespec='seconds')}  {command}\n")
            fh.write(tilde("".join(traceback.format_exception(type(exc), exc, exc.__traceback__))))
    except OSError:
        pass


def _run(*cmd: str) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _counts() -> dict:
    """Row counts only. Never a row."""
    out = {}
    for name, path in (("notifications", STREAM / "notifications.jsonl"),
                       ("parsed", STREAM / "parsed.jsonl")):
        if not path.exists():
            out[name] = "none"
            continue
        kinds: dict[str, int] = {}
        total = 0
        first = last = ""
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            total += 1
            k = str(row.get("kind") or row.get("channel") or "?")
            kinds[k] = kinds.get(k, 0) + 1
            ts = (row.get("ts") or row.get("date") or "")[:10]
            if ts:
                first = min(first or ts, ts)
                last = max(last, ts)
        out[name] = {"rows": total, "by_kind": kinds, "range": f"{first} .. {last}"}
    return out


def _permissions() -> dict:
    from .collect import CHAT_DB, MAIL_ROOT, copy_sqlite

    tmp = Path("/tmp/smsledger-support.db")
    messages = "missing"
    if CHAT_DB.exists():
        messages = "readable" if copy_sqlite(CHAT_DB, tmp) else "blocked"
        tmp.unlink(missing_ok=True)
    try:
        list(MAIL_ROOT.iterdir())
        mail = "readable"
    except PermissionError:
        mail = "blocked"
    except OSError:
        mail = "missing"
    return {"messages_db": messages, "apple_mail": mail}


def _agent() -> dict:
    from .agent import LABEL, LOG, PLIST

    info = {"installed": PLIST.exists()}
    if PLIST.exists():
        r = subprocess.run(["launchctl", "list", LABEL], capture_output=True, text=True)
        info["loaded"] = r.returncode == 0
    if LOG.exists():
        lines = LOG.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
        # Log lines are counts and paths, never message content.
        info["recent_log"] = [tilde(x) for x in lines[-15:]]
    return info


def _config_shape() -> dict:
    """How config is shaped, not what is in it."""
    out = {}
    for path in sorted(CONFIG.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            out[path.name] = "unreadable"
            continue
        if path.stem == "sources":
            out[path.name] = {
                "sms_senders": len(data.get("sms") or []),
                "mail_senders": len(data.get("mail") or []),
                "kinds": sorted({s.get("kind") for s in
                                 (data.get("sms") or []) + (data.get("mail") or []) if s.get("kind")}),
                "mail_body_limit": data.get("mail_body_limit"),
            }
        else:
            # profile.json holds account tails. Shape only.
            out[path.name] = {"keys": sorted(k for k in data if not k.startswith("_")),
                              "accounts": len(data.get("accounts") or []),
                              "loans": len(data.get("loans") or [])}
    return out


def _unknown_senders(days: int) -> dict:
    """Senders of transaction-shaped messages with no parser.

    The sender is included because it is what a fix needs, and bank shortcodes are
    public. **No sample text** -- which is what doctor shows on screen and what must
    not travel. If a personal number appears here, the file is readable and it can be
    deleted before sending.
    """
    from . import doctor

    try:
        cfg = json.loads((CONFIG / "sources.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    scan = doctor.scan_messages(cfg, days)
    return {s: v["money"] for s, v in (scan.get("unknown") or {}).items()
            if v["money"] >= doctor.MIN_HITS}


def build(days: int = 90) -> str:
    from .registry import kinds

    lines = [
        "smsledger support report",
        f"generated  {datetime.now().isoformat(timespec='seconds')}",
        "",
        f"{_('support.file.sendto')}   {SUPPORT_EMAIL}",
        "",
        # Section headers stay English so the file reads the same to whoever ends up
        # diagnosing it. These two paragraphs are for the sender, not the reader:
        # nobody can decide whether to send a file describing itself in a language
        # they do not read.
        _("support.file.in"),
        "  " + _("support.file.in1"),
        "  " + _("support.file.in2"),
        _("support.file.out"),
        "  " + _("support.file.out1"),
        "  " + _("support.file.out2"),
        "",
        "ENVIRONMENT",
        f"  smsledger      {__version__}",
        f"  python         {platform.python_version()}  ({tilde(sys.executable)})",
        f"  macOS          {platform.mac_ver()[0] or 'unknown'}  {platform.machine()}",
        f"  language       {language()}  (AppleLocale={_run('defaults', 'read', '-g', 'AppleLocale') or '-'},"
        f" LANG={os.environ.get('LANG') or '-'})",
        f"  home           {tilde(HOME)}",
        f"  installed from {tilde(Path(__file__).resolve().parent.parent)}",
        f"  parsers        {', '.join(kinds()) or 'none'}",
        "",
        "PERMISSIONS",
    ]
    for k, v in _permissions().items():
        lines.append(f"  {k:<14} {v}")

    lines += ["", "CONFIG (shape only)"]
    shape = _config_shape()
    lines.append("  " + (json.dumps(shape, ensure_ascii=False, indent=2).replace("\n", "\n  ")
                         if shape else "no config files"))

    lines += ["", "DATA (counts only)"]
    lines.append("  " + json.dumps(_counts(), ensure_ascii=False, indent=2).replace("\n", "\n  "))

    lines += ["", "BACKGROUND TASK"]
    lines.append("  " + json.dumps(_agent(), ensure_ascii=False, indent=2).replace("\n", "\n  "))

    unknown = _unknown_senders(days)
    lines += ["", f"SENDERS WITH NO PARSER (last {days} days)"]
    if unknown:
        for sender, n in sorted(unknown.items(), key=lambda kv: -kv[1]):
            lines.append(f"  {sender}   {n} messages")
    else:
        lines.append("  none")

    lines += ["", "RECENT ERRORS"]
    if ERRORS.exists():
        text = ERRORS.read_text(encoding="utf-8", errors="ignore").strip()
        lines.append("  " + (text[-4000:].replace("\n", "\n  ") if text else "none"))
    else:
        lines.append("  none")

    lines.append("")
    return "\n".join(lines)


def compose(path: Path, note: str = "") -> None:
    """Open a mail draft and reveal the file, so attaching it is a drag.

    Mail clients cannot be handed an attachment through a mailto: link -- that is a
    standing restriction, not an oversight -- so the next best thing is to put the
    draft and the file in front of someone at the same moment. Asking a
    non-technical person to navigate to a path is where this otherwise stops.
    """
    import urllib.parse

    body = _("support.mail.body", path=path, note=note)
    url = "mailto:{to}?subject={s}&body={b}".format(
        to=SUPPORT_EMAIL,
        s=urllib.parse.quote(_("support.mail.subject", version=__version__)),
        b=urllib.parse.quote(body),
    )
    for cmd in (["open", url], ["open", "-R", str(path)]):
        try:
            subprocess.run(cmd, check=False, timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass


def main() -> None:
    ap = argparse.ArgumentParser(description="Write a diagnostic file that can be shared")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("-o", "--out", help="output path (default $SMSLEDGER_HOME/support.txt)")
    ap.add_argument("--email", action="store_true",
                    help="open a mail draft and reveal the file")
    ap.add_argument("--no-email", action="store_true", help="just write the file")
    a = ap.parse_args()

    out = Path(a.out) if a.out else HOME / "support.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(a.days), encoding="utf-8")
    print(_("support.wrote", path=out))
    print("  " + _("support.readfirst"))
    print("  " + _("support.contents"))
    print("  " + _("support.sendto", email=SUPPORT_EMAIL))

    if a.no_email:
        return
    if a.email or _ask_send():
        compose(out)
        print("  " + _("support.mail.opened"))


def _ask_send() -> bool:
    try:
        got = input("  " + _("support.mail.ask") + f" [{_('yes').upper()}/{_('no')}] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return (got or _("yes")) in (_("yes"), "y", "yes")


if __name__ == "__main__":
    main()
