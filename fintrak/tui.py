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
    add_recurring_item, update_recurring_item, delete_recurring_item,
    get_recurring_items, get_recurring_item_by_id,
    get_monthly_card_spending, get_available_months,
)
from fintrak.importer import parse_csv
from fintrak.analysis import spending_summary, by_category, top_merchants, profit_loss


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


# ── Recurring Item Modal ──────────────────────────────────────────────────────

class RecurringItemModal(ModalScreen[str]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    RecurringItemModal {
        align: center middle;
    }
    RecurringItemModal > #recurring-dialog {
        width: 60;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    RecurringItemModal #recurring-dialog Label {
        margin-bottom: 1;
    }
    RecurringItemModal #recurring-dialog Input, RecurringItemModal #recurring-dialog Select {
        margin-bottom: 1;
    }
    RecurringItemModal #recurring-buttons {
        height: 3;
        align: right middle;
    }
    RecurringItemModal #recurring-buttons Button {
        margin-left: 1;
    }
    RecurringItemModal #recurring-error {
        color: $error;
        margin-bottom: 1;
        display: none;
    }
    """

    def __init__(self, item_id: int | None = None, name: str = "", amount: str = "", item_type: str = "income", paid_via_cc: bool = False) -> None:
        super().__init__()
        self.item_id = item_id
        self._name = name
        self._amount = amount
        self._item_type = item_type
        self._paid_via_cc = paid_via_cc

    def compose(self) -> ComposeResult:
        editing = self.item_id is not None
        title = "Edit Item" if editing else "Add Item"
        with Vertical(id="recurring-dialog"):
            yield Label(f"[b]{title}[/b]")
            yield Label("Name:")
            yield Input(value=self._name, placeholder="e.g. Salary, Rent, Internet", id="recurring-name")
            yield Label("Monthly amount:")
            yield Input(value=self._amount, placeholder="0.00", id="recurring-amount")
            if self._item_type == "expense":
                yield Label("Paid via credit card?")
                yield Select(
                    [("No", "no"), ("Yes", "yes")],
                    value="yes" if self._paid_via_cc else "no",
                    id="recurring-cc",
                    allow_blank=False,
                )
            yield Label("", id="recurring-error")
            with Horizontal(id="recurring-buttons"):
                yield Button("Save", variant="primary", id="btn-recurring-save")
                if editing:
                    yield Button("Delete", variant="error", id="btn-recurring-delete")
                yield Button("Cancel", variant="default", id="btn-recurring-cancel")

    def _show_error(self, msg: str) -> None:
        err = self.query_one("#recurring-error", Label)
        err.update(msg)
        err.styles.display = "block"

    @on(Button.Pressed, "#btn-recurring-cancel")
    def cancel(self) -> None:
        self.dismiss("")

    def action_cancel(self) -> None:
        self.dismiss("")

    @on(Button.Pressed, "#btn-recurring-save")
    def save(self) -> None:
        name = self.query_one("#recurring-name", Input).value.strip()
        amount_str = self.query_one("#recurring-amount", Input).value.strip()
        item_type = self._item_type

        if not name:
            self._show_error("Name is required.")
            return
        try:
            amount = round(float(amount_str), 2)
            if amount <= 0:
                raise ValueError
        except (ValueError, TypeError):
            self._show_error("Amount must be a positive number.")
            return

        paid_via_cc = False
        if self._item_type == "expense":
            paid_via_cc = self.query_one("#recurring-cc", Select).value == "yes"

        conn = get_connection()
        if self.item_id is not None:
            update_recurring_item(conn, self.item_id, name, amount, item_type, paid_via_cc)
            self.dismiss(f"Updated: {name} ${amount:,.2f}")
        else:
            add_recurring_item(conn, name, amount, item_type, paid_via_cc)
            self.dismiss(f"Added: {name} ${amount:,.2f}")
        conn.close()

    @on(Button.Pressed, "#btn-recurring-delete")
    def delete(self) -> None:
        if self.item_id is not None:
            conn = get_connection()
            item = get_recurring_item_by_id(conn, self.item_id)
            delete_recurring_item(conn, self.item_id)
            conn.close()
            name = item["name"] if item else "item"
            self.dismiss(f"Deleted: {name}")


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
    #txn-table, #import-table, #recent-table, #income-table, #expense-table {
        height: 1fr;
        margin: 1;
    }
    #income-buttons, #expense-buttons {
        height: 3;
        margin: 0 1 0 1;
        align: left middle;
    }
    #income-buttons Button, #expense-buttons Button {
        margin-right: 1;
    }
    #income-total, #expense-total {
        height: 1;
        margin: 0 1 1 1;
        padding: 0 1;
        text-align: right;
        text-style: bold;
    }
    .stat-spent {
        border: tall $error;
    }
    #pnl-month-row {
        height: 3;
        margin: 1 1 0 1;
        align: left middle;
    }
    #pnl-month-row Label {
        width: auto;
        height: 3;
        content-align: left middle;
        margin-right: 1;
    }
    #pnl-month-row Select {
        width: 20;
        margin-right: 2;
    }
    #pnl-stats-row {
        height: 5;
        margin: 0 1;
    }
    .stat-income {
        border: tall $success;
    }
    .stat-expenses {
        border: tall $error;
    }
    .stat-net {
        border: tall $warning;
    }
    #pnl-table {
        height: 1fr;
        margin: 1;
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
        Binding("2", "tab_pnl", "P&L", show=False),
        Binding("3", "tab_income", "Income", show=False),
        Binding("4", "tab_expenses", "Key Expenses", show=False),
        Binding("5", "tab_transactions", "Transactions", show=False),
        Binding("6", "tab_imports", "Imports", show=False),
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
        self.pnl_month: str = datetime.now().strftime("%Y-%m")

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
        with TabbedContent("Dashboard", "Income", "Key Expenses", "P&L", "Transactions", "Imports", id="tabs"):
            with TabPane("Dashboard", id="tab-dashboard"):
                yield DateRangeFilter(id="dash-filter")
                with Horizontal(id="stats-row"):
                    yield StatCard("Total Spent", "$0.00", "stat-spent")
                    yield StatCard("Transactions", "0")
                with VerticalScroll(id="dashboard-content"):
                    with Vertical(id="categories-box"):
                        yield Static("Spending by Category", classes="category-title")
                    yield DataTable(id="recent-table")
            with TabPane("P&L", id="tab-pnl"):
                with Horizontal(id="pnl-month-row"):
                    yield Label("Month:")
                    current_month = datetime.now().strftime("%Y-%m")
                    yield Select(
                        [(current_month, current_month)],
                        value=current_month,
                        id="pnl-month-select",
                        allow_blank=False,
                    )
                with Horizontal(id="pnl-stats-row"):
                    yield StatCard("Total Income", "$0.00", "stat-income")
                    yield StatCard("Total Expenses", "$0.00", "stat-expenses")
                    yield StatCard("Net P/L", "$0.00", "stat-net")
                yield DataTable(id="pnl-table")
            with TabPane("Income", id="tab-income"):
                with Horizontal(id="income-buttons"):
                    yield Button("Add Income", variant="success", id="btn-add-income")
                yield DataTable(id="income-table")
                yield Static("", id="income-total")
            with TabPane("Key Expenses", id="tab-expenses"):
                with Horizontal(id="expense-buttons"):
                    yield Button("Add Expense", variant="warning", id="btn-add-expense")
                yield DataTable(id="expense-table")
                yield Static("", id="expense-total")
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

        income_table = self.query_one("#income-table", DataTable)
        income_table.cursor_type = "row"
        income_table.add_columns("Name", "Amount")

        expense_table = self.query_one("#expense-table", DataTable)
        expense_table.cursor_type = "row"
        expense_table.add_columns("Name", "Amount", "Paid via CC")

        pnl_table = self.query_one("#pnl-table", DataTable)
        pnl_table.cursor_type = "row"
        pnl_table.add_columns("Line Item", "Amount")

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
        self._refresh_income()
        self._refresh_expenses()
        self._refresh_transactions()
        self._refresh_imports()
        self._refresh_pnl()

    def _refresh_income(self) -> None:
        conn = get_connection()
        items = get_recurring_items(conn, item_type="income")
        conn.close()

        table = self.query_one("#income-table", DataTable)
        table.clear()
        total = 0.0
        for item in items:
            amt = item["amount"]
            total += amt
            table.add_row(
                item["name"],
                f"[green]${amt:,.2f}[/green]",
                key=str(item["id"]),
            )
        self.query_one("#income-total", Static).update(
            f"{len(items)} items    Total: [green]${total:,.2f}[/green]"
        )

    def _refresh_expenses(self) -> None:
        conn = get_connection()
        items = get_recurring_items(conn, item_type="expense")
        conn.close()

        table = self.query_one("#expense-table", DataTable)
        table.clear()
        total = 0.0
        for item in items:
            amt = item["amount"]
            total += amt
            cc_label = "[yellow]Yes[/yellow]" if item["paid_via_cc"] else "No"
            table.add_row(
                item["name"],
                f"[red]${amt:,.2f}[/red]",
                cc_label,
                key=str(item["id"]),
            )
        self.query_one("#expense-total", Static).update(
            f"{len(items)} items    Total: [red]${total:,.2f}[/red]"
        )

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

    def _refresh_pnl(self) -> None:
        conn = get_connection()
        months = get_available_months(conn)
        current = datetime.now().strftime("%Y-%m")
        if current not in months:
            months.insert(0, current)

        month_select = self.query_one("#pnl-month-select", Select)
        month_options = [(m, m) for m in months]
        with self.prevent(Select.Changed):
            month_select.set_options(month_options)
            if self.pnl_month in months:
                month_select.value = self.pnl_month
            elif months:
                self.pnl_month = months[0]
                month_select.value = months[0]

        items = get_recurring_items(conn)
        card_spending = get_monthly_card_spending(conn, self.pnl_month)
        conn.close()

        pnl = profit_loss(items, card_spending)

        # Update stat cards in the P&L tab
        pnl_stats = list(self.query_one("#pnl-stats-row", Horizontal).query(StatCard))
        if len(pnl_stats) >= 3:
            pnl_stats[0].update_stat("Total Income", f"[green]${pnl['total_income']:,.2f}[/green]")
            pnl_stats[1].update_stat("Total Expenses", f"[red]${pnl['total_expenses']:,.2f}[/red]")
            net = pnl["net"]
            net_color = "green" if net >= 0 else "red"
            net_sign = "" if net >= 0 else "-"
            pnl_stats[2].update_stat("Net P/L", f"[{net_color}]{net_sign}${abs(net):,.2f}[/{net_color}]")

        # Populate P&L table
        table = self.query_one("#pnl-table", DataTable)
        table.clear()

        # Income section
        table.add_row("[bold cyan]INCOME[/bold cyan]", "", key="header-income")
        for item in pnl["income_items"]:
            table.add_row(f"  {item['name']}", f"[green]${item['amount']:,.2f}[/green]", key=f"item-{item['id']}")
        table.add_row("[dim]  Subtotal[/dim]", f"[green bold]${pnl['total_income']:,.2f}[/green bold]", key="subtotal-income")
        table.add_row("", "", key="spacer-1")

        # Recurring expenses section
        table.add_row("[bold cyan]EXPENSES — Recurring[/bold cyan]", "", key="header-recurring")
        for item in pnl["recurring_expense_items"]:
            table.add_row(f"  {item['name']}", f"[red]${item['amount']:,.2f}[/red]", key=f"item-{item['id']}")
        table.add_row("[dim]  Subtotal[/dim]", f"[red]${pnl['total_recurring_expenses']:,.2f}[/red]", key="subtotal-recurring")
        table.add_row("", "", key="spacer-2")

        # Card expenses section
        table.add_row("[bold cyan]EXPENSES — Credit Cards[/bold cyan]", "", key="header-cards")
        for item in pnl["card_expense_items"]:
            table.add_row(f"  {item['card']}", f"[red]${item['amount']:,.2f}[/red]", key=f"card-{item['card']}")
        table.add_row("[dim]  Subtotal[/dim]", f"[red]${pnl['total_card_expenses']:,.2f}[/red]", key="subtotal-cards")
        table.add_row("", "", key="spacer-3")

        # Net line
        net = pnl["net"]
        net_color = "green" if net >= 0 else "red"
        net_sign = "" if net >= 0 else "-"
        table.add_row(
            "[bold]NET PROFIT / LOSS[/bold]",
            f"[{net_color} bold]{net_sign}${abs(net):,.2f}[/{net_color} bold]",
            key="net-total",
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

    def action_tab_income(self) -> None:
        self.query_one(TabbedContent).active = "tab-income"

    def action_tab_expenses(self) -> None:
        self.query_one(TabbedContent).active = "tab-expenses"

    def action_tab_pnl(self) -> None:
        self.query_one(TabbedContent).active = "tab-pnl"

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

    @on(Select.Changed, "#pnl-month-select")
    def on_pnl_month_changed(self, event: Select.Changed) -> None:
        val = str(event.value) if event.value != Select.BLANK else ""
        if val and val != self.pnl_month:
            self.pnl_month = val
            self._refresh_pnl()

    @on(Button.Pressed, "#btn-add-income")
    def on_add_income(self) -> None:
        def on_dismiss(result: str) -> None:
            if result:
                self._toast(result)
                self._refresh_income()
                self._refresh_pnl()
        self.push_screen(RecurringItemModal(item_type="income"), callback=on_dismiss)

    @on(Button.Pressed, "#btn-add-expense")
    def on_add_expense(self) -> None:
        def on_dismiss(result: str) -> None:
            if result:
                self._toast(result)
                self._refresh_expenses()
                self._refresh_pnl()
        self.push_screen(RecurringItemModal(item_type="expense"), callback=on_dismiss)

    @on(DataTable.RowSelected, "#income-table")
    def on_income_row_selected(self, event: DataTable.RowSelected) -> None:
        self._edit_recurring_item(event, "income")

    @on(DataTable.RowSelected, "#expense-table")
    def on_expense_row_selected(self, event: DataTable.RowSelected) -> None:
        self._edit_recurring_item(event, "expense")

    def _edit_recurring_item(self, event: DataTable.RowSelected, item_type: str) -> None:
        if event.row_key is None:
            return
        item_id = int(event.row_key.value)
        conn = get_connection()
        item = get_recurring_item_by_id(conn, item_id)
        conn.close()
        if not item:
            return

        def on_dismiss(result: str) -> None:
            if result:
                self._toast(result)
                if item_type == "income":
                    self._refresh_income()
                else:
                    self._refresh_expenses()
                self._refresh_pnl()

        self.push_screen(
            RecurringItemModal(
                item_id=item["id"],
                name=item["name"],
                amount=str(item["amount"]),
                item_type=item["type"],
                paid_via_cc=bool(item["paid_via_cc"]),
            ),
            callback=on_dismiss,
        )

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
