from datetime import datetime
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button, DataTable, Footer, Header, Input, Label,
    Select, Static, TabbedContent, TabPane,
)

from textual_autocomplete import AutoComplete, DropdownItem

from fintrak.db import (
    get_connection, add_card, get_cards, get_card_by_last4,
    create_import, finalize_import, insert_transactions,
    get_transactions, get_earliest_transaction_date,
    get_categories, get_descriptions,
    get_imports, get_import_by_id, delete_import,
)
from fintrak.importer import parse_csv
from fintrak.analysis import spending_summary, by_category, top_merchants


# ── Import Modal ──────────────────────────────────────────────────────────────

class ImportModal(ModalScreen[str]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    ImportModal {
        align: center middle;
    }
    ImportModal > #import-dialog {
        width: 70;
        height: auto;
        max-height: 20;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    ImportModal #import-dialog Label {
        margin-bottom: 1;
    }
    ImportModal #import-dialog Input {
        margin-bottom: 1;
    }
    ImportModal #import-buttons {
        height: 3;
        align: right middle;
    }
    ImportModal #import-buttons Button {
        margin-left: 1;
    }
    ImportModal #import-error {
        color: $error;
        margin-bottom: 1;
        display: none;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="import-dialog"):
            yield Label("[b]Import Statement[/b]")
            yield Label("Statement file path (.csv or .numbers):")
            yield Input(placeholder="/path/to/statement.csv or .numbers", id="csv-path")
            yield Label("Last 4 digits of card:")
            yield Input(placeholder="1234", id="card-last4", max_length=4)
            yield Label("", id="import-error")
            with Horizontal(id="import-buttons"):
                yield Button("Import", variant="primary", id="btn-import")
                yield Button("Cancel", variant="default", id="btn-cancel")

    @on(Button.Pressed, "#btn-cancel")
    def cancel(self) -> None:
        self.dismiss("")

    def action_cancel(self) -> None:
        self.dismiss("")

    @on(Button.Pressed, "#btn-import")
    def do_import(self) -> None:
        self._run_import()

    def _show_error(self, msg: str) -> None:
        err = self.query_one("#import-error", Label)
        err.update(msg)
        err.styles.display = "block"

    def _run_import(self) -> None:
        csv_path = self.query_one("#csv-path", Input).value.strip()
        last4 = self.query_one("#card-last4", Input).value.strip()

        if not csv_path:
            self._show_error("File path is required.")
            return
        path = Path(csv_path).expanduser()
        if not path.exists():
            self._show_error(f"File not found: {path}")
            return
        if not (last4.isdigit() and len(last4) == 4):
            self._show_error("Card must be exactly 4 digits.")
            return

        try:
            profile_name, rows = parse_csv(path)
        except ValueError as e:
            self._show_error(str(e))
            return

        conn = get_connection()
        card_row = get_card_by_last4(conn, last4)
        if not card_row:
            card_id = add_card(conn, last4)
        else:
            card_id = card_row["id"]

        import_id = create_import(conn, card_id, path.name, profile_name)
        inserted, skipped = insert_transactions(conn, card_id, import_id, rows)
        finalize_import(conn, import_id, inserted, skipped)
        conn.close()

        self.dismiss(
            f"Imported {inserted} transactions ({skipped} duplicates skipped) "
            f"from {path.name} to ****{last4}"
        )


# ── Undo Confirmation Modal ──────────────────────────────────────────────────

