"""Year inference: the quietest trap in this tool, since texts omit the year."""
from __future__ import annotations

import pytest

from smsledger.util import won, year_for


@pytest.mark.parametrize(
    "ts,month,day,expected",
    [
        ("2026-09-27 10:00:00", 9, 20, 2026),   # earlier the same year
        ("2026-09-27 10:00:00", 9, 27, 2026),   # same day
        ("2027-01-03 09:00:00", 12, 28, 2026),  # last December, received in January
        ("2026-01-01 00:30:00", 12, 31, 2025),  # just past midnight
        ("2026-09-27 10:00:00", 2, 30, 2026),   # impossible date: keep received year
    ],
)
def test_year_for(ts: str, month: int, day: int, expected: int) -> None:
    assert year_for(ts, month, day) == expected


def test_year_for_without_ts_does_not_crash() -> None:
    assert isinstance(year_for("", 9, 20), int)


@pytest.mark.parametrize("raw,expected", [("1,234", 1234), ("0", 0), ("", None), ("abc", None), (None, None)])
def test_won(raw, expected) -> None:
    """None, never 0, when an amount cannot be read."""
    assert won(raw) == expected


def test_strip_html_drops_style_before_truncation() -> None:
    """A kilobyte of CSS must not push the amount past the body limit.

    This is the difference between working and not in locales where the
    transaction only ever arrives by mail.
    """
    from smsledger.collect import strip_html

    html = (
        "<head><style>" + ".x{color:red}" * 200 + "</style></head>"
        "<body><script>var a=1;</script><p>Transaction: $42.50 at SOME STORE</p></body>"
    )
    out = strip_html(html)
    assert "color:red" not in out
    assert "var a" not in out
    assert out.index("$42.50") < 200, out[:80]


def test_strip_html_decodes_common_entities() -> None:
    from smsledger.collect import strip_html

    assert strip_html("<p>A&nbsp;&amp;&nbsp;B</p>") == "A & B"


def test_identity_is_independent_of_body_processing() -> None:
    """Raising the body limit must not turn history into a second copy of itself.

    This is the regression for a real incident: changing how mail bodies were
    truncated changed every content hash, so a rescan silently added 187 duplicate
    rows -- and because the new hashes were all distinct, nothing looked wrong.
    """
    from smsledger.collect import identity

    row_short = {"channel": "mail", "ts": "2026-09-22 08:15:40",
                 "sender": "alerts@example.com", "subject": "Transaction",
                 "text": "A" * 500}
    row_long = dict(row_short, text="A" * 8000)
    assert identity(row_short) == identity(row_long)


def test_identity_separates_different_senders() -> None:
    from smsledger.collect import identity

    base = {"channel": "sms", "ts": "2026-09-22 08:15:40", "subject": ""}
    assert identity({**base, "sender": "+1"}) != identity({**base, "sender": "+2"})


def test_mask_digits_never_prints_a_full_account_number() -> None:
    """Parsers keep account numbers on purpose; a screen must not echo them."""
    from smsledger.summary import mask_digits

    out = mask_digits("98765432109876")
    assert "98765432109876" not in out
    assert out.endswith("9876")
    # short numbers are amounts or dates, leave them alone
    assert mask_digits("09/20 13:05") == "09/20 13:05"


def test_redact_replaces_payee_names_with_positions() -> None:
    """The name must be gone whatever language the label is rendered in."""
    from smsledger.i18n import set_language
    from smsledger.summary import label

    for lang in ("en", "ko"):
        set_language(lang)
        hidden = label("SOME LANDLORD", 3, redact=True)
        assert "LANDLORD" not in hidden
        assert "3" in hidden
        assert label("SOME LANDLORD", 3, redact=False) == "SOME LANDLORD"
    set_language(None)


def test_every_language_covers_the_reference_catalogue() -> None:
    """A partial translation falls back, but a shipped one should be complete."""
    import json

    from smsledger.i18n import MESSAGES, available

    ref = json.loads((MESSAGES / "en.json").read_text(encoding="utf-8"))
    for lang in available():
        if lang == "en":
            continue
        got = json.loads((MESSAGES / f"{lang}.json").read_text(encoding="utf-8"))
        missing = set(ref) - set(got)
        assert not missing, f"{lang} is missing: {sorted(missing)}"


