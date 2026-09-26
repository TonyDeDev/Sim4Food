"""Computes historical waste and dollar loss per ingredient, by week.

waste = start stock + purchases - end stock - (dishes sold x recipe qty)

Weeks run Monday to Sunday. Each week's start/end stock is taken from the
latest inventory_counts row at or before that boundary date; if no count
exists yet for an ingredient on one side, we assume no net change in stock
over the week (start == end), so waste there falls back to
purchases - consumption for that week alone.
"""
from collections import defaultdict
from datetime import date, timedelta

from app.db import get_pool


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _stock_at_or_before(counts: list[tuple[date, float]], d: date) -> float | None:
    result = None
    for count_date, qty in counts:
        if count_date <= d:
            result = qty
        else:
            break
    return result


def build_waste_report(
    ingredients: list[dict],
    purchases: list[dict],
    counts: list[dict],
    consumption: list[dict],
) -> dict:
    """Pure aggregation over already-fetched rows (DB-agnostic, testable).

    ingredients: [{id, external_id, name, unit_cost}]
    purchases: [{ingredient_id, date, qty}]
    counts: [{ingredient_id, date, qty_on_hand}]
    consumption: [{ingredient_id, date, qty}]  (qty_sold * qty_per_serving, pre-joined)
    """
    names = {row["id"]: row["name"] for row in ingredients}
    external_ids = {row["id"]: row["external_id"] for row in ingredients}
    unit_costs = {row["id"]: float(row["unit_cost"]) for row in ingredients}

    counts_by_ingredient: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for row in counts:
        counts_by_ingredient[row["ingredient_id"]].append((row["date"], float(row["qty_on_hand"])))
    for entries in counts_by_ingredient.values():
        entries.sort(key=lambda pair: pair[0])

    purchases_by_week: dict[tuple[str, date], float] = defaultdict(float)
    for row in purchases:
        week = _week_start(row["date"])
        purchases_by_week[(row["ingredient_id"], week)] += float(row["qty"])

    consumption_by_week: dict[tuple[str, date], float] = defaultdict(float)
    for row in consumption:
        week = _week_start(row["date"])
        consumption_by_week[(row["ingredient_id"], week)] += float(row["qty"])

    weeks = sorted({week for _, week in purchases_by_week} | {week for _, week in consumption_by_week})

    by_ingredient = []
    for ingredient_id, name in names.items():
        counts_for_ingredient = counts_by_ingredient.get(ingredient_id, [])
        weekly = []
        for week in weeks:
            week_end = week + timedelta(days=6)
            purchased = purchases_by_week.get((ingredient_id, week), 0.0)
            consumed = consumption_by_week.get((ingredient_id, week), 0.0)

            start_stock = _stock_at_or_before(counts_for_ingredient, week - timedelta(days=1))
            end_stock = _stock_at_or_before(counts_for_ingredient, week_end)

            if start_stock is None:
                start_stock = end_stock if end_stock is not None else 0.0
            if end_stock is None:
                end_stock = start_stock

            waste_qty = max(0.0, start_stock + purchased - end_stock - consumed)
            weekly.append({
                "week_start": week.isoformat(),
                "waste_qty": round(waste_qty, 3),
                "waste_cost": round(waste_qty * unit_costs[ingredient_id], 2),
            })

        by_ingredient.append({
            "ingredient_id": external_ids[ingredient_id],
            "name": name,
            "weeks": weekly,
            "total_waste_qty": round(sum(w["waste_qty"] for w in weekly), 3),
            "total_waste_cost": round(sum(w["waste_cost"] for w in weekly), 2),
        })

    return {"by_ingredient": by_ingredient}


async def compute_waste(restaurant_id: str) -> dict:
    pool = get_pool()
    async with pool.acquire() as conn:
        restaurant_uuid = await conn.fetchval("SELECT id FROM restaurants WHERE name = $1", restaurant_id)
        if restaurant_uuid is None:
            return {"by_ingredient": []}

        ingredients = await conn.fetch(
            "SELECT id, external_id, name, unit_cost FROM ingredients WHERE restaurant_id = $1",
            restaurant_uuid,
        )
        purchases = await conn.fetch(
            "SELECT ingredient_id, date, qty FROM purchases WHERE restaurant_id = $1",
            restaurant_uuid,
        )
        counts = await conn.fetch(
            "SELECT ingredient_id, date, qty_on_hand FROM inventory_counts WHERE restaurant_id = $1",
            restaurant_uuid,
        )
        consumption = await conn.fetch(
            """
            SELECT r.ingredient_id, s.date, s.qty_sold * r.qty_per_serving AS qty
            FROM sales s
            JOIN recipes r ON r.menu_item_id = s.menu_item_id
            WHERE s.restaurant_id = $1
            """,
            restaurant_uuid,
        )

    return build_waste_report(
        [dict(r) for r in ingredients],
        [dict(r) for r in purchases],
        [dict(r) for r in counts],
        [dict(r) for r in consumption],
    )
