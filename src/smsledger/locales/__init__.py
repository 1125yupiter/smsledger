"""Locale packages, one per country.

Each subpackage holds that country's wording patterns and its bank parsers.
``registry._load_all()`` imports every module it finds here, so a new locale
needs no wiring anywhere else.

    locales/
      kr/   South Korea -- Hyundai Card, Hana, KB, KB corporate card
      in/   (open) India -- HDFC, ICICI, SBI ...
      id/   (open) Indonesia
      br/   (open) Brazil

Collection is country-neutral: macOS Messages and Apple Mail are read the same
way everywhere. Only the parsing of the message body is local.
"""
