"""The first run, on a Mac where nothing has been set up yet.

Everything here is about a path CI cannot reach and the author's own Mac never
takes, because the author has ``SMSLEDGER_HOME`` set. That combination is how the
first-run defects these tests pin survived three rounds of green ticks:

- ``setup`` filled one ledger and built its report from another, so the one screen
  a new reader ever sees said "read 5 notices, found 0 transactions" and then
  opened an empty page.
- Every later command looked in the directory the reader happened to be standing
  in, so a second and third ledger appeared, each holding real financial data.
- A copy of the whole Messages database was left in world-readable ``/tmp`` after
  every collection, which under the scheduled agent is every six hours.
- The support file -- the one thing a reader is asked to send back -- scanned
  messages only, so "does my bank reach this tool" came back "none" from a Mac
  whose bank writes by email.

Every value below is invented.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


def _import_paths(cwd: Path, env_home: str | None = None) -> dict:
    """Where a fresh process thinks everything lives, started from ``cwd``."""
    env = dict(os.environ)
    env.pop("SMSLEDGER_HOME", None)
    if env_home:
        env["SMSLEDGER_HOME"] = env_home
    src = (
        "import json\n"
        "from smsledger import paths, collect, parse, support\n"
        "print(json.dumps({'home': str(paths.HOME), 'collect': str(collect.OUT),\n"
        "                  'parse': str(parse.OUT_PATH), 'errors': str(support.ERRORS)}))\n"
    )
    out = subprocess.run([sys.executable, "-c", src], cwd=str(cwd), env=env,
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_one_ledger_wherever_the_reader_is_standing(tmp_path: Path) -> None:
    """Home must not depend on the working directory.

    It used to default to ``./.smsledger``, which is the same sentence as "wherever
    you happen to be standing": ``cd Documents && refresh`` built a second complete
    ledger there, and ``summary`` from the home directory reported an empty third.
    """
    a = _import_paths(tmp_path)
    (tmp_path / "somewhere-else").mkdir()
    b = _import_paths(tmp_path / "somewhere-else")
    assert a == b, "the ledger moved when the reader changed directory"
    assert a["home"] == str(Path.home() / "smsledger")


def test_everything_in_one_process_agrees_on_where_home_is(tmp_path: Path) -> None:
    """Collection, parsing and the error log must resolve to the same ledger.

    ``setup`` used to set ``SMSLEDGER_HOME`` in the environment half way through a
    run and expect the modules it had already imported to notice. They did not, and
    clearing ``sys.modules`` does not help: ``from . import collect`` finds the stale
    module still attached to the parent package. Nothing may move home after import,
    so this reads the environment the way a process actually does -- once, up front.
    """
    home = tmp_path / "ledger"
    seen = _import_paths(tmp_path, env_home=str(home))
    assert seen["home"] == str(home)
    for key in ("collect", "parse", "errors"):
        assert seen[key].startswith(str(home)), (key, seen[key])


def _fake_chat_db(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(
        "create table handle (ROWID integer primary key, id text);"
        "create table message (ROWID integer primary key, date integer, text text,"
        " attributedBody blob, is_from_me integer, handle_id integer);")
    con.commit()
    con.close()
    return path


def test_no_copy_of_the_messages_database_is_left_behind(tmp_path, monkeypatch) -> None:
    """And it is never put somewhere another account can read it.

    ``collect`` copied ``chat.db`` to a fixed ``/tmp`` name and deleted nothing: on
    this Mac that was 98 MB of message text, plus a journal, sitting in a
    world-readable directory after every run. The cleanup that was written covered
    one of the four readers and missed the one the scheduled agent invokes.
    """
    from smsledger import collect

    src = _fake_chat_db(tmp_path / "chat.db")
    monkeypatch.setattr(collect, "CHAT_DB", src)
    shared = Path(tempfile.gettempdir())

    with collect.scratch_copy(src) as copy:
        assert copy is not None and copy.exists()
        holder = copy.parent
        # Only this account may look at it.
        assert holder.stat().st_mode & 0o077 == 0, oct(holder.stat().st_mode)

    assert not copy.exists(), "the working copy outlived the read"
    assert not holder.exists(), "the directory holding it outlived the read"
    for suffix in ("", "-wal", "-shm"):
        assert not Path(str(copy) + suffix).exists()
    # The old fixed names, which two readers on one Mac would have fought over.
    for stale in ("krsms-chat.db", "smsledger-doctor.db", "smsledger-setup.db",
                  "smsledger-support.db"):
        assert not (shared / stale).exists(), f"{stale} came back"


def _emlx(path: Path, frm: str, html: str) -> None:
    raw = ("From: %s\r\nTo: reader@example.com\r\nSubject: Account alert\r\n"
           "Date: Mon, 5 Oct 2026 15:20:00 +0900\r\nMIME-Version: 1.0\r\n"
           "Content-Type: text/html; charset=utf-8\r\n\r\n%s\r\n" % (frm, html))
    body = raw.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(str(len(body)).encode() + b"\n" + body)


CONFIGURED = {"mail": [{"id": "known", "address": "known@invented.example",
                        "kind": "hana_alert"}], "sms": []}


def test_a_bank_that_only_writes_by_email_is_still_reported(tmp_path, monkeypatch) -> None:
    """Otherwise the answer is "none" and the meaning is "nobody looked".

    Whether a reader's bank reaches this tool is read off one section of the support
    file. That section scanned ``chat.db`` alone, so a US issuer that writes by email
    -- which is most of them -- came back as no unsupported senders at all. A question
    that returns confidently wrong is worse than one that returns unanswered.
    """
    from smsledger import collect, doctor

    root = tmp_path / "Library/Mail/V10"
    monkeypatch.setattr(collect, "MAIL_ROOT", root)
    monkeypatch.setattr(doctor, "MAIL_ROOT", root)
    box = root / "INBOX.mbox/Data/1/Messages"
    for i in range(3):
        _emlx(box / f"{i}.emlx", "Invented Bank <alerts@invented-bank.example>",
              "<html><body><p>A charge of $1,204.50 at TEST FURNITURE posted to your "
              "account ending 4321.</p></body></html>")
    # Configured senders are not news, and marketing that quotes a price is not either.
    # A display name outside ASCII arrives as a Header object, not a string, and
    # handing that straight to `re` is how the whole check died on the first Mac
    # that had one.
    _emlx(box / "9.emlx", "테스트은행 <known@invented.example>",
          "<html><body><p>출금45,000원</p></body></html>")
    _emlx(box / "8.emlx", "Shop <deals@invented-shop.example>",
          "<html><body><p>Everything $19.99 today. Unsubscribe here.</p></body></html>")

    found = doctor.scan_mail(CONFIGURED, days=90)
    assert set(found) == {"alerts@invented-bank.example"}, found
    rec = found["alerts@invented-bank.example"]
    assert rec["money"] == 3 and rec["channel"] == "mail"

    # And it survives the merge the screen and the support file both read.
    loud, _quiet = doctor.unknown_senders({"unknown": {}}, CONFIGURED, days=90)
    assert "alerts@invented-bank.example" in loud
