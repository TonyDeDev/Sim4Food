"""Current stock and historical usage per ingredient.

Deliberately stops short of estimating how long stock will last. Average
daily usage is honest historical arithmetic (same kind of computation
waste.py already does), but the forward projection - "will this run out,
and when" - depends on the agent-based simulation, not on anything this
module can derive by itself. It surfaces only what's directly knowable:
current quantity on hand, and average historical daily usage.
"""
from collections import defaultdict
from datetime import date

from app.db import get_pool


def build_inventory_report(
    ingredients: list[dict],
    stock: list[dict],
    consumption: list[dict],
) -> dict:
    """Pure aggregation over already-fetched rows (DB-agnostic, testable).

    ingredients: [{id, external_id, name, unit}]
    stock: [{ingredient_id, qty_on_hand}]  (from inventory_current)
    consumption: [{ingredient_id, date, qty}]  (qty_sold * qty_per_serving, pre-joined)
    """
    stock_by_ingredient = {row["ingredient_id"]: float(row["qty_on_hand"]) for row in stock}

    consumed_by_ingredient: dict[str, float] = defaultdict(float)
    all_dates: list[date] = []
    for row in consumption:
        consumed_by_ingredient[row["ingredient_id"]] += float(row["qty"])
        all_dates.append(row["date"])

    # One shared history window for every ingredient, not a per-ingredient
    # span, so an ingredient with no recent sales still divides by the
    # restaurant's real observation period instead of looking artificially busy.
    num_days = (max(all_dates) - min(all_dates)).days + 1 if all_dates else 0

    rows = []
    for row in ingredients:
        ingredient_id = row["id"]
        qty_on_hand = stock_by_ingredient.get(ingredient_id)
        total_consumed = consumed_by_ingredient.get(ingredient_id, 0.0)
        avg_daily = total_consumed / num_days if num_days > 0 else 0.0

        rows.append({
            "ingredient_id": row["external_id"],
            "name": row["name"],
            "unit": row["unit"],
            "qty_on_hand": qty_on_hand,
            "avg_daily_consumption": round(avg_daily, 3) if avg_daily else 0.0,
        })

    tracked = sum(1 for r in rows if r["qty_on_hand"] is not None)
    return {
        "ingredients": rows,
        "summary": {"total": len(rows), "tracked": tracked, "missing_count": len(rows) - tracked},
    }


async def compute_inventory(restaurant_id: str) -> dict:
    pool = get_pool()
    async with pool.acquire() as conn:
        ingredients = await conn.fetch(
            "SELECT id, external_id, name, unit FROM ingredients WHERE restaurant_id = $1 ORDER BY external_id",
            restaurant_id,
        )
        stock = await conn.fetch(
            "SELECT ingredient_id, qty_on_hand FROM inventory_current WHERE restaurant_id = $1",
            restaurant_id,
        )
        consumption = await conn.fetch(
            """
            SELECT r.ingredient_id, s.date, s.qty_sold * r.qty_per_serving AS qty
            FROM sales s
            JOIN recipes r ON r.menu_item_id = s.menu_item_id
            WHERE s.restaurant_id = $1
            ORDER BY s.date, r.ingredient_id
            """,
            restaurant_id,
        )

    return build_inventory_report(
        [dict(r) for r in ingredients],
        [dict(r) for r in stock],
        [dict(r) for r in consumption],
    )
