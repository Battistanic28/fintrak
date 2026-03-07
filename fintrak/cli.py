import sys
import click
from datetime import datetime
from pathlib import Path
from rich.console import Console

from fintrak.db import (
    get_connection, add_card, get_cards, get_card_by_last4,
    create_import, finalize_import, insert_transactions,
    get_transactions, get_imports, get_import_by_id, delete_import,
)
from fintrak.importer import parse_csv
from fintrak.analysis import spending_summary, by_category, top_merchants

console = Console()


@click.group(invoke_without_command=True)
@click.version_option(package_name="fintrak")
@click.pass_context
def cli(ctx):
    """fintrak — personal finance tracking TUI"""
    if ctx.invoked_subcommand is None:
        from fintrak.tui import main
        main()


@cli.command("import")
@click.argument("csv_file", type=click.Path(exists=True, path_type=Path))
@click.option("--card", required=True, help="Last 4 digits of the card (created if it doesn't exist)")
def import_cmd(csv_file, card):
    """Import transactions from a credit card CSV statement."""
    if not (card.isdigit() and len(card) == 4):
        console.print("[red]Error:[/red] --card must be exactly 4 digits (last 4 of your card number)")
        raise SystemExit(1)

    conn = get_connection()

    card_row = get_card_by_last4(conn, card)
    if not card_row:
        card_id = add_card(conn, card)
        console.print(f"[green]Created new card:[/green] ****{card} (id={card_id})")
    else:
        card_id = card_row["id"]
        console.print(f"Using existing card: [cyan]****{card}[/cyan] (id={card_id})")

    try:
        profile_name, rows = parse_csv(csv_file)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)

    console.print(f"Detected format: [cyan]{profile_name}[/cyan]")
    console.print(f"Parsed [bold]{len(rows)}[/bold] transactions from {csv_file.name}")

    import_id = create_import(conn, card_id, csv_file.name, profile_name)
    inserted, skipped = insert_transactions(conn, card_id, import_id, rows)
    finalize_import(conn, import_id, inserted, skipped)
    console.print(f"[green]{inserted} new[/green] transactions imported, [yellow]{skipped} duplicates[/yellow] skipped")
    console.print(f"Import ID: [bold]{import_id}[/bold] (use [cyan]fintrak undo {import_id}[/cyan] to revert)")
    conn.close()


@cli.command()
@click.option("--card", default=None, help="Filter by last 4 digits of card")
@click.option("--month", default=None, help="Month as YYYY-MM, or 'all' for everything (default: current month)")
@click.option("--limit", default=50, help="Max transactions to display")
def summary(card, month, limit):
    """Show spending summary and recent transactions."""
    from fintrak.display import (
        print_transactions, print_summary,
        print_categories, print_top_merchants,
    )
    conn = get_connection()
    card_id = None
    if card:
        card_row = get_card_by_last4(conn, card)
        if not card_row:
            console.print(f"[red]Card not found:[/red] ****{card}")
            raise SystemExit(1)
        card_id = card_row["id"]

    if month is None:
        month = datetime.now().strftime("%Y-%m")

    txns = get_transactions(conn, card_id=card_id, month=month)
    if not txns:
        console.print("[yellow]No transactions found for the given filters.[/yellow]")
        conn.close()
        return

    label = "all time" if month == "all" else month
    console.print(f"\n[bold]Summary for {label}[/bold]")

    stats = spending_summary(txns)
    if stats:
        print_summary(stats)

    cats = by_category(txns)
    print_categories(cats)

    merchants = top_merchants(txns)
    print_top_merchants(merchants)

    console.print(f"\n[bold]Recent Transactions[/bold] (showing up to {limit})")
    print_transactions(txns[:limit], title=f"Transactions — {label}")
    conn.close()


@cli.command()
def cards():
    """List all registered cards."""
    from fintrak.display import print_cards
    conn = get_connection()
    card_list = get_cards(conn)
    if not card_list:
        console.print("[yellow]No cards registered yet. Import a statement to get started.[/yellow]")
    else:
        print_cards(card_list)
    conn.close()


@cli.command()
def imports():
    """List recent imports."""
    from fintrak.display import print_imports
    conn = get_connection()
    import_list = get_imports(conn)
    if not import_list:
        console.print("[yellow]No imports yet.[/yellow]")
    else:
        print_imports(import_list)
    conn.close()


@cli.command()
@click.argument("import_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def undo(import_id, yes):
    """Revert an import by its ID. Deletes all transactions from that import."""
    conn = get_connection()
    imp = get_import_by_id(conn, import_id)
    if not imp:
        console.print(f"[red]Import {import_id} not found.[/red]")
        raise SystemExit(1)

    console.print(f"Import [bold]{import_id}[/bold]: {imp['filename']} -> ****{imp['card_last4']} "
                  f"({imp['inserted']} transactions, {imp['created_at']})")

    if not yes:
        click.confirm("Delete all transactions from this import?", abort=True)

    count = delete_import(conn, import_id)
    console.print(f"[green]Reverted:[/green] {count} transactions deleted")
    conn.close()


if __name__ == "__main__":
    cli()
