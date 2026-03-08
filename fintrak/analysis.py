import pandas as pd


def spending_summary(transactions):
    if not transactions:
        return None
    df = _to_dataframe(transactions)
    charges = df[df["amount"] > 0]
    return {
        "total_spent": round(charges["amount"].sum(), 2),
        "transaction_count": len(df),
        "avg_transaction": round(charges["amount"].mean(), 2) if len(charges) else 0,
    }


def by_category(transactions):
    if not transactions:
        return []
    df = _to_dataframe(transactions)
    charges = df[df["amount"] > 0]
    if charges.empty:
        return []
    grouped = charges.groupby("category").agg(
        total=("amount", "sum"),
        count=("amount", "size"),
    ).sort_values("total", ascending=False).reset_index()
    grouped["total"] = grouped["total"].round(2)
    return grouped.to_dict("records")


def top_merchants(transactions, n=10):
    if not transactions:
        return []
    df = _to_dataframe(transactions)
    charges = df[df["amount"] > 0]
    if charges.empty:
        return []
    grouped = charges.groupby("description").agg(
        total=("amount", "sum"),
        count=("amount", "size"),
    ).sort_values("total", ascending=False).head(n).reset_index()
    grouped["total"] = grouped["total"].round(2)
    return grouped.to_dict("records")


def profit_loss(recurring_items, card_spending_rows):
    income_items = []
    recurring_expense_items = []
    for item in recurring_items:
        entry = {"id": item["id"], "name": item["name"], "amount": round(item["amount"], 2)}
        if item["type"] == "income":
            income_items.append(entry)
        else:
            recurring_expense_items.append(entry)

    card_expense_items = [
        {"card": f"****{row['card_last4']}", "amount": round(row["total_spent"], 2)}
        for row in card_spending_rows
    ]

    total_income = round(sum(i["amount"] for i in income_items), 2)
    total_recurring = round(sum(e["amount"] for e in recurring_expense_items), 2)
    total_cards = round(sum(c["amount"] for c in card_expense_items), 2)
    total_expenses = round(total_recurring + total_cards, 2)

    return {
        "income_items": income_items,
        "total_income": total_income,
        "recurring_expense_items": recurring_expense_items,
        "total_recurring_expenses": total_recurring,
        "card_expense_items": card_expense_items,
        "total_card_expenses": total_cards,
        "total_expenses": total_expenses,
        "net": round(total_income - total_expenses, 2),
    }


def _to_dataframe(transactions):
    rows = [dict(t) for t in transactions]
    df = pd.DataFrame(rows)
    df["category"] = df["category"].fillna("Uncategorized")
    return df
