import sqlite3
from pathlib import Path

DB_DIR = Path.home() / ".fintrak"
DB_PATH = DB_DIR / "fintrak.db"


def get_connection():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _create_tables(conn)
    return conn


def _create_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cards (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            last4       TEXT NOT NULL UNIQUE,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS imports (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id     INTEGER NOT NULL REFERENCES cards(id),
            filename    TEXT NOT NULL,
            profile     TEXT,
            inserted    INTEGER NOT NULL DEFAULT 0,
            skipped     INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id     INTEGER NOT NULL REFERENCES cards(id),
            import_id   INTEGER REFERENCES imports(id),
            date        TEXT NOT NULL,
            description TEXT NOT NULL,
            category    TEXT,
            amount      REAL NOT NULL,
            created_at  TEXT DEFAULT (datetime('now')),
            UNIQUE(card_id, date, description, amount)
        );

        CREATE TABLE IF NOT EXISTS recurring_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            amount      REAL NOT NULL,
            type        TEXT NOT NULL CHECK(type IN ('income', 'expense')),
            created_at  TEXT DEFAULT (datetime('now')),
            updated_at  TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()


def add_card(conn, last4):
    cur = conn.execute(
        "INSERT INTO cards (last4) VALUES (?)",
        (last4,),
    )
    conn.commit()
    return cur.lastrowid


def get_cards(conn):
    return conn.execute("SELECT * FROM cards ORDER BY id").fetchall()


def get_card_by_last4(conn, last4):
    return conn.execute(
        "SELECT * FROM cards WHERE last4 = ?", (last4,)
    ).fetchone()


def create_import(conn, card_id, filename, profile):
    cur = conn.execute(
        "INSERT INTO imports (card_id, filename, profile) VALUES (?, ?, ?)",
        (card_id, filename, profile),
    )
    conn.commit()
    return cur.lastrowid


def finalize_import(conn, import_id, inserted, skipped):
    conn.execute(
        "UPDATE imports SET inserted = ?, skipped = ? WHERE id = ?",
        (inserted, skipped, import_id),
    )
    conn.commit()


def insert_transactions(conn, card_id, import_id, rows):
    inserted = 0
    skipped = 0
    for row in rows:
        try:
            conn.execute(
                """INSERT INTO transactions (card_id, import_id, date, description, category, amount)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (card_id, import_id, row["date"], row["description"], row.get("category"), row["amount"]),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1
    conn.commit()
    return inserted, skipped


def get_imports(conn, limit=20):
    return conn.execute(
        """SELECT i.*, c.last4 as card_last4
           FROM imports i JOIN cards c ON i.card_id = c.id
           ORDER BY i.id DESC LIMIT ?""",
        (limit,),
    ).fetchall()


def get_import_by_id(conn, import_id):
    return conn.execute(
        """SELECT i.*, c.last4 as card_last4
           FROM imports i JOIN cards c ON i.card_id = c.id
           WHERE i.id = ?""",
        (import_id,),
    ).fetchone()


def delete_import(conn, import_id):
    count = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE import_id = ?", (import_id,)
    ).fetchone()[0]
    conn.execute("DELETE FROM transactions WHERE import_id = ?", (import_id,))
    conn.execute("DELETE FROM imports WHERE id = ?", (import_id,))
    conn.commit()
    return count


def get_earliest_transaction_date(conn):
    row = conn.execute("SELECT MIN(date) as earliest FROM transactions").fetchone()
    return row["earliest"] if row else None


def get_descriptions(conn):
    rows = conn.execute(
        "SELECT DISTINCT description FROM transactions ORDER BY description"
    ).fetchall()
    return [r["description"] for r in rows]


def get_categories(conn):
    rows = conn.execute(
        "SELECT DISTINCT category FROM transactions WHERE category IS NOT NULL ORDER BY category"
    ).fetchall()
    return [r["category"] for r in rows]


def add_recurring_item(conn, name, amount, item_type):
    cur = conn.execute(
        "INSERT INTO recurring_items (name, amount, type) VALUES (?, ?, ?)",
        (name, amount, item_type),
    )
    conn.commit()
    return cur.lastrowid


def update_recurring_item(conn, item_id, name, amount, item_type):
    conn.execute(
        "UPDATE recurring_items SET name = ?, amount = ?, type = ?, updated_at = datetime('now') WHERE id = ?",
        (name, amount, item_type, item_id),
    )
    conn.commit()


def delete_recurring_item(conn, item_id):
    conn.execute("DELETE FROM recurring_items WHERE id = ?", (item_id,))
    conn.commit()


def get_recurring_items(conn, item_type=None):
    if item_type:
        return conn.execute(
            "SELECT * FROM recurring_items WHERE type = ? ORDER BY name", (item_type,)
        ).fetchall()
    return conn.execute("SELECT * FROM recurring_items ORDER BY type, name").fetchall()


def get_recurring_item_by_id(conn, item_id):
    return conn.execute(
        "SELECT * FROM recurring_items WHERE id = ?", (item_id,)
    ).fetchone()


def get_monthly_card_spending(conn, month):
    return conn.execute(
        """SELECT c.last4 AS card_last4, SUM(t.amount) AS total_spent
           FROM transactions t JOIN cards c ON t.card_id = c.id
           WHERE t.amount > 0 AND strftime('%Y-%m', t.date) = ?
           GROUP BY c.last4
           ORDER BY total_spent DESC""",
        (month,),
    ).fetchall()


def get_available_months(conn):
    rows = conn.execute(
        "SELECT DISTINCT strftime('%Y-%m', date) AS month FROM transactions ORDER BY month DESC"
    ).fetchall()
    return [r["month"] for r in rows]


def get_transactions(conn, card_id=None, month=None, category=None, description=None, date_from=None, date_to=None):
    query = "SELECT t.*, c.last4 as card_last4 FROM transactions t JOIN cards c ON t.card_id = c.id WHERE 1=1"
    params = []
    if card_id:
        query += " AND t.card_id = ?"
        params.append(card_id)
    if month and month != "all":
        if len(month) == 4:
            query += " AND strftime('%Y', t.date) = ?"
        else:
            query += " AND strftime('%Y-%m', t.date) = ?"
        params.append(month)
    if category:
        query += " AND t.category = ?"
        params.append(category)
    if description:
        query += " AND t.description LIKE ?"
        if "*" in description:
            params.append(description.replace("*", "%"))
        else:
            params.append(f"%{description}%")
    if date_from:
        query += " AND t.date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND t.date <= ?"
        params.append(date_to)
    query += " ORDER BY t.date DESC"
    return conn.execute(query, params).fetchall()
