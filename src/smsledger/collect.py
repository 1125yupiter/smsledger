#!/usr/bin/env python3
"""Collect: pull notice bodies out of macOS Messages and Apple Mail into jsonl.

**There is no login.** No bank website, no scraping, no open-banking API. This
reads only the messages and mail that already arrived on this Mac. That is why
there is no server, and why nobody's financial data can travel anywhere -- there
is nowhere for it to go. That property is the whole design premise.

All it needs is macOS Full Disk Access, plus your phone's messages forwarded to
this Mac (Settings > Messages > Text Message Forwarding).

Collection is country-neutral. Only the parsing of a body is locale-specific.
"""
from __future__ import annotations

import argparse
import email
import email.header
import hashlib
import json
import re
import shutil
import sqlite3
from datetime import datetime
from email.header import decode_header
from pathlib import Path

from .config import sources as load_cfg  # noqa: E402
from .paths import STREAM  # noqa: E402

CURSOR = STREAM / "cursor.json"
OUT = STREAM / "notifications.jsonl"
MAIL_INDEX = Path.home() / "Library/Mail/V10/MailData/Envelope Index"
MAIL_ROOT = Path.home() / "Library/Mail/V10"
CHAT_DB = Path.home() / "Library/Messages/chat.db"
EPOCH = "2001-01-01 00:00:00"   # Apple epoch; earlier than any message
AMT_RE = re.compile(r"([0-9,]+)\s*원")


def load_cursor() -> dict:
    if not CURSOR.exists():
        return {"sms": EPOCH, "mail": EPOCH}
    return json.loads(CURSOR.read_text(encoding="utf-8"))


def save_cursor(cur: dict) -> None:
    STREAM.mkdir(parents=True, exist_ok=True)
    CURSOR.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")


def existing_hashes() -> set[str]:
    seen: set[str] = set()
    if not OUT.exists():
        return seen
    for line in OUT.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            seen.add(json.loads(line)["hash"])
        except (json.JSONDecodeError, KeyError):
            continue
    return seen


def digest(kind: str, ts: str, sender: str, body: str) -> str:
    raw = f"{kind}|{ts}|{sender}|{body}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def deny(what: str) -> None:
    """Could not read it for lack of permission. Say so loudly.

    Returning an empty list quietly is the failure mode that costs days: the
    cursor stops and nothing looks wrong. Both the mail and the message side have
    stalled this way in practice, which is why this shouts.
    """
    print(f"!! No permission to read {what}. Collection has stopped.")
    print("   Grant Full Disk Access: System Settings > Privacy & Security.")


def copy_sqlite(src: Path, dest: Path) -> Path | None:
    try:
        if not src.exists():
            return None
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        wal = Path(str(src) + "-wal")
        shm = Path(str(src) + "-shm")
        if wal.exists():
            shutil.copy2(wal, Path(str(dest) + "-wal"))
        if shm.exists():
            shutil.copy2(shm, Path(str(dest) + "-shm"))
    except PermissionError:
        deny(f"{src.name}")
        return None
    return dest


def decode_ab(blob: bytes) -> str:
    """streamtyped NSAttributedString BLOB -> body text.

    Newer macOS stores the body in ``attributedBody`` and leaves ``text`` NULL, so
    skipping this loses recent messages entirely.
    """
    if not blob:
        return ""
    i = blob.find(b"NSString")
    if i < 0:
        return ""
    j = blob.find(b"+", i)
    if j < 0:
        return ""
    k = j + 1
    if k >= len(blob):
        return ""
    n = blob[k]
    k += 1
    if n == 0x81:
        n = int.from_bytes(blob[k : k + 2], "little")
        k += 2
    elif n == 0x82:
        n = int.from_bytes(blob[k : k + 3], "little")
        k += 3
    return blob[k : k + n].decode("utf-8", "ignore")