class UndoModal(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    UndoModal {
        align: center middle;
    }
    UndoModal > #undo-dialog {
        width: 60;
        height: auto;
        border: thick $error;
        background: $surface;
        padding: 1 2;
    }
    UndoModal #undo-buttons {
        height: 3;
        align: right middle;
    }
    UndoModal #undo-buttons Button {
        margin-left: 1;
    }
    """

    def __init__(self, import_id: int, description: str) -> None:
        super().__init__()
        self.import_id = import_id
        self.description = description

    def compose(self) -> ComposeResult:
        with Vertical(id="undo-dialog"):
            yield Label("[b]Undo Import[/b]")
            yield Label(f"\n{self.description}\n")
            yield Label("[yellow]This will delete all transactions from this import.[/yellow]")
            with Horizontal(id="undo-buttons"):
                yield Button("Undo", variant="error", id="btn-confirm-undo")
                yield Button("Cancel", variant="default", id="btn-cancel-undo")

    @on(Button.Pressed, "#btn-cancel-undo")
    def cancel(self) -> None:
        self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#btn-confirm-undo")
    def confirm(self) -> None:
        self.dismiss(True)


# ── Stat Widget ───────────────────────────────────────────────────────────────

class StatCard(Static):
    DEFAULT_CSS = """
    StatCard {
        width: 1fr;
        height: 5;
        content-align: center middle;
        text-align: center;
        border: tall $accent;
        padding: 0 1;
    }
    """

    def __init__(self, label: str, value: str, style_class: str = "") -> None:
        super().__init__()
        self._label = label
        self._value = value
        if style_class:
            self.add_class(style_class)

    def compose(self) -> ComposeResult:
        yield Static(f"[dim]{self._label}[/dim]\n[bold]{self._value}[/bold]")

    def update_stat(self, label: str, value: str) -> None:
        self._label = label
        self._value = value
        try:
            self.query_one(Static).update(f"[dim]{label}[/dim]\n[bold]{value}[/bold]")
        except Exception:
            pass


# ── Category Bar ──────────────────────────────────────────────────────────────

class CategoryBar(Static):
    DEFAULT_CSS = """
    CategoryBar {
        height: 1;
        margin: 0 1;
    }
    """

    def __init__(self, name_: str, total: float, pct: float) -> None:
        super().__init__()
        self._cat_name = name_
        self._total = total
        self._pct = pct

    def render(self) -> str:
        bar_width = int(self._pct * 30)
        bar = "█" * bar_width + "░" * (30 - bar_width)
        return f"{self._cat_name:<20} [red]{bar}[/red] ${self._total:>10,.2f}"


# ── Main App ─────────────────────────────────────────────────────────────────

class DateRangeFilter(Static):
    DEFAULT_CSS = """
    DateRangeFilter {
        height: 3;
        margin: 0 1;
    }
    DateRangeFilter > Horizontal {
        height: 3;
        align: left middle;
    }
    DateRangeFilter .range-label {
        width: auto;
        height: 3;
        content-align: left middle;
        margin-right: 2;
    }
    DateRangeFilter Button {
        min-width: 6;
        height: 3;
        margin: 0 1 0 0;
    }
    """

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label("", id="date-range-label", classes="range-label")
            yield Button("MTD", id="btn-mtd", variant="primary")
            yield Button("YTD", id="btn-ytd", variant="default")
            yield Button("All", id="btn-all", variant="default")


class TransactionFilters(Static):
    DEFAULT_CSS = """
    TransactionFilters {
        height: auto;
        margin: 1 1;
        padding: 1 2;
        border: tall $accent;
    }
    TransactionFilters .filter-row {
        height: 3;
        align: left middle;
        margin-bottom: 1;
    }
    TransactionFilters .filter-row:last-of-type {
        margin-bottom: 0;
    }
    TransactionFilters Label {
        width: auto;
        height: 3;
        content-align: left middle;
        margin: 0 1 0 0;
    }
    TransactionFilters Select {
        width: 28;
        margin: 0 3 0 0;
    }
    TransactionFilters Input {
        width: 18;
        margin: 0 2 0 0;
    }
    TransactionFilters #txn-desc-filter {
        width: 40;
    }
    TransactionFilters Button {
        min-width: 10;
        margin: 0 1 0 0;
    }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(classes="filter-row"):
            yield Label("Card:")
            yield Select(
                [("All Cards", "")],
                value="",
                id="txn-card-filter",
                allow_blank=False,
            )
            yield Label("Category:")
            yield Select(
                [("All Categories", "")],
                value="",
                id="txn-category-filter",
                allow_blank=False,
            )
        with Horizontal(classes="filter-row"):
            yield Label("Description:")
            yield Input(placeholder="Search descriptions...", id="txn-desc-filter")
        with Horizontal(classes="filter-row"):
            yield Label("From:")
            yield Input(placeholder="YYYY-MM-DD", id="txn-date-from")
            yield Label("To:")
            yield Input(placeholder="YYYY-MM-DD", id="txn-date-to")
            yield Button("Apply", variant="primary", id="btn-txn-apply")
            yield Button("Clear", variant="default", id="btn-txn-clear")


