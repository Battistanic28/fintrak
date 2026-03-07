from rich.console import Console
from rich.table import Table

console = Console()


def print_cards(cards):
    table = Table(title="Registered Cards")
    table.add_column("ID", style="dim")
    table.add_column("Card", style="cyan bold")
    for card in cards:
        table.add_row(str(card["id"]), f"****{card['last4']}")
    console.print(table)


def print_imports(imports):
    table = Table(title="Import History")
    table.add_column("ID", style="bold")
    table.add_column("Card", style="cyan")
    table.add_column("File")
    table.add_column("Format", style="dim")
    table.add_column("Imported", justify="right", style="green")
    table.add_column("Skipped", justify="right", style="yellow")
    table.add_column("Date", style="dim")
    for imp in imports:
        table.add_row(
            str(imp["id"]),
            f"****{imp['card_last4']}",
            imp["filename"],
            imp["profile"] or "—",
            str(imp["inserted"]),
            str(imp["skipped"]),
            imp["created_at"],
        )
    console.print(table)


def print_transactions(transactions, title="Transactions"):
    table = Table(title=title)
    table.add_column("Date", style="dim")
    table.add_column("Card", style="cyan")
    table.add_column("Description")
    table.add_column("Category", style="green")
    table.add_column("Amount", justify="right")
    for t in transactions:
        amt = t["amount"]
        style = "red" if amt > 0 else "green"
        table.add_row(
            t["date"],
            f"****{t['card_last4']}",
            t["description"][:50],
            t["category"] or "—",
            f"[{style}]${amt:,.2f}[/{style}]",
        )
    console.print(table)


def print_summary(summary):
    table = Table(title="Spending Summary")
    table.add_column("Metric", style="cyan bold")
    table.add_column("Value", justify="right")
    table.add_row("Total Spent", f"[red]${summary['total_spent']:,.2f}[/red]")
    table.add_row("Total Payments/Credits", f"[green]${summary['total_payments']:,.2f}[/green]")
    table.add_row("Net", f"${summary['net']:,.2f}")
    table.add_row("Transactions", str(summary["transaction_count"]))
    table.add_row("Avg Transaction", f"${summary['avg_transaction']:,.2f}")
    console.print(table)


def print_categories(categories):
    if not categories:
        console.print("[yellow]No category data available.[/yellow]")
        return
    table = Table(title="Spending by Category")
    table.add_column("Category", style="cyan")
    table.add_column("Total", justify="right", style="red")
    table.add_column("Count", justify="right")
    table.add_column("", min_width=30)  # bar chart column
    max_total = categories[0]["total"] if categories else 1
    for cat in categories:
        bar_len = int((cat["total"] / max_total) * 30)
        bar = "█" * bar_len
        table.add_row(
            cat["category"],
            f"${cat['total']:,.2f}",
            str(cat["count"]),
            f"[red]{bar}[/red]",
        )
    console.print(table)


def print_top_merchants(merchants):
    if not merchants:
        console.print("[yellow]No merchant data available.[/yellow]")
        return
    table = Table(title="Top Merchants")
    table.add_column("#", style="dim")
    table.add_column("Merchant", style="cyan")
    table.add_column("Total", justify="right", style="red")
    table.add_column("Count", justify="right")
    for i, m in enumerate(merchants, 1):
        table.add_row(str(i), m["description"][:40], f"${m['total']:,.2f}", str(m["count"]))
    console.print(table)