DROP_TAGS = re.compile(r"(?is)<(style|script|head)[^>]*>.*?</\1>")
TAG = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    """HTML mail body -> flat text.

    Marketing templates put the whole stylesheet and a navigation block before
    anything that matters. Dropping <style>/<script>/<head> first is what keeps a
    transaction amount from being pushed past the body limit by a kilobyte of CSS.
    """
    out = DROP_TAGS.sub(" ", text or "")
    out = TAG.sub(" ", out)
    out = out.replace("&nbsp;", " ").replace("&amp;", "&").replace("&gt;", ">").replace("&lt;", "<")
    return re.sub(r"\s+", " ", out).strip()


def body_limit() -> int:
    """How much of a mail body to keep.

    Which channel carries the transaction is a per-user setting, not a fact about
    a country: the same bank will send SMS, email, both or neither depending on
    what you switched on. And where email is the channel, HTML templates put the
    amount well past the first few hundred characters -- order emails here run a
    few thousand characters and up to ~19k.

    So the default is generous. A few kilobytes per row is cheap next to silently
    truncating the one line that mattered. Parsers needing the whole body (an
    itemised order table, say) should read the message themselves rather than rely
    on this.
    """
    return int(load_cfg().get("mail_body_limit") or 8000)


def amount_of(text: str) -> int | None:
    m = AMT_RE.search(text.replace(" ", ""))
    if not m:
        m = AMT_RE.search(text)
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


def hdr_decode(v: str | None) -> str:
    if not v:
        return ""
    parts = []
    for chunk, enc in decode_header(v):
        if isinstance(chunk, bytes):
            try:
                parts.append(chunk.decode(enc or "utf-8", "ignore"))
            except LookupError:
                parts.append(chunk.decode("utf-8", "ignore"))
        else:
            parts.append(chunk)
    return "".join(parts)


def match_sender(handle: str, senders: dict[str, dict]) -> dict | None:
    """Treat a plain number and its RCS handle (number@domain) as one sender."""
    if handle in senders:
        return senders[handle]
    local = re.sub(r"\D", "", (handle or "").split("@")[0])
    if len(local) < 8:
        return None
    tail = local[-8:]
    for key, cfg in senders.items():
        digits = re.sub(r"\D", "", key)
        if digits and digits[-8:] == tail:
            return cfg
    return None


def collect_sms(cfg: dict, since: str) -> tuple[list[dict], str, int]:
    senders = {s["sender"]: s for s in cfg.get("sms") or []}
    tmp = Path("/tmp/krsms-chat.db")
    if not copy_sqlite(CHAT_DB, tmp):
        return [], since, 0
    try:
        con = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
    except sqlite3.Error:
        return [], since, 0
    q = """
    select h.id,
           datetime(m.date/1000000000 + strftime('%s','2001-01-01'),'unixepoch','localtime') as ts,
           m.text,
           m.attributedBody
    from message m join handle h on m.handle_id = h.ROWID
    where m.is_from_me = 0
      and datetime(m.date/1000000000 + strftime('%s','2001-01-01'),'unixepoch','localtime') > ?
    order by m.date
    """
    rows = []
    fail = 0
    latest = since
    try:
        for sender, ts, text, ab in con.execute(q, (since,)):
            src = match_sender(sender or "", senders)
            if not src:
                continue
            if not ts:
                fail += 1
                continue
            body = (text or "").strip() or decode_ab(ab or b"")
            if not body:
                fail += 1
                continue
            latest = max(latest, ts)
            rows.append(
                {
                    "channel": "sms",
                    "kind": src["kind"],
                    "sender": sender,
                    "ts": ts,
                    "text": body,
                    "amount": amount_of(body),
                    "matched": False,
                }
            )
    except sqlite3.Error:
        fail += 1
    finally:
        con.close()
    return rows, latest, fail