def test_missing_key_never_crashes() -> None:
    from smsledger.i18n import t

    assert t("no.such.key") == "no.such.key"
    assert t("no.such.key", count=3) == "no.such.key"


def test_nice_ceiling_rounds_axis_max_to_a_readable_number() -> None:
    """A tick of 12,127,964 reads as noise; nobody checks a bar against it."""
    from smsledger.report import nice_ceiling

    assert nice_ceiling(12_127_964 / 3) == 5_000_000   # -> axis max 15M, ticks 0/5/10/15
    assert nice_ceiling(93) == 100
    assert nice_ceiling(0) == 1.0


def test_compact_is_for_axis_labels_only() -> None:
    from smsledger.report import compact

    assert compact(15_000_000) == "15M"
    assert compact(1_500_000) == "1.5M"
    assert compact(950) == "950"


def test_support_report_carries_no_money_data(tmp_path, monkeypatch) -> None:
    """The file is meant to be sent to a stranger. Enforce what it may contain.

    Facts about the environment go in; facts about money stay out. This is the test
    that keeps the claim printed at the top of the file honest as the code changes.
    """
    import json
    import sys

    home = tmp_path / "home"
    (home / "data" / "stream").mkdir(parents=True)
    (home / "config").mkdir(parents=True)

    secret_merchant = "VERY-SPECIFIC-MERCHANT-NAME"
    secret_amount = "98765432"
    secret_body = "SECRET-MESSAGE-BODY-TEXT"
    (home / "data" / "stream" / "parsed.jsonl").write_text(
        json.dumps({"kind": "card_approve", "amount": int(secret_amount),
                    "merchant": secret_merchant, "desc": secret_merchant,
                    "text": secret_body, "acct_tail": "13579",
                    "date": "2026-09-20", "source": "x"}) + "\n",
        encoding="utf-8")
    (home / "config" / "profile.json").write_text(
        json.dumps({"accounts": [{"id": "a", "alias": "MY PRIVATE ALIAS", "tail": "13579"}],
                    "self_patterns": ["MY REAL NAME"]}), encoding="utf-8")

    monkeypatch.setenv("SMSLEDGER_HOME", str(home))
    for mod in [m for m in list(sys.modules) if m.startswith("smsledger")]:
        del sys.modules[mod]
    from smsledger.support import build

    text = build(days=1)

    for leaked in (secret_merchant, secret_amount, secret_body,
                   "MY PRIVATE ALIAS", "MY REAL NAME", "13579"):
        assert leaked not in text, f"support report leaked {leaked!r}"
    # ...while still being useful
    assert "smsledger support report" in text
    assert "rows" in text and "1" in text


def test_support_report_hides_the_username(tmp_path, monkeypatch) -> None:
    from smsledger.support import tilde
    from pathlib import Path

    assert str(Path.home()) not in tilde(str(Path.home() / "smsledger" / "x.json"))
    assert tilde(str(Path.home() / "a")).startswith("~")


def test_columns_are_measured_in_terminal_cells_not_characters() -> None:
    """A Korean label is fewer characters and more columns than its English twin."""
    from smsledger.i18n import cells, pad

    assert cells("card approvals") == 14
    assert cells("카드 승인") == 9          # four wide glyphs plus the space
    assert len("카드 승인") == 5            # which is why str.ljust cannot be used
    # Both labels must leave the amount starting in the same column.
    assert cells(pad("card approvals", 22)) == 22
    assert cells(pad("카드 승인", 22)) == 22
    assert pad("over the stated width", 3) == "over the stated width"


