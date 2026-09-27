# Adding your bank or your country

One file, one config line, one fixture pair. No existing code is modified.

## 1. Pick or create a locale

Locales live in `src/smsledger/locales/<cc>/` using the ISO 3166-1 alpha-2 code
(`kr`, `in`, `id`, `br`, `ng`, …). A new locale is a directory with an `__init__.py`
and a `patterns.py`; nothing else needs wiring, because the registry walks the
directory.

Country-specific wording belongs in `patterns.py` — never in `util.py`:

```python
# locales/in/patterns.py
import re

AMT = re.compile(r"(?:INR|Rs\.?)\s*([0-9,]+(?:\.[0-9]{2})?)")
BAL = re.compile(r"(?:Avl Bal|Available Balance)[:\s]*(?:INR|Rs\.?)?\s*([0-9,]+)")

def plain(text: str) -> str:
    return (text or "").strip()

_plain = plain
```

Note grouping differs by locale — India writes `1,23,456`. Stripping commas handles both,
but do not assume a three-digit grouping anywhere.

## 2. The parser — `locales/<cc>/<bank>.py`

```python
from ...registry import register
from ...util import MMDD_HM, _won, year_for
from .patterns import AMT, BAL, _plain


@register("hdfc_alert")          # must match the `kind` in config
def parse_hdfc(text: str, ts: str) -> dict | None:
    lines = [ln.strip() for ln in _plain(text).splitlines() if ln.strip()]
    ...
    return {
        "kind": "bank_tx",       # card_approve | card_cancel | bank_tx
        "amount": amount,
        "date": f"{year_for(ts, mo, da):04d}-{mo:02d}-{da:02d}",
        "desc": counterparty,
        "source": "hdfc_alert",
    }
```

### Contract

- Signature is `(text, ts) -> dict | None`.
- **Return `None` if the message is not yours; return `{"skip": "<reason>"}` if it is yours
  but is not a transaction.** Keep these apart. The first means the sender config is wrong,
  the second is normal. Conflate them and you can never find what went missing.
- **Return `None` when the amount cannot be read. Never `0`, never a guess.**
- Anything that must not count as personal spending gets a `kind` prefix (see `corp_card`).
- Dates without a year must go through `year_for(ts, month, day)`. Reaching for
  `datetime.now().year` fails silently every January.

## 3. A fixture pair — `tests/fixtures/sms/`

`<name>.txt` holds the message body, `<name>.json` the expectation. **You do not write test
code.**

```json
{ "kind": "hdfc_alert", "ts": "2026-09-22 08:15:40",
  "note": "one line on why this case has to exist",
  "expect": { "kind": "bank_tx", "amount": 120500, "...": "the parser's full dict" } }
```

`expect` must equal the output exactly. Do not pass by asserting on a subset of keys.

### ★ Fabricate every value

**Do not put real amounts, merchants, account tails or names in a fixture.** Once committed it
cannot be removed from history, and at that moment this repository is holding someone's
financial records.

Change: amount → anything · merchant → `SOME STORE` · account tail → `12345` · name → `J** D**`.

**Do not change the shape by even one character** — line endings (`\r\n` vs `\n`), spacing,
full-width parentheses, carrier prefixes are all things the parser sees. "Tidying" them makes
the test stop representing a real message.

Minimum set: a normal transaction · a cancellation or an inbound one · a non-transaction notice
(`skip`) · a body whose amount cannot be read (`"expect": null`).

## 3b. If your transactions arrive by email

Nothing extra is needed — a parser receives a body and does not know the channel. Two things
differ in practice:

- **Register the sender address, not a number.** Put it under `mail` in `sources.json`.
- **The body is flattened HTML.** `strip_html` has already removed `<style>`, `<script>` and
  `<head>` and collapsed whitespace, so you get one long line. Anchor on wording
  (`"Transaction of"`, `"at"`, `"Available balance"`) rather than on line positions, which is
  the opposite of how an SMS parser works.

If your issuer's template is unusually large, raise `mail_body_limit` in config. The dedupe
hash uses the untruncated body, so changing it does not re-collect your history as duplicates.

A parser that needs the *whole* message — an itemised order table, a statement attachment —
should read the `.emlx` itself rather than widen the limit for everyone.

**Fixtures work the same way.** Save the flattened body (what `strip_html` returns) as the
`.txt`, not the raw HTML, and fabricate every value in it.

## 4. One config line — `src/smsledger/examples/sources.example.json`

```json
{ "id": "hdfc_sms", "sender": "+911234567890", "kind": "hdfc_alert", "note": "HDFC alerts" }
```

For an email sender, use the `mail` list and an `address`:

```json
{ "id": "chase_alerts", "address": "no.reply.alerts@chase.com", "kind": "chase_alert" }
```

Sender numbers are public information. **Do not put your own account tail or limits in `note`.**

## 5. Check

```bash
pytest
```

`test_every_registered_kind_has_a_fixture` blocks a parser that ships without one.

## Adding a language

Same size of contribution as a parser: **one JSON file**.

1. Copy `src/smsledger/messages/en.json` to `<code>.json` (ISO 639-1: `ja`, `es`, `pt`…).
2. Translate the values. Leave the keys alone. `{placeholders}` must survive.
3. `pytest` — one test asserts a shipped language covers every key in `en.json`.

Missing keys fall back to English rather than failing, so a partial file is already
useful; a shipped one should be complete.

Two things worth knowing:

- **Write for someone who is not technical.** These strings are read by people who
  will not open a config file. "Full Disk Access" is a thing they must find in System
  Settings, so name it exactly as their OS does — translate the sentence, not the menu
  item, unless the OS itself translates it.
- **Language and country are separate.** A Korean-bank user may read English, and the
  locale packages under `locales/` are about *where the money is*, not what language
  the reader wants. Do not put UI text in a locale package.

Detection order: `SMSLEDGER_LANG` → `language` in `config/profile.json` → the OS
→ English. On macOS the OS is read via `defaults read -g AppleLocale`, because
`LANG` is routinely unset in Terminal and always unset under launchd — relying on
`LANG` alone gives a Korean Mac an English interface.

## Reporting a problem

`python3 -m smsledger support` writes everything needed — including any errors already recorded —
so one file is all that needs sending.

- **Not on GitHub?** Email it to [1125.yupiter@gmail.com](mailto:1125.yupiter@gmail.com). `python3 -m smsledger support` will open a draft
  and reveal the file for you.
- **On GitHub?** Open an issue and attach the same file.

If you are adding to it, the rule is the one printed at the top of its output:
**facts about the environment go in, facts about money stay out.** A test
(`test_support_report_carries_no_money_data`) plants known values in a fake home and
asserts none of them reach the file. Extend that test alongside any new section.

## Not accepted

- Code that fetches data by logging in, scraping, or calling an open-banking API. Not doing
  that is the reason this tool can stand without a server.
- Code that sends anything outward — analytics, remote logging, telemetry. Having no network
  calls is this repository's promise.
- Fixtures, logs or screenshots containing real transaction data.
