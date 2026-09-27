"""How each upload file must be laid out, for the assistant on the Records tab.

Column lists come from sim.ingest (the validator the upload actually runs), so
this guide can never drift from what an upload accepts. Only the plain-language
meaning and the example values live here.
"""
from sim import ingest

UPLOAD_ORDER = ["ingredients", "menu", "recipes", "sales", "purchases", "inventory_counts", "events"]

LABELS = {
    "ingredients": "Ingredients",
    "menu": "Menu",
    "recipes": "Recipes",
    "sales": "POS / sales history",
    "purchases": "Purchases",
    "inventory_counts": "Inventory counts",
    "events": "Deals and holidays",
}

PURPOSE = {
    "ingredients": "Every ingredient you buy, with its unit, cost and pack size.",
    "menu": "Every dish you sell and its menu price.",
    "recipes": "How much of each ingredient one serving of a dish uses. One row per dish and ingredient.",
    "sales": "Dishes sold per day, from the POS. One row per day and dish.",
    "purchases": "What you bought from suppliers, one row per delivery line.",
    "inventory_counts": "Stock counted on the shelf, one row per count date and ingredient.",
    "events": "Past and planned deals and holidays. Uploading replaces the whole list.",
}

MEANING = {
    "ingredient_id": "Your short code for the ingredient, no spaces (e.g. chicken). Must match across files.",
    "item_id": "Your short code for the dish, no spaces (e.g. chicken_wrap). Must match across files.",
    "name": "Display name.",
    "unit": "Unit you count it in: kg, L, each, head...",
    "unit_cost": "Cost per unit, a plain number without $.",
    "pack_size": "How many units come in one supplier pack.",
    "shelf_life_days": "Days it keeps (7 or less counts as perishable).",
    "effective_date": "Date a changed cost or recipe starts to apply (YYYY-MM-DD). Leave empty for 'now'.",
    "price": "Menu price, a plain number without $.",
    "category": "Menu section, e.g. main, side, salad.",
    "qty_per_serving": "Amount of the ingredient in one serving, in the ingredient's unit.",
    "date": "Date as YYYY-MM-DD.",
    "qty_sold": "Servings sold that day.",
    "avg_price": "Average price actually charged that day (after discounts).",
    "qty": "Quantity received, in the ingredient's unit.",
    "total": "Line total paid.",
    "qty_on_hand": "Quantity counted on the shelf.",
    "start_date": "First day of the event (YYYY-MM-DD).",
    "end_date": "Last day of the event (YYYY-MM-DD).",
    "type": "holiday or deal.",
    "items": "Dish item_ids the event applies to, separated by commas. Empty means every dish.",
    "discount_pct": "Discount, as 0.2 or 20 for 20%.",
    "expected_lift": "Your own guess of the sales increase, as 0.3 or 30 for +30%. Optional.",
}

EXAMPLES = {
    "ingredients": [
        ["chicken", "Chicken breast", "kg", "11.5", "5", "4", ""],
        ["tortilla", "Flour tortilla 12in", "each", "0.35", "48", "30", ""],
    ],
    "menu": [["chicken_wrap", "Chicken Wrap", "13", "main"], ["fries", "Fries", "5", "side"]],
    "recipes": [["chicken_wrap", "chicken", "0.15", ""], ["chicken_wrap", "tortilla", "1", ""]],
    "sales": [["2026-09-14", "chicken_wrap", "42", "13.0"], ["2026-09-14", "fries", "30", "5.0"]],
    "purchases": [["2026-09-14", "chicken", "40", "11.5", "460.0"], ["2026-09-17", "chicken", "35", "11.5", "402.5"]],
    "inventory_counts": [["2026-09-20", "chicken", "4.5"], ["2026-09-20", "tortilla", "34"]],
    "events": [
        ["2026-10-09", "2026-10-11", "deal", "Pasta Special", "penne_alfredo", "0.2", ""],
        ["2026-10-12", "2026-10-12", "holiday", "Thanksgiving", "", "", ""],
    ],
}

TIPS = [
    "Save from Excel as 'CSV UTF-8 (Comma delimited)'. The first row must be the column names exactly as listed.",
    "Dates must be YYYY-MM-DD. In Excel, format the date column as Custom 'yyyy-mm-dd' before saving.",
    "Numbers must be plain: no currency symbols, no thousands separators, a dot for decimals.",
    "Upload in this order, because later files refer to ids in earlier ones: " + ", ".join(UPLOAD_ORDER) + ".",
    "Re-uploading ingredients, menu or recipes updates them (cost and recipe history is kept). "
    "Re-uploading sales, purchases or counts adds the rows again, so only upload new dates.",
]


def columns(file_type: str) -> list[dict]:
    required = ingest.REQUIRED_COLUMNS[file_type]
    optional = ingest.OPTIONAL_COLUMNS.get(file_type, [])
    return [
        {"name": c, "required": c in required, "meaning": MEANING.get(c, "")}
        for c in required + [o for o in optional if o not in required]
    ]


def guide() -> dict:
    """Everything the assistant needs to explain or show any upload file's layout."""
    return {
        "upload_order": UPLOAD_ORDER,
        "tips": TIPS,
        "files": [
            {
                "file_type": t,
                "card": LABELS[t],
                "purpose": PURPOSE[t],
                "columns": columns(t),
                "example_rows": EXAMPLES[t],
            }
            for t in UPLOAD_ORDER
        ],
    }
