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
    assert out.endswith("1105")
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
