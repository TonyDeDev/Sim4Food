"""Estimates how long current stock will last, per ingredient.

days_remaining = qty_on_hand / average historical daily consumption

This is a historical-average estimate, not the agent-based simulation's
forecast - it only needs data already on hand (inventory_current, sales,
recipes) and has no dependency on the simulation engine, so it can ship
before forecast.py exists. Once that lands, it can replace avg_daily_consumption
with a simulated per-day demand figure without changing this module's shape.
"""
from collections import defaultdict
from datetime import date

from app.db import get_pool

CRITICAL_DAYS = 1
WATCH_DAYS = 3


def _status(days_remaining: float | None) -> str:
    if days_remaining is None:
        return "unknown"
    if days_remaining < CRITICAL_DAYS:
        return "critical"
    if days_remaining < WATCH_DAYS:
        return "watch"
    return "ok"


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

        days_remaining = None
        if qty_on_hand is not None and avg_daily > 0:
            days_remaining = qty_on_hand / avg_daily

        rows.append({
            "ingredient_id": row["external_id"],
            "name": row["name"],
            "unit": row["unit"],
            "qty_on_hand": qty_on_hand,
            "avg_daily_consumption": round(avg_daily, 3) if avg_daily else 0.0,
            "days_remaining": round(days_remaining, 1) if days_remaining is not None else None,
            "status": _status(days_remaining),
        })

    rows.sort(key=lambda r: (r["days_remaining"] is None, r["days_remaining"]))

    summary = {"tracked": 0, "critical": 0, "watch": 0, "ok": 0}
    for row in rows:
        if row["qty_on_hand"] is not None:
            summary["tracked"] += 1
        if row["status"] in summary:
            summary[row["status"]] += 1

    return {"ingredients": rows, "summary": summary}


async def compute_inventory(restaurant_id: str) -> dict:
    pool = get_pool()
    async with pool.acquire() as conn:
        restaurant_uuid = await conn.fetchval("SELECT id FROM restaurants WHERE name = $1", restaurant_id)
        if restaurant_uuid is None:
            return {"ingredients": [], "summary": {"tracked": 0, "critical": 0, "watch": 0, "ok": 0}}

        ingredients = await conn.fetch(
            "SELECT id, external_id, name, unit FROM ingredients WHERE restaurant_id = $1 ORDER BY external_id",
            restaurant_uuid,
        )
        stock = await conn.fetch(
            "SELECT ingredient_id, qty_on_hand FROM inventory_current WHERE restaurant_id = $1",
            restaurant_uuid,
        )
        consumption = await conn.fetch(
            """
            SELECT r.ingredient_id, s.date, s.qty_sold * r.qty_per_serving AS qty
            FROM sales s
            JOIN recipes r ON r.menu_item_id = s.menu_item_id
            WHERE s.restaurant_id = $1
            ORDER BY s.date, r.ingredient_id
            """,
            restaurant_uuid,
        )

    return build_inventory_report(
        [dict(r) for r in ingredients],
        [dict(r) for r in stock],
        [dict(r) for r in consumption],
    )
