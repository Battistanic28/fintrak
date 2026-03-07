# fintrak

Personal finance CLI toolkit for tracking credit card spending via CSV imports.

## Features

- **Import statements** from Chase, Capital One, Amex, and Citi (CSV and `.numbers` formats)
- **Auto-detect** card format based on column headers
- **Deduplicate** transactions automatically on re-import
- **Spending summaries** with breakdowns by category and top merchants
- **Undo imports** to cleanly revert mistakes
- **Interactive TUI** for browsing and filtering transactions
- All data stored locally in SQLite (`~/.fintrak/fintrak.db`)

## Installation

```bash
pip install -e .
```

Requires Python 3.10+.

## Quick Start

```bash
# Import a statement (creates the card if it doesn't exist)
fintrak import statement.csv --card 4321

# Launch the interactive TUI
fintrak

# View spending summary for the current month
fintrak summary

# View all-time summary
fintrak summary --month all

# Filter by card and month
fintrak summary --card 4321 --month 2025-12
```

## Commands

| Command | Description |
|---------|-------------|
| `fintrak` | Launch the interactive TUI |
| `fintrak import FILE --card LAST4` | Import transactions from a CSV or `.numbers` file |
| `fintrak summary` | Show spending summary, categories, top merchants, and recent transactions |
| `fintrak cards` | List all registered cards |
| `fintrak imports` | List recent import history |
| `fintrak undo IMPORT_ID` | Revert an import and delete its transactions |

### `summary` options

- `--card LAST4` — filter by card
- `--month YYYY-MM` — filter by month (default: current month, use `all` for everything)
- `--limit N` — max transactions to display (default: 50)

## Supported Card Formats

| Profile | Issuer | Detected by columns |
|---------|--------|---------------------|
| `chase` | Chase | Transaction Date, Description, Amount, Category |
| `capital_one` | Capital One | Transaction Date, Posted Date, Card No., Description, Category, Debit, Credit |
| `amex` | American Express | Date, Description, Amount |
| `citi` | Citi | Status, Date, Description, Debit, Credit |

Formats are auto-detected from CSV headers. If your statement doesn't match a known profile, you'll get an error listing the columns found.

## Data Storage

All data lives in `~/.fintrak/fintrak.db` (created automatically on first use). Three tables:

- **cards** — registered cards (identified by last 4 digits)
- **transactions** — all imported transactions, deduplicated by `(card_id, date, description, amount)`
- **imports** — import history for auditing and undo support

## Amount Convention

- **Positive** = spending/charge
- **Negative** = payment/credit

Each card profile handles sign normalization automatically.
