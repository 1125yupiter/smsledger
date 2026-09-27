"""Fixture-driven golden tests.

A pull request that adds a parser **does not touch this file**. Drop a pair into
``tests/fixtures/sms/`` -- ``<name>.txt`` (the message body) and ``<name>.json``
(kind, ts, expect) -- and it runs automatically.

``expect`` must equal the parser's output exactly. Asserting on a subset of keys
hides which field broke and when.

Two optional keys:

- ``channel``: ``"sms"`` (default) or ``"mail"``. A mail body has been through
  ``strip_html`` before a parser sees it, so it is one long line; that is a
  different shape, not a different parser, and it needs its own cases.
- ``broken``: a sentence naming a gap the fixture pins **and the fix it wants**.
  The case runs as a strict expected failure, so the expectation in the file is
  the correct output, not today's output. Fixing the parser turns the case red
  until the flag is removed -- which is how the note gets deleted at the same
  time as the bug.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from smsledger.paths import EXAMPLES
from smsledger.registry import REGISTRY, parse_row

FIXTURES = Path(__file__).parent / "fixtures" / "sms"
SPECS = sorted(FIXTURES.glob("*.json"))

assert SPECS, f"no fixtures found: {FIXTURES}"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _case(path: Path):
    reason = _load(path).get("broken")
    if reason:
        return pytest.param(path, marks=pytest.mark.xfail(reason=reason, strict=True))
    return pytest.param(path)


CASES = [_case(p) for p in SPECS]


@pytest.mark.parametrize("spec_path", CASES, ids=lambda p: p.stem)
def test_fixture(spec_path: Path) -> None:
    spec = _load(spec_path)
    body = spec_path.with_suffix(".txt")
    assert body.exists(), f"{spec_path.name} has no matching .txt"

    got = parse_row({"kind": spec["kind"], "ts": spec["ts"],
                     "text": body.read_text(encoding="utf-8")})
    assert got == spec["expect"], spec.get("note") or spec_path.stem


def test_every_registered_kind_has_a_fixture() -> None:
    """Block a parser that ships without a fixture."""
    covered = {_load(p)["kind"] for p in SPECS}
    missing = set(REGISTRY) - covered
    assert not missing, f"kinds with no fixture: {sorted(missing)}"


def test_every_parsed_mail_sender_has_a_mail_fixture() -> None:
    """Email is a first-class channel, so it gets the same rule as a parser.

    ``strip_html`` hands a parser one long line where the same notice over SMS
    arrives as seven short ones. A parser that only ever sees the SMS shape in
    the tests can lose a field on the mail path with every test still green --
    which is what happened to ``desc`` here. Kinds with no parser at all
    (``hyundai_stmt``) are excluded: config lists them so the sender is not
    reported as unknown.
    """
    sources = _load(EXAMPLES / "sources.example.json")
    want = {m["kind"] for m in sources.get("mail") or []} & set(REGISTRY)
    have = {s["kind"] for s in map(_load, SPECS) if s.get("channel") == "mail"}
    assert not want - have, f"mail senders with no mail fixture: {sorted(want - have)}"


def test_unknown_kind_is_skipped_not_crashed() -> None:
    assert parse_row({"kind": "nope", "ts": "", "text": "x"}) == {"skip": "kind"}
