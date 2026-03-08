# fintrak

Personal finance CLI toolkit for tracking credit card spending via CSV imports.

## Features

- **Import statements** from Chase, Capital One, Amex, Citi, and US Bank (CSV and `.numbers` formats)
- **Auto-detect** card format based on column headers
- **Deduplicate** transactions automatically on re-import
- **Spending summaries** with breakdowns by category and top merchants
- **Profit & Loss tracking** with configurable recurring income and expenses
- **Expense breakdown chart** showing spending by category on the P&L tab
- **Export P&L reports** as formatted Excel spreadsheets with charts
- **Undo imports** to cleanly revert mistakes
- **Interactive TUI** with tabs for P&L, Income, Key Expenses, Transactions, and Imports
- **Transaction filtering** by card, category, month, year, and description (supports `*` wildcards)
- All data stored locally in SQLite (`~/.fintrak/fintrak.db`)

## Installation

```bash
pip install -e .
```

Requires Python 3.10+.

## Quick Start

```bash
# Launch the interactive TUI
fintrak

# Import a statement (creates the card if it doesn't exist)
fintrak import statement.csv --card 4321

# View spending summary for the current month
fintrak summary

# Export P&L report for the current month
fintrak export

# Export P&L report for a specific month
fintrak export --month 2026-02
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `fintrak` | Launch the interactive TUI |
| `fintrak import FILE --card LAST4` | Import transactions from a CSV or `.numbers` file |
| `fintrak summary` | Show spending summary, categories, top merchants, and recent transactions |
| `fintrak export` | Export a P&L report as an Excel spreadsheet |
| `fintrak cards` | List all registered cards |
| `fintrak imports` | List recent import history |
| `fintrak undo IMPORT_ID` | Revert an import and delete its transactions |

### `import` options

- `--card LAST4` (required) — last 4 digits of the card number (created automatically if new)

### `summary` options

- `--card LAST4` — filter by card
- `--month YYYY-MM` — filter by month (default: current month, use `all` for everything)
- `--limit N` — max transactions to display (default: 50)

### `export` options

- `--month YYYY-MM` — month to export (default: current month)
- `-o, --output PATH` — output file path (default: `exports/pnl-YYYY-MM.xlsx`)

### `undo` options

- `-y, --yes` — skip confirmation prompt

## Interactive TUI

Launch with `fintrak` (no subcommand). The TUI has five tabs:

| Tab | Description |
|-----|-------------|
| **P&L** | Monthly profit & loss report with income, recurring expenses, credit card spending, expense breakdown chart, and an Export button |
| **Income** | Add, edit, and delete recurring income sources (e.g. salary, freelance) |
| **Key Expenses** | Add, edit, and delete recurring expenses with a "Paid via CC" flag to avoid double-counting |
| **Transactions** | Browse and filter all imported transactions by card, category, month, year, and description |
| **Imports** | View import history and undo imports |

### TUI Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1` | P&L tab |
| `2` | Income tab |
| `3` | Key Expenses tab |
| `4` | Transactions tab |
| `5` | Imports tab |
| `i` | Import CSV |
| `r` | Refresh data |
| `q` | Quit |

## Supported Card Formats

| Profile | Issuer | Detected by columns |
|---------|--------|---------------------|
| `chase` | Chase | Transaction Date, Description, Amount, Category |
| `capital_one` | Capital One | Transaction Date, Posted Date, Card No., Description, Category, Debit |
| `amex` | American Express | Date, Description, Amount |
| `citi` | Citi | Status, Date, Description, Debit, Credit |
| `us_bank` | US Bank | Transaction, Amount, Category |

Formats are auto-detected from CSV headers. If your statement doesn't match a known profile, you'll get an error listing the columns found.

## Data Storage

All data lives in `~/.fintrak/fintrak.db` (created automatically on first use). Four tables:

- **cards** — registered cards (identified by last 4 digits)
- **transactions** — all imported transactions, deduplicated by `(card_id, date, description, amount)`
- **imports** — import history for auditing and undo support
- **recurring_items** — configured recurring income and expense entries for P&L

## Amount Convention

- **Positive** = spending/charge
- **Negative** = payment/credit

Each card profile handles sign normalization automatically.
