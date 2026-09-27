# smsledger

Turn bank and card notification messages into ledger rows — **without logging in anywhere.**

Reads only the SMS and email that already arrived on your Mac.

- **No login.** No bank website, no scraping, no open-banking API, no account linking.
- **No server.** Runs on your machine and sends nothing anywhere. There is nowhere to send it.
- So nobody else can be holding your financial data. That is structural, not a policy.

Built and verified against **6,249 real notices**.

## Getting started

```bash
pip3 install smsledger
smsledger-setup
```

`smsledger-setup` asks a few plain questions, writes the configuration for you,
reads your messages, builds the report and offers to keep it up to date. After
that, **using this is opening one bookmarked file.** You do not have to touch a
config file or run anything again.

It works with the Python that ships with macOS — there is nothing else to install.

### Language

It follows your Mac's language automatically — Korean and English ship today.
To pin it:

```bash
SMSLEDGER_LANG=en smsledger-setup      # or set "language" in config/profile.json
```

Code and documentation are English so anyone can contribute; **what you read on
screen is not**. Adding a language is one JSON file — see CONTRIBUTING.md.

### What it needs

- **macOS.** The notices are read from `~/Library/Messages/chat.db` and Apple Mail.
- **Your phone's messages on this Mac** — on the phone, Settings > Messages >
  Text Message Forwarding.
- **Full Disk Access**, which is what lets it read the notices your bank already sent
  you. Setup tells you exactly what to do if it is missing, and it stops loudly rather
  than quietly reading nothing.

Not sure any of this applies to you? `smsledger-doctor` answers it in about thirty
seconds without changing anything.

### Keeping it current

`smsledger-setup` offers this at the end; you can also do it later:

```bash
smsledger-agent install     # refresh a few times a day, in the background
smsledger-agent status      # is it running, and did the last run work
smsledger-agent remove      # stop it
```

macOS grants file permission per program, and a background task counts as a different
program from your terminal. So `install` waits for the first run and **tells you if it
was blocked** — an agent that runs on time and silently collects nothing is the worst
kind of broken.

### If you would rather not have a background task

```bash
smsledger-refresh           # collect, parse and rebuild the report, once
```

## If something goes wrong

```bash
smsledger-support
```

Writes one plain-text file with what is needed to diagnose it. **Open it and read it
before sending** — it is deliberately readable.

| In it | Not in it |
|---|---|
| versions, macOS, permissions, row counts | message text, amounts, merchants |
| error traces, background-task status | account numbers, names |
| senders that have no parser yet | your username (replaced with `~`) |

That split is enforced by a test, not by a promise on a page.

Failures are appended to `errors.log` in your data folder as they happen, so a
problem you hit last Tuesday is still answerable today.

To update after a fix ships: `pip3 install -U smsledger`.

## What it handles

| | |
|---|---|
| Approvals and cancellations | Cancellation notices are separated from approvals. Conflate them and spending is counted twice. |
| Foreign currency | Notices with no local amount are converted at a configured rate and flagged `estimated`. |
| Deposits and withdrawals | The masked account tail identifies the account. Balances are read too. |
| Dates with no year | Texts say `09/20`. The year is inferred from the receive time — including across New Year. |
| Corporate cards | Kept under a separate `kind` so they never mix into personal spending. |
| Points and service notices | Non-transactions are recognised and dropped. |

## Two channels, equally

Notices arrive by **SMS** or by **email**, and which one carries your transactions is a
setting on your side — the same bank will use either, both, or neither depending on what you
switched on. Region matters too: Korean issuers lean on SMS, while US issuers default to
email and make SMS opt-in.

So both channels are first-class here. `collect` reads macOS Messages *and* Apple Mail, and a
parser does not care which one a body came from.

Email bodies are HTML templates, which is a different problem from a five-line SMS: stylesheets
and navigation come before anything useful. `strip_html` drops `<style>`/`<script>`/`<head>`
first, and `mail_body_limit` (default 8000) is generous on purpose — truncating the one line
that mattered is the expensive mistake.

## Which countries

Collection is country-neutral. macOS Messages and Apple Mail work the same everywhere;
**only the parsing of a body is local.**

| Locale | Status |
|---|---|
| 🇰🇷 `kr` South Korea | Hyundai Card · Hana Bank · KB Bank · KB corporate card (SMS) |
| elsewhere | **open** — see [CONTRIBUTING.md](CONTRIBUTING.md) |

Adding your country is **one file plus one config line**. Worth doing wherever you would rather
not hand your bank credentials to an aggregator to get your own transactions back.

## Doing it by hand

Every step is a command of its own, and the parsers are importable on their own:

```bash
smsledger-collect           # messages + mail -> notifications.jsonl   (--rescan to sweep all)
smsledger-parse             # -> parsed.jsonl
smsledger-summary           # a summary in the terminal                (--redact to share)
smsledger-report            # the HTML page                            (--redact to share)
```

```python
from smsledger.registry import parse_row

# A real Korean card approval: issuer + "승인" (approved), amount + "일시불"
# (single payment), MM/DD HH:MM, then the merchant.
parse_row({"kind": "hyundai_card", "ts": "2026-09-20 13:05:11",
           "text": "현대카드 승인\n12,300원 일시불\n09/20 13:05\nSOME CAFE"})
# {'kind': 'card_approve', 'amount': 12300, 'installment': '일시불',
#  'date': '2026-09-20', 'merchant': 'SOME CAFE', 'source': 'hyundai_card'}
```

## Configuration

| File | Holds |
|---|---|
| `config/sources.json` | sender numbers / email addresses → parser `kind`; `mail_body_limit` |
| `config/profile.json` | your account and card **tails**, aliases and roles, estimate rates |

**Full account numbers are never accepted.** Notices only carry the tail, so the tail is
enough — and not accepting something is the surest way not to leak it.

`smsledger-setup` writes these for you. Lookup order is
`$SMSLEDGER_HOME/config/*.json` → the shipped `*.example.json` → code defaults, and the
parsers run with no config at all.

## What it does not do

- **No categorisation, budgeting or reporting.** This ends at turning a message into a row.
- No statement/spreadsheet importer. Drop a `data/transactions.csv` next to the output and rows
  are joined on date and amount to set `matched`, but producing that file is out of scope here.
- Not Windows or Linux. There is no `chat.db` to read.

## Design rules

These are promises, not implementation details.

1. **Never guess.** An unreadable amount yields `None`, not `0`. In a ledger a zero-amount row
   is worse than a missing one — it looks settled.
2. **Estimates say so.** Converted foreign amounts carry `estimated: true` and are meant to be
   replaced by the statement.
3. **Loud failure over quiet emptiness.** Missing permission stops with a message. Returning an
   empty list silently is the failure that costs weeks.

## Tests

```bash
pip install -e ".[dev]" && pytest
```

Every `.txt` / `.json` pair under `tests/fixtures/sms/` runs. Amounts, merchants and account
tails in fixtures are **all fabricated**.

## License

MIT.