def test_wrapped_prose_stays_inside_the_terminal_in_either_language() -> None:
    from smsledger.i18n import cells, wrap

    korean = "커서보다 오래된 문자가 남아 있어요. " * 4
    for line in wrap(korean, 60, first="  ! ", rest="    "):
        assert cells(line) <= 60, line
    english = "Phones sync old messages late and the cursor only moves forward. " * 2
    for line in wrap(english, 60, first="  ! ", rest="    "):
        assert cells(line) <= 60, line
    # A single word longer than the width is emitted rather than lost.
    assert wrap("x" * 80, 10) == ["x" * 80]


def test_every_message_key_used_in_code_exists_in_the_catalogue() -> None:
    """A typo in a key is invisible at runtime: ``t`` falls back to the key itself.

    Keys assembled at runtime (``"cli." + name`` in ``__main__``) cannot be found
    this way, which is exactly why a grep for quoted keys once reported nine of
    them as dead. Only literals are checked here.
    """
    import json
    import re
    from pathlib import Path

    from smsledger.i18n import MESSAGES

    ref = json.loads((MESSAGES / "en.json").read_text(encoding="utf-8"))
    # A literal ending in a dot is a prefix being concatenated, not a key.
    pattern = re.compile(r"""\b_t?\(\s*["']([a-z][a-z0-9._]*[a-z0-9])["']""")
    src = Path(MESSAGES).parent
    for path in sorted(src.rglob("*.py")):
        for key in pattern.findall(path.read_text(encoding="utf-8")):
            assert key in ref, f"{path.name} asks for a message that does not exist: {key}"


def test_summary_speaks_korean_all_the_way_down(capsys) -> None:
    """Invented rows -- the point is the wording, not the numbers."""
    from smsledger.i18n import set_language
    from smsledger.summary import report

    rows = [
        {"date": "2026-03-04", "ts": "2026-03-04 10:00", "kind": "card_approve",
         "amount": 12_345, "merchant": "MADE UP SHOP"},
        {"date": "2026-03-05", "ts": "2026-03-05 10:00", "kind": "card_cancel",
         "amount": 345},
        {"date": "2026-03-06", "ts": "2026-03-06 10:00", "kind": "bank_tx",
         "amount": 50_000, "dir": "출금", "desc": "MADE UP TRANSFER",
         "acct_tail": "9999", "balance": 1_000},
        {"date": "2026-03-07", "ts": "2026-03-07 10:00", "kind": "bank_tx",
         "amount": 70_000, "dir": "입금", "acct_tail": "9999", "balance": 71_000},
        {"date": "2026-04-08", "ts": "2026-04-08 10:00", "kind": "corp_card_approve",
         "amount": 9_000},
    ]
    try:
        set_language("ko")
        report(rows, "2026-03-01", "2026-04-30")
        out = capsys.readouterr().out
    finally:
        set_language(None)

    for english in ("Money out", "card approvals", "account withdrawals",
                    "total out", "Money in", "Where it went", "as of", "Not shown"):
        assert english not in out, f"still English: {english!r}"
    assert "summary." not in out and "report.caveat" not in out   # no unresolved keys
    assert "나간 돈" in out and "어디로 나갔나" in out
    assert "12,345" in out                                        # values are untouched


def test_doctor_speaks_korean_all_the_way_down(capsys) -> None:
    from smsledger import doctor
    from smsledger.i18n import set_language

    try:
        set_language("ko")
        doctor.check_sync("")
        doctor.check_coverage({"known": {}}, days=90)
        doctor.check_unknown(
            {"1500-0000": {"money": 4, "sample": "made up", "channel": "sms"},
             "alerts@invented.example": {"money": 3, "sample": "also made up",
                                         "channel": "mail"}},
            dropped=0, days=90)
        out = capsys.readouterr().out
    finally:
        set_language(None)

    for english in ("Phone sync", "Recognised senders", "no parser",
                    "sample:", "nothing arrived"):
        assert english not in out, f"still English: {english!r}"
    assert "doctor." not in out and "arrivals." not in out
    assert "폰에서 오고 있나" in out and "예: made up" in out
    # A mail sender is told where to put it -- "mail", not "sms".
    assert '"mail" 에 넣어요' in out and '"sms" 에 넣어요' in out
