"""Loads and validates uploaded CSV files.

Each of the 6 upload types (ingredients, menu, recipes, sales, purchases,
inventory_counts) is validated independently here: required columns present,
numeric/date fields parseable, no duplicate ids. Cross-file references (e.g.
a recipes row's ingredient_id actually existing) are checked at persistence
time against the database, not here, since this function only sees one
file's rows at a time.
"""
from datetime import datetime

REQUIRED_COLUMNS = {
    "ingredients": ["ingredient_id", "name", "unit", "unit_cost", "pack_size"],
    "menu": ["item_id", "name", "price", "category"],
    "recipes": ["item_id", "ingredient_id", "qty_per_serving"],
    "sales": ["date", "item_id", "qty_sold", "avg_price"],
    "purchases": ["date", "ingredient_id", "qty", "unit_cost", "total"],
    "inventory_counts": ["date", "ingredient_id", "qty_on_hand"],
}

# effective_date (YYYY-MM-DD) back-dates a changed value in the change log. Without
# it a change is effective from the moment of upload.
OPTIONAL_COLUMNS = {
    "ingredients": ["shelf_life_days", "effective_date"],
    "recipes": ["effective_date"],
}

NUMERIC_COLUMNS = {
    "ingredients": ["unit_cost", "pack_size", "shelf_life_days"],
    "menu": ["price"],
    "recipes": ["qty_per_serving"],
    "sales": ["qty_sold", "avg_price"],
    "purchases": ["qty", "unit_cost", "total"],
    "inventory_counts": ["qty_on_hand"],
}

DATE_COLUMNS = {
    "ingredients": ["effective_date"],
    "recipes": ["effective_date"],
    "sales": ["date"],
    "purchases": ["date"],
    "inventory_counts": ["date"],
}

ID_COLUMNS = {
    "ingredients": "ingredient_id",
    "menu": "item_id",
}


def _is_missing(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _is_valid_date(value) -> bool:
    try:
        datetime.strptime(str(value), "%Y-%m-%d")
        return True
    except ValueError:
        return False


def validate_upload(file_type: str, rows: list[dict]) -> dict:
    if file_type not in REQUIRED_COLUMNS:
        return {"status": "error", "row_count": 0, "errors": [f"unknown file_type: {file_type}"]}
    if not rows:
        return {"status": "error", "row_count": 0, "errors": ["file has no rows"]}

    required = REQUIRED_COLUMNS[file_type]
    optional = set(OPTIONAL_COLUMNS.get(file_type, []))
    numeric_cols = NUMERIC_COLUMNS.get(file_type, [])
    date_cols = DATE_COLUMNS.get(file_type, [])
    id_col = ID_COLUMNS.get(file_type)

    errors: list[str] = []
    seen_ids: set[str] = set()

    for i, row in enumerate(rows):
        line = i + 2  # 1-indexed data rows, plus the header row

        missing = [c for c in required if _is_missing(row.get(c))]
        if missing:
            errors.append(f"line {line}: missing required value(s): {', '.join(missing)}")
            continue  # remaining checks need those values

        for col in numeric_cols:
            value = row.get(col)
            if col in optional and _is_missing(value):
                continue
            try:
                num = float(value)
            except (TypeError, ValueError):
                errors.append(f"line {line}: {col} is not numeric: {value!r}")
                continue
            if num < 0:
                errors.append(f"line {line}: {col} must not be negative: {num}")

        for col in date_cols:
            if col in optional and _is_missing(row.get(col)):
                continue
            if not _is_valid_date(row.get(col)):
                errors.append(f"line {line}: {col} is not a valid date (YYYY-MM-DD): {row.get(col)!r}")

        if id_col:
            row_id = row[id_col]
            if row_id in seen_ids:
                errors.append(f"line {line}: duplicate {id_col}: {row_id}")
            seen_ids.add(row_id)

    return {
        "status": "ok" if not errors else "error",
        "row_count": len(rows),
        "errors": errors,
    }
