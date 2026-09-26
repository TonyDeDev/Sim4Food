"""Loads the demo restaurant dataset from backend/data/demo/*.csv."""
import csv
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parents[1] / "data" / "demo"

TABLES = ["ingredients", "menu", "recipes", "sales", "purchases", "inventory_counts", "events"]

NUMERIC_COLUMNS = {
    "ingredients": ["unit_cost", "pack_size", "shelf_life_days"],
    "menu": ["price"],
    "recipes": ["qty_per_serving"],
    "sales": ["qty_sold", "avg_price"],
    "purchases": ["qty", "unit_cost", "total"],
    "inventory_counts": ["qty_on_hand"],
    "events": ["discount_pct", "expected_lift"],
}


def _coerce(file_type: str, row: dict) -> dict:
    numeric_cols = set(NUMERIC_COLUMNS.get(file_type, []))
    out = {}
    for key, value in row.items():
        if value == "" or value is None:
            out[key] = None
        elif key in numeric_cols:
            out[key] = float(value)
        else:
            out[key] = value
    return out


def _load_table(file_type: str) -> list[dict]:
    path = DEMO_DIR / f"{file_type}.csv"
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [_coerce(file_type, row) for row in csv.DictReader(f)]


def _load_customer_profile() -> dict:
    """customer_profile.csv holds two side-by-side tables from the source
    workbook - a segments table and a settings table (daily_customers_estimate,
    busy_days) - joined into one sheet with a blank separator column. Split
    them back into the shape described for customer_profile.json.
    """
    path = DEMO_DIR / "customer_profile.csv"
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    segments = [
        {
            "name": row["segment"],
            "share": float(row["share"]),
            "price_sensitivity": float(row["price_sensitivity"]),
            "likes": [like.strip() for like in row["likes"].split(",")],
        }
        for row in rows
        if row.get("segment")
    ]

    settings = {row["setting"]: row["value"] for row in rows if row.get("setting")}
    busy_days = settings.get("busy_days") or ""

    return {
        "daily_customers_estimate": float(settings["daily_customers_estimate"]),
        "busy_days": [d.strip() for d in busy_days.split(",")] if busy_days else [],
        "segments": segments,
    }


def generate_demo_dataset() -> dict:
    data = {table: _load_table(table) for table in TABLES}
    data["customer_profile"] = _load_customer_profile()
    return data