def collect_mail(cfg: dict, since: str) -> tuple[list[dict], str, int]:
    allow = {m["address"].lower(): m for m in cfg.get("mail") or []}
    rows = []
    fail = 0
    latest = since
    # "Folder absent" and "folder unreadable" are different failures. rglob swallows
    # the permission error and returns nothing, so probe the directory first.
    try:
        list(MAIL_ROOT.iterdir())
    except PermissionError:
        deny("Mail")
        return rows, latest, fail
    except OSError:
        return rows, latest, fail
    needles = tuple(a.encode("ascii", "ignore") for a in allow)
    for path in MAIL_ROOT.rglob("*.emlx"):
        try:
            raw = path.read_bytes()
        except OSError:
            fail += 1
            continue
        if not any(n and n in raw for n in needles):
            continue
        try:
            body = raw.split(b"\n", 1)[1]
            msg = email.message_from_bytes(body)
            frm = hdr_decode(msg.get("From"))
        except Exception:
            fail += 1
            continue
        addr = ""
        m = re.search(r"[\w.+-]+@[\w.-]+", frm)
        if m:
            addr = m.group(0).lower()
        if addr not in allow:
            continue
        date_s = msg.get("Date") or ""
        try:
            ts = email.utils.parsedate_to_datetime(date_s).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            ts = ""
        if ts and ts <= since:
            continue
        if ts:
            latest = max(latest, ts)
        text = ""
        for part in msg.walk():
            if part.get_content_type() not in ("text/plain", "text/html"):
                continue
            payload = part.get_payload(decode=True) or b""
            try:
                text += payload.decode(part.get_content_charset() or "utf-8", "ignore")
            except Exception:
                fail += 1
        plain = strip_html(text)
        if len(plain) < 20:
            fail += 1
        rows.append(
            {
                "channel": "mail",
                "kind": allow[addr]["kind"],
                "sender": addr,
                "ts": ts,
                "subject": hdr_decode(msg.get("Subject")),
                "text": plain[:body_limit()],
                "_full_text": plain,
                "amount": amount_of(plain),
                "partial": path.name.endswith(".partial.emlx"),
                "matched": False,
            }
        )
    return rows, latest, fail


def run(rescan: bool = False) -> dict:
    """Collect new notices. With ``rescan``, ignore the cursor and sweep everything.

    A rescan is safe to run any time: rows are deduplicated by content hash, so
    re-reading history adds nothing new. It exists because the cursor only moves
    forward while phones sync old messages late -- anything that landed behind the
    cursor would otherwise never be collected at all.
    """
    cfg = load_cfg()
    cur = {"sms": EPOCH, "mail": EPOCH} if rescan else load_cursor()
    seen = existing_hashes()
    sms, sms_ts, sms_fail = collect_sms(cfg, cur.get("sms") or EPOCH)
    mail, mail_ts, mail_fail = collect_mail(cfg, cur.get("mail") or EPOCH)
    added = 0
    STREAM.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as f:
        for row in sms + mail:
            # Hash the untruncated body. Otherwise raising the mail body limit changes
            # every hash and re-collects the entire history as duplicates.
            h = digest(row["channel"], row.get("ts") or "", row.get("sender") or "",
                       row.pop("_full_text", None) or row.get("text") or "")
            if h in seen:
                continue
            row["hash"] = h
            row["collected_at"] = datetime.now().isoformat(timespec="seconds")
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            seen.add(h)
            added += 1
    cur["sms"] = sms_ts
    cur["mail"] = mail_ts
    save_cursor(cur)
    print(f"wrote {OUT}")
    print(f"added {added} · sms {len(sms)} fail {sms_fail} · mail {len(mail)} fail {mail_fail}")
    return {"added": added, "sms": len(sms), "mail": len(mail), "sms_fail": sms_fail, "mail_fail": mail_fail}


def main() -> None:
    ap = argparse.ArgumentParser(description="Collect notices from Messages and Apple Mail")
    ap.add_argument("--rescan", action="store_true",
                    help="ignore the cursor and sweep everything (safe; deduplicated by hash)")
    run(rescan=ap.parse_args().rescan)


if __name__ == "__main__":
    main()
