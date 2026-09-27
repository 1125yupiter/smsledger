# smsledger

Turn bank and card notification messages into ledger rows — **without logging in anywhere.**

Reads only the SMS and email that already arrived on your Mac.

- **No login.** No bank website, no scraping, no open-banking API, no account linking.
- **No server.** Runs on your machine and sends nothing anywhere. There is nowhere to send it.
- So nobody else can be holding your financial data. That is structural, not a policy.

Built and verified against **6,249 real notices**.

## What it handles

| | |
|---|---|
| Approvals and cancellations | Cancellation notices are separated from approvals. Conflate them and spending is counted twice. |
| Foreign currency | Notices with no local amount are converted at a configured rate and flagged `estimated`. |
| Deposits and withdrawals | The masked account tail identifies the account. Balances are read too. |
| Dates with no year | Texts say `09/20`. The year is inferred from the receive time — including across New Year. |
| Corporate cards | Kept under a separate `kind` so they never mix into personal spending. |
| Points and service notices | Non-transactions are recognised and dropped. |

## Which countries

Collection is country-neutral — macOS Messages and Apple Mail work the same everywhere.
**Only the message body parsing is local.**

| Locale | Status |
|---|---|
| 🇰🇷 `kr` South Korea | Hyundai Card · Hana Bank · KB Bank · KB corporate card |
| elsewhere | **open** — see [CONTRIBUTING.md](CONTRIBUTING.md) |

Adding your country is **one file plus one config line**. This works best where banks send
transaction alerts by SMS and you would rather not hand your ledger to an aggregator.

## Requirements

- **macOS.** The data comes from `~/Library/Messages/chat.db` and Apple Mail.
- **Your phone's messages forwarded to this Mac** (Settings > Messages > Text Message Forwarding).
- **Full Disk Access.** Without it collection does not quietly return nothing — it stops loudly.
- Apple Mail is read at `Library/Mail/V10`. A future macOS may move that; known limitation.

## Use

```bash
pip install smsledger

export SMSLEDGER_HOME=~/smsledger        # keep data out of the repo
mkdir -p $SMSLEDGER_HOME/config
cp config/sources.example.json $SMSLEDGER_HOME/config/sources.json

smsledger-collect   # messages + mail -> $SMSLEDGER_HOME/data/stream/notifications.jsonl
smsledger-parse     # -> parsed.jsonl
```

As a library, no files or config needed:

```python
from smsledger.registry import parse_row

# A real Korean card approval looks like this: issuer + "승인" (approved),
# amount + "일시불" (single payment), MM/DD HH:MM, then the merchant.
parse_row({"kind": "hyundai_card", "ts": "2026-09-20 13:05:11",
           "text": "현대카드 승인\n12,300원 일시불\n09/20 13:05\nSOME CAFE"})
# {'kind': 'card_approve', 'amount': 12300, 'installment': '일시불',
#  'date': '2026-09-20', 'merchant': 'SOME CAFE', 'source': 'hyundai_card'}
```

## Configuration

| File | Holds |
|---|---|
| `config/sources.json` | sender numbers / email addresses → parser `kind` |
| `config/profile.json` | your account and card **tails**, aliases and roles, estimate rates |

**Full account numbers are never accepted.** Notices only carry the tail, so the tail is
enough — and not accepting something is the surest way not to leak it.

Lookup order: `$SMSLEDGER_HOME/config/*.json` → the repo's `*.example.json` → code defaults.
Parsers run with no config at all.

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