class FintrakApp(App):
    CSS = """
    Screen {
        background: $background;
    }
    ToastRack {
        dock: top;
        align: left top;
        margin-bottom: 0;
        margin-top: 1;
    }
    #stats-row {
        height: 5;
        margin: 1 1 0 1;
    }
    #dashboard-content {
        margin: 0 1;
    }
    #categories-box {
        height: auto;
        max-height: 14;
        border: tall $accent;
        margin: 1 0;
        padding: 1;
    }
    #categories-box > .category-title {
        text-style: bold;
        margin-bottom: 1;
    }
    #txn-table, #import-table, #recent-table {
        height: 1fr;
        margin: 1;
    }
    .stat-spent {
        border: tall $error;
    }
    #txn-total {
        height: 1;
        margin: 0 1 1 1;
        padding: 0 1;
        text-align: right;
        text-style: bold;
    }
    #toast-bar {
        dock: bottom;
        height: 1;
        background: $accent;
        color: $text;
        padding: 0 2;
        display: none;
    }
    """

    TITLE = "fintrak"
    BINDINGS = [
        Binding("i", "import_csv", "Import CSV"),
        Binding("r", "refresh_data", "Refresh"),
        Binding("q", "quit", "Quit"),
        Binding("1", "tab_dashboard", "Dashboard", show=False),
        Binding("2", "tab_transactions", "Transactions", show=False),
        Binding("3", "tab_imports", "Imports", show=False),
    ]

    FILTER_MTD = "mtd"
    FILTER_YTD = "ytd"
    FILTER_ALL = "all"

    def __init__(self) -> None:
        super().__init__()
        self.active_filter = self.FILTER_MTD
        self.txn_card_filter: str = ""
        self.txn_category_filter: str = ""
        self.txn_desc_filter: str = ""
        self.txn_date_from: str = ""
        self.txn_date_to: str = ""

    def _get_filter_month(self) -> str:
        now = datetime.now()
        if self.active_filter == self.FILTER_MTD:
            return now.strftime("%Y-%m")
        elif self.active_filter == self.FILTER_YTD:
            return now.strftime("%Y")
        return "all"

    def _get_date_range_text(self) -> str:
        now = datetime.now()
        if self.active_filter == self.FILTER_MTD:
            start = now.replace(day=1).strftime("%b %d, %Y")
            end = now.strftime("%b %d, %Y")
            return f"[bold]Month to Date[/bold]  {start} — {end}"
        elif self.active_filter == self.FILTER_YTD:
            start = now.replace(month=1, day=1).strftime("%b %d, %Y")
            end = now.strftime("%b %d, %Y")
            return f"[bold]Year to Date[/bold]  {start} — {end}"
        conn = get_connection()
        earliest = get_earliest_transaction_date(conn)
        conn.close()
        if earliest:
            start = datetime.strptime(earliest, "%Y-%m-%d").strftime("%b %d, %Y")
            end = now.strftime("%b %d, %Y")
            return f"[bold]All Time[/bold]  {start} — {end}"
        return "[bold]All Time[/bold]"

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent("Dashboard", "Transactions", "Imports", id="tabs"):
            with TabPane("Dashboard", id="tab-dashboard"):
                yield DateRangeFilter(id="dash-filter")
                with Horizontal(id="stats-row"):
                    yield StatCard("Total Spent", "$0.00", "stat-spent")
                    yield StatCard("Transactions", "0")
                with VerticalScroll(id="dashboard-content"):
                    with Vertical(id="categories-box"):
                        yield Static("Spending by Category", classes="category-title")
                    yield DataTable(id="recent-table")
            with TabPane("Transactions", id="tab-transactions"):
                yield TransactionFilters(id="txn-filters")
                yield DataTable(id="txn-table")
                yield Static("", id="txn-total")
            with TabPane("Imports", id="tab-imports"):
                yield DataTable(id="import-table")
        yield Static("", id="toast-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._setup_tables()
        self._update_filter_buttons()
        self._populate_txn_filters()
        self._mount_autocomplete()
        self._refresh_all()

    def _mount_autocomplete(self) -> None:
        self._desc_candidates: list[DropdownItem] = []
        ac = AutoComplete(
            target="#txn-desc-filter",
            candidates=self._get_desc_candidates,
            prevent_default_enter=False,
            prevent_default_tab=True,
            id="desc-autocomplete",
        )
        txn_pane = self.query_one("#tab-transactions", TabPane)
        txn_pane.mount(ac)

    def _get_desc_candidates(self, state) -> list[DropdownItem]:
        return self._desc_candidates

    def _setup_tables(self) -> None:
        for table_id in ("txn-table", "recent-table"):
            table = self.query_one(f"#{table_id}", DataTable)
            table.cursor_type = "row"
            table.add_columns("Date", "Card", "Description", "Category", "Amount")

        imp_table = self.query_one("#import-table", DataTable)
        imp_table.cursor_type = "row"
        imp_table.add_columns("ID", "Card", "File", "Format", "Imported", "Skipped", "Date")

    def _update_filter_buttons(self) -> None:
        range_text = self._get_date_range_text()
        dash_filter = self.query_one("#dash-filter", DateRangeFilter)
        dash_filter.query_one("#date-range-label", Label).update(range_text)
        for btn_id, filter_val in [("#btn-mtd", self.FILTER_MTD), ("#btn-ytd", self.FILTER_YTD), ("#btn-all", self.FILTER_ALL)]:
            btn = dash_filter.query_one(btn_id, Button)
            btn.variant = "primary" if self.active_filter == filter_val else "default"

    def _populate_txn_filters(self) -> None:
        conn = get_connection()
        cards = get_cards(conn)
        categories = get_categories(conn)
        descriptions = get_descriptions(conn)
        conn.close()

        card_options = [("All Cards", "")]
        for c in cards:
            card_options.append((f"****{c['last4']}", str(c["id"])))

        cat_options = [("All Categories", "")]
        for cat in categories:
            cat_options.append((cat, cat))

        card_select = self.query_one("#txn-card-filter", Select)
        card_select.set_options(card_options)

        cat_select = self.query_one("#txn-category-filter", Select)
        cat_select.set_options(cat_options)

        self._desc_candidates = [DropdownItem(d) for d in descriptions]

    def _refresh_all(self) -> None:
        self._populate_txn_filters()
        self._refresh_dashboard()
        self._refresh_transactions()
        self._refresh_imports()

    def _refresh_dashboard(self) -> None:
        conn = get_connection()
        txns = get_transactions(conn, month=self._get_filter_month())
        conn.close()

        stat_cards = self.query(StatCard)
        stats = spending_summary(txns)
        if stats and len(list(stat_cards)) >= 2:
            cards_list = list(self.query(StatCard))
            cards_list[0].update_stat("Total Spent", f"[red]${stats['total_spent']:,.2f}[/red]")
            cards_list[1].update_stat("Transactions", str(stats["transaction_count"]))
        else:
            cards_list = list(self.query(StatCard))
            if len(cards_list) >= 2:
                cards_list[0].update_stat("Total Spent", "$0.00")
                cards_list[1].update_stat("Transactions", "0")

        cats_box = self.query_one("#categories-box", Vertical)
        for bar in self.query(CategoryBar):
            bar.remove()

        cats = by_category(txns)
        if cats:
            max_total = cats[0]["total"]
            for cat in cats[:8]:
                pct = cat["total"] / max_total if max_total else 0
                cats_box.mount(CategoryBar(cat["category"], cat["total"], pct))

        recent = self.query_one("#recent-table", DataTable)
        recent.clear()
        for t in txns[:20]:
            amt = t["amount"]
            amt_str = f"${amt:,.2f}" if amt >= 0 else f"-${abs(amt):,.2f}"
            recent.add_row(
                t["date"],
                f"****{t['card_last4']}",
                t["description"][:40],
                t["category"] or "—",
                amt_str,
            )

    def _refresh_transactions(self) -> None:
        conn = get_connection()
        card_id = int(self.txn_card_filter) if self.txn_card_filter else None
        txns = get_transactions(
            conn,
            card_id=card_id,
            category=self.txn_category_filter or None,
            description=self.txn_desc_filter or None,
            date_from=self.txn_date_from or None,
            date_to=self.txn_date_to or None,
        )
        conn.close()

        table = self.query_one("#txn-table", DataTable)
        table.clear()
        total = 0.0
        for t in txns:
            amt = t["amount"]
            if amt > 0:
                total += amt
            amt_str = f"${amt:,.2f}" if amt >= 0 else f"-${abs(amt):,.2f}"
            table.add_row(
                t["date"],
                f"****{t['card_last4']}",
                t["description"][:50],
                t["category"] or "—",
                amt_str,
            )

        count = len(txns)
        total_str = f"${total:,.2f}" if total >= 0 else f"-${abs(total):,.2f}"
        self.query_one("#txn-total", Static).update(
            f"{count} transactions    Total: [red]{total_str}[/red]"
        )

    def _refresh_imports(self) -> None:
        conn = get_connection()
        import_list = get_imports(conn)
        conn.close()

        table = self.query_one("#import-table", DataTable)
        table.clear()
        for imp in import_list:
            table.add_row(
                str(imp["id"]),
                f"****{imp['card_last4']}",
                imp["filename"],
                imp["profile"] or "—",
                str(imp["inserted"]),
                str(imp["skipped"]),
                imp["created_at"],
                key=str(imp["id"]),
            )

    def _toast(self, message: str) -> None:
        self.notify(message, timeout=4)

    # ── Actions ───────────────────────────────────────────────────────────

    def action_import_csv(self) -> None:
        def on_dismiss(result: str) -> None:
            if result:
                self._toast(result)
                self._refresh_all()

        self.push_screen(ImportModal(), callback=on_dismiss)

    def action_refresh_data(self) -> None:
        self._refresh_all()
        self._toast("Data refreshed")

    def action_tab_dashboard(self) -> None:
        self.query_one(TabbedContent).active = "tab-dashboard"

    def action_tab_transactions(self) -> None:
        self.query_one(TabbedContent).active = "tab-transactions"

    def action_tab_imports(self) -> None:
        self.query_one(TabbedContent).active = "tab-imports"

    # ── Events ────────────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn-mtd")
    def on_filter_mtd(self) -> None:
        self._set_filter(self.FILTER_MTD)

    @on(Button.Pressed, "#btn-ytd")
    def on_filter_ytd(self) -> None:
        self._set_filter(self.FILTER_YTD)

    @on(Button.Pressed, "#btn-all")
    def on_filter_all(self) -> None:
        self._set_filter(self.FILTER_ALL)

    def _set_filter(self, filter_val: str) -> None:
        self.active_filter = filter_val
        self._update_filter_buttons()
        self._refresh_dashboard()

    @on(Select.Changed, "#txn-card-filter")
    def on_txn_card_changed(self, event: Select.Changed) -> None:
        self.txn_card_filter = str(event.value) if event.value != Select.BLANK else ""

    @on(Select.Changed, "#txn-category-filter")
    def on_txn_category_changed(self, event: Select.Changed) -> None:
        self.txn_category_filter = str(event.value) if event.value != Select.BLANK else ""

    @on(Button.Pressed, "#btn-txn-apply")
    @on(Input.Submitted, "#txn-date-from")
    @on(Input.Submitted, "#txn-date-to")
    @on(Input.Submitted, "#txn-desc-filter")
    def on_txn_apply(self) -> None:
        self.txn_desc_filter = self.query_one("#txn-desc-filter", Input).value.strip()
        self.txn_date_from = self.query_one("#txn-date-from", Input).value.strip()
        self.txn_date_to = self.query_one("#txn-date-to", Input).value.strip()
        self._refresh_transactions()

    @on(Button.Pressed, "#btn-txn-clear")
    def on_txn_clear(self) -> None:
        self.txn_card_filter = ""
        self.txn_category_filter = ""
        self.txn_desc_filter = ""
        self.txn_date_from = ""
        self.txn_date_to = ""
        self.query_one("#txn-card-filter", Select).value = ""
        self.query_one("#txn-category-filter", Select).value = ""
        self.query_one("#txn-desc-filter", Input).value = ""
        self.query_one("#txn-date-from", Input).value = ""
        self.query_one("#txn-date-to", Input).value = ""
        self._refresh_transactions()

    @on(DataTable.RowSelected, "#import-table")
    def on_import_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key is None:
            return
        import_id = int(event.row_key.value)

        conn = get_connection()
        imp = get_import_by_id(conn, import_id)
        conn.close()
        if not imp:
            return

        desc = (
            f"Import #{imp['id']}: {imp['filename']} -> ****{imp['card_last4']}\n"
            f"{imp['inserted']} transactions imported on {imp['created_at']}"
        )

        def on_dismiss(confirmed: bool) -> None:
            if confirmed:
                conn = get_connection()
                count = delete_import(conn, import_id)
                conn.close()
                self._toast(f"Reverted: {count} transactions deleted")
                self._refresh_all()

        self.push_screen(UndoModal(import_id, desc), callback=on_dismiss)


def main():
    app = FintrakApp()
    app.run()
