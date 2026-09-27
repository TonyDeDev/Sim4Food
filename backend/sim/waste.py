"""Computes historical waste and dollar loss per ingredient, by week.

waste = start stock + purchases - end stock - (dishes sold x recipe qty)

Weeks run Monday to Sunday. Each week's start/end stock is taken from the
latest inventory_counts row at or before that boundary date; if no count
exists yet for an ingredient on one side, we assume no net change in stock
over the week (start == end), so waste there falls back to
purchases - consumption for that week alone.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from app.db import get_pool
from sim import history
from sim.consumption import load_consumption


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


def _week_start_ts(week: date) -> datetime:
    return datetime(week.year, week.month, week.day, tzinfo=timezone.utc)


def build_waste_report(
    ingredients: list[dict],
    purchases: list[dict],
    counts: list[dict],
    consumption: list[dict],
    cost_changes: list[dict] | None = None,
) -> dict:
    """Pure aggregation over already-fetched rows (DB-agnostic, testable).

    ingredients: [{id, external_id, name, unit_cost}]
    purchases: [{ingredient_id, date, qty}]
    counts: [{ingredient_id, date, qty_on_hand}]
    consumption: [{ingredient_id, date, qty}]  (qty_sold * qty_per_serving, pre-joined)
    cost_changes: [{ingredient_id, old_value, new_value, effective_at}] for unit_cost,
        so each week is priced at the cost in force at the start of that week
        instead of today's cost. Without it every week uses ingredients.unit_cost.
    """
    names = {row["id"]: row["name"] for row in ingredients}
    external_ids = {row["id"]: row["external_id"] for row in ingredients}
    unit_costs = {row["id"]: float(row["unit_cost"]) for row in ingredients}

    cost_log: dict[str, list[tuple[datetime, float, float]]] = defaultdict(list)
    for row in cost_changes or []:
        cost_log[row["ingredient_id"]].append(
            (row["effective_at"], float(row["old_value"]), float(row["new_value"]))
        )
    for entries in cost_log.values():
        entries.sort(key=lambda entry: entry[0])

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
                "waste_cost": round(
                    waste_qty
                    * history.value_at(unit_costs[ingredient_id], cost_log.get(ingredient_id, []), _week_start_ts(week)),
                    2,
                ),
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
        # Every fetch is explicitly ordered. Weekly totals are accumulated as
        # floats, and float addition is not associative, so an unordered fetch
        # let physical row order shift a total by a cent between runs.
        ingredients = await conn.fetch(
            "SELECT id, external_id, name, unit_cost FROM ingredients WHERE restaurant_id = $1 AND current_id IS NULL ORDER BY external_id",
            restaurant_id,
        )
        purchases = await conn.fetch(
            "SELECT ingredient_id, date, qty FROM purchases WHERE restaurant_id = $1 ORDER BY date, ingredient_id",
            restaurant_id,
        )
        counts = await conn.fetch(
            "SELECT ingredient_id, date, qty_on_hand FROM inventory_counts WHERE restaurant_id = $1 ORDER BY date, ingredient_id",
            restaurant_id,
        )
        cost_versions = await conn.fetch(
            "SELECT COALESCE(current_id, id) AS ingredient_id, unit_cost, valid_from "
            "FROM ingredients WHERE restaurant_id = $1 ORDER BY valid_from, id",
            restaurant_id,
        )
        consumption = await load_consumption(conn, restaurant_id, [dict(r) for r in ingredients])

    return build_waste_report(
        [dict(r) for r in ingredients],
        [dict(r) for r in purchases],
        [dict(r) for r in counts],
        consumption,
        history.cost_changes([dict(r) for r in cost_versions]),
    )

