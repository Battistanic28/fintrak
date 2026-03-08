import csv
from datetime import datetime, date as date_type
from pathlib import Path

PROFILES = {
    "chase": {
        "columns": {"Transaction Date", "Description", "Amount", "Category"},
        "map": {
            "date": "Transaction Date",
            "description": "Description",
            "amount": "Amount",
            "category": "Category",
        },
        "negate": True,  # Chase: negative = charge, we want positive = charge
    },
    "capital_one": {
        "columns": {"Transaction Date", "Posted Date", "Card No.", "Description", "Category", "Debit", "Credit"},
        "map": {
            "date": "Transaction Date",
            "description": "Description",
            "category": "Category",
            "debit": "Debit",
            "credit": "Credit",
        },
    },
    "amex": {
        "columns": {"Date", "Description", "Amount"},
        "map": {
            "date": "Date",
            "description": "Description",
            "amount": "Amount",
            "category": "Category",
        },
        "negate": False,  # Amex: positive = charge
    },
    "citi": {
        "columns": {"Status", "Date", "Description", "Debit", "Credit"},
        "map": {
            "date": "Date",
            "description": "Description",
            "debit": "Debit",
            "credit": "Credit",
        },
    },
}

SUPPORTED_EXTENSIONS = {".csv", ".numbers"}


def detect_profile(headers):
    header_set = set(headers)
    for name, profile in PROFILES.items():
        if profile["columns"].issubset(header_set):
            return name, profile
    return None, None


def parse_date(value):
    if isinstance(value, (datetime, date_type)):
        return value.strftime("%Y-%m-%d")
    value = str(value).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%m-%d-%Y"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return value


def parse_amount(value):
    if isinstance(value, (int, float)):
        return float(value)
    if not value or not str(value).strip():
        return 0.0
    cleaned = str(value).strip().replace("$", "").replace(",", "")
    return float(cleaned)


def extract_row(row, profile):
    m = profile["map"]

    date = parse_date(row[m["date"]])
    description = str(row[m["description"]]).strip()
    category = str(row[m["category"]]).strip() if m.get("category") and m["category"] in row and row[m["category"]] else None

    if "debit" in m:
        debit = parse_amount(row.get(m["debit"], ""))
        credit = parse_amount(row.get(m["credit"], ""))
        amount = debit - credit  # positive = spending, negative = payment
    else:
        amount = parse_amount(row[m["amount"]])
        if profile.get("negate"):
            amount = -amount

    return {
        "date": date,
        "description": description,
        "category": category,
        "amount": round(amount, 2),
    }


def _read_csv(filepath):
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = list(reader)
    return headers, rows


def _read_numbers(filepath):
    from numbers_parser import Document

    doc = Document(filepath)
    sheet = doc.sheets[0]
    table = sheet.tables[0]

    # First row is headers
    headers = []
    for col in range(table.num_cols):
        cell = table.cell(0, col)
        headers.append(str(cell.value) if cell.value is not None else "")

    rows = []
    for row_idx in range(1, table.num_rows):
        row = {}
        for col_idx, header in enumerate(headers):
            cell = table.cell(row_idx, col_idx)
            row[header] = cell.value
        rows.append(row)

    return headers, rows


def parse_file(filepath):
    filepath = Path(filepath)
    ext = filepath.suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {ext}\n"
            f"Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    if ext == ".numbers":
        headers, raw_rows = _read_numbers(filepath)
    else:
        headers, raw_rows = _read_csv(filepath)

    profile_name, profile = detect_profile(headers)
    if not profile:
        raise ValueError(
            f"Could not detect card format. Found columns: {headers}\n"
            f"Supported profiles: {', '.join(PROFILES.keys())}"
        )

    rows = []
    for row in raw_rows:
        try:
            rows.append(extract_row(row, profile))
        except (KeyError, ValueError, TypeError):
            continue

    return profile_name, rows


# Keep backward compat alias
parse_csv = parse_file
