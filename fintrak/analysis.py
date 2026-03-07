import pandas as pd


def spending_summary(transactions):
    if not transactions:
        return None
    df = _to_dataframe(transactions)
    charges = df[df["amount"] > 0]
    payments = df[df["amount"] < 0]
    return {
        "total_spent": round(charges["amount"].sum(), 2),
        "total_payments": round(payments["amount"].sum(), 2),
        "net": round(df["amount"].sum(), 2),
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


def _to_dataframe(transactions):
    rows = [dict(t) for t in transactions]
    df = pd.DataFrame(rows)
    df["category"] = df["category"].fillna("Uncategorized")
    return df
