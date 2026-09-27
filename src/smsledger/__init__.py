"""Turn bank and card notification messages into ledger rows, without a login.

Collection (macOS Messages + Apple Mail) is country-neutral; parsing is per
locale. South Korea ships today -- see ``locales/`` and CONTRIBUTING.md to add
your own country.

    from smsledger.registry import parse_row

    parse_row({"kind": "hyundai_card", "text": "...", "ts": "2026-09-27 12:00:00"})
"""
__version__ = "0.1.0"
