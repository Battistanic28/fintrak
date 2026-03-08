# fintrak

Personal finance CLI toolkit for tracking credit card spending via CSV imports.

## Features

- **Import statements** from Chase, Capital One, Amex, and Citi (CSV and `.numbers` formats)
- **Auto-detect** card format based on column headers
- **Deduplicate** transactions automatically on re-import
- **Spending summaries** with breakdowns by category and top merchants
- **Profit & Loss tracking** with configurable recurring income and expenses
- **Undo imports** to cleanly revert mistakes
- **Interactive TUI** for browsing and filtering transactions
- **Wildcard search** — use `*` in description filters (e.g. `AMAZON*`)
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

## Profit & Loss

The TUI includes a P&L tab for monthly profit/loss tracking. It combines:

- **Recurring income** — configurable sources (e.g. salary, freelance)
- **Recurring expenses** — configurable fixed costs (e.g. rent, HOA, internet, utilities)
- **Credit card spending** — pulled automatically from imported transactions, broken down per card

Use the "Add Income" and "Add Expense" buttons to configure recurring items. Click any recurring item row to edit or delete it. Select a month from the dropdown to view historical P&L.

## Data Storage

All data lives in `~/.fintrak/fintrak.db` (created automatically on first use). Four tables:

- **cards** — registered cards (identified by last 4 digits)
- **transactions** — all imported transactions, deduplicated by `(card_id, date, description, amount)`
- **imports** — import history for auditing and undo support
- **recurring_items** — configured recurring income and expense entries for P&L

## TUI Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1` | Dashboard tab |
| `2` | Transactions tab |
| `3` | Imports tab |
| `4` | P&L tab |
| `i` | Import CSV |
| `r` | Refresh data |
| `q` | Quit |

## Amount Convention

- **Positive** = spending/charge
- **Negative** = payment/credit

Each card profile handles sign normalization automatically.
