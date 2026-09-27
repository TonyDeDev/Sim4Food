"""Owner-facing headline numbers for the Home tab.

Everything here is derived from data already stored (sales, waste report,
inventory report, events, uploads) - no new tables and no model. The "last 7
days" window is anchored to the latest sales date rather than today, so a
restaurant whose data ends a while ago still sees real numbers.
"""
from datetime import date, timedelta

from app.db import get_pool
from sim import inventory, waste

LOW_RUNWAY_DAYS = 3


def _pct_change(current: float, previous: float) -> float | None:
    if previous <= 0:
        return None
    return round((current - previous) / previous * 100, 1)


def build_revenue(sales: list[dict]) -> dict:
    """sales: [{date, qty_sold, avg_price}]"""
    by_day: dict[date, float] = {}
    for row in sales:
        by_day[row["date"]] = by_day.get(row["date"], 0.0) + float(row["qty_sold"]) * float(row["avg_price"])

    if not by_day:
        return {"last7": 0.0, "prev7": 0.0, "change_pct": None, "daily": [], "as_of": None}

    latest = max(by_day)
    window_start = latest - timedelta(days=6)
    prev_start = window_start - timedelta(days=7)
    daily = [
        {"date": (window_start + timedelta(days=i)).isoformat(),
         "revenue": round(by_day.get(window_start + timedelta(days=i), 0.0), 2)}
        for i in range(7)
    ]
    last7 = sum(v for d, v in by_day.items() if window_start <= d <= latest)
    prev7 = sum(v for d, v in by_day.items() if prev_start <= d < window_start)
    return {
        "last7": round(last7, 2),
        "prev7": round(prev7, 2),
        "change_pct": _pct_change(last7, prev7),
        "daily": daily,
        "as_of": latest.isoformat(),
    }


def build_waste(waste_report: dict) -> dict:
    """Latest full week's waste cost vs the week before, from build_waste_report output."""
    week_totals: dict[str, float] = {}
    week_by_ingredient: dict[str, dict[str, float]] = {}
    for ingredient in waste_report["by_ingredient"]:
        for week in ingredient["weeks"]:
            week_totals[week["week_start"]] = week_totals.get(week["week_start"], 0.0) + week["waste_cost"]
            week_by_ingredient.setdefault(week["week_start"], {})[ingredient["name"]] = week["waste_cost"]

    weeks = sorted(week_totals)
    if not weeks:
        return {"last_week_cost": 0.0, "prev_week_cost": 0.0, "change_pct": None,
                "top_ingredient": None, "week_start": None, "weekly": []}

    last = weeks[-1]
    last_cost = week_totals[last]
    prev_cost = week_totals[weeks[-2]] if len(weeks) > 1 else 0.0
    top = max(week_by_ingredient[last].items(), key=lambda kv: kv[1])
    return {
        "last_week_cost": round(last_cost, 2),
        "prev_week_cost": round(prev_cost, 2),
        "change_pct": _pct_change(last_cost, prev_cost),
        "top_ingredient": top[0] if top[1] > 0 else None,
        "week_start": last,
        "weekly": [{"week_start": w, "cost": round(week_totals[w], 2)} for w in weeks[-8:]],
    }


def runway_days(row: dict) -> float | None:
    """Days of stock left at historical usage; None when it can't be known."""
    if row["qty_on_hand"] is None or not row["avg_daily_consumption"]:
        return None
    return row["qty_on_hand"] / row["avg_daily_consumption"]


def build_stock(inventory_report: dict, unit_costs: dict[str, float]) -> dict:
    """unit_costs is keyed by the ingredient's external_id, as in the inventory report."""
    low = out = 0
    stock_value = 0.0
    urgent: tuple[float, str] | None = None
    for row in inventory_report["ingredients"]:
        qty = row["qty_on_hand"]
        if qty is None:
            continue
        stock_value += qty * unit_costs.get(row["ingredient_id"], 0.0)
        days = runway_days(row)
        if qty <= 0:
            out += 1
            days = 0.0
        elif days is not None and days < LOW_RUNWAY_DAYS:
            low += 1
        if days is not None and days < LOW_RUNWAY_DAYS and (urgent is None or days < urgent[0]):
            urgent = (days, row["name"])
    return {
        "low_count": low,
        "out_count": out,
        "stock_value": round(stock_value, 2),
        "most_urgent": urgent[1] if urgent else None,
        "most_urgent_days": round(urgent[0], 1) if urgent else None,
        "tracked": inventory_report["summary"]["tracked"],
        "total": inventory_report["summary"]["total"],
    }


def build_next_event(events: list[dict], today: date) -> dict | None:
    """events: [{type, name, start_date, end_date, discount_pct, expected_lift}]"""
    upcoming = sorted(
        (e for e in events if e["end_date"] >= today), key=lambda e: e["start_date"]
    )
    if not upcoming:
        return None
    e = upcoming[0]
    return {
        "type": e["type"],
        "name": e["name"],
        "start_date": e["start_date"].isoformat(),
        "end_date": e["end_date"].isoformat(),
        "days_until": max(0, (e["start_date"] - today).days),
        "discount_pct": float(e["discount_pct"]) if e["discount_pct"] is not None else None,
        "expected_lift": float(e["expected_lift"]) if e["expected_lift"] is not None else None,
    }


async def compute_home_summary(restaurant_id: str) -> dict:
    pool = get_pool()
    async with pool.acquire() as conn:
        sales = await conn.fetch(
            "SELECT date, qty_sold, avg_price FROM sales WHERE restaurant_id = $1 ORDER BY date",
            restaurant_id,
        )
        costs = await conn.fetch(
            "SELECT external_id, unit_cost FROM ingredients WHERE restaurant_id = $1 AND current_id IS NULL",
            restaurant_id,
        )
        events = await conn.fetch(
            "SELECT type, name, start_date, end_date, discount_pct, expected_lift "
            "FROM events WHERE restaurant_id = $1 AND end_date >= CURRENT_DATE ORDER BY start_date LIMIT 5",
            restaurant_id,
        )
        last_upload = await conn.fetchval(
            "SELECT max(uploaded_at) FROM upload_batches WHERE restaurant_id = $1 AND status = 'processed'",
            restaurant_id,
        )

    waste_report = await waste.compute_waste(restaurant_id)
    inventory_report = await inventory.compute_inventory(restaurant_id)

    return {
        "revenue": build_revenue([dict(r) for r in sales]),
        "waste": build_waste(waste_report),
        "stock": build_stock(inventory_report, {r["external_id"]: float(r["unit_cost"]) for r in costs}),
        "next_event": build_next_event([dict(r) for r in events], date.today()),
        "last_upload_at": last_upload.isoformat() if last_upload else None,
    }
