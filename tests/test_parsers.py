"""Fixture-driven golden tests.

A pull request that adds a parser **does not touch this file**. Drop a pair into
``tests/fixtures/sms/`` -- ``<name>.txt`` (the message body) and ``<name>.json``
(kind, ts, expect) -- and it runs automatically.

``expect`` must equal the parser's output exactly. Asserting on a subset of keys
hides which field broke and when.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from smsledger.registry import REGISTRY, parse_row

FIXTURES = Path(__file__).parent / "fixtures" / "sms"
CASES = sorted(FIXTURES.glob("*.json"))

assert CASES, f"no fixtures found: {FIXTURES}"


@pytest.mark.parametrize("spec_path", CASES, ids=lambda p: p.stem)
def test_fixture(spec_path: Path) -> None:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    body = spec_path.with_suffix(".txt")
    assert body.exists(), f"{spec_path.name} has no matching .txt"

    got = parse_row({"kind": spec["kind"], "ts": spec["ts"],
                     "text": body.read_text(encoding="utf-8")})
    assert got == spec["expect"], spec.get("note") or spec_path.stem


def test_every_registered_kind_has_a_fixture() -> None:
    """Block a parser that ships without a fixture."""
    covered = {json.loads(p.read_text(encoding="utf-8"))["kind"] for p in CASES}
    missing = set(REGISTRY) - covered
    assert not missing, f"kinds with no fixture: {sorted(missing)}"


def test_unknown_kind_is_skipped_not_crashed() -> None:
    assert parse_row({"kind": "nope", "ts": "", "text": "x"}) == {"skip": "kind"}
