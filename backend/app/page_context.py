"""What the assistant may see on each dashboard tab.

The browser only says which tab the owner is on; every number is loaded here,
on the server, for the restaurant the session owns. Nothing the browser sends
ends up in the context, and uploaded strings go through guardrails.safe_text.
Internal ids and account details (emails, UUIDs) are never included.
"""
from __future__ import annotations

from typing import Literal

from app import db
from app.guardrails import safe_text
from app.record_formats import guide
from sim import forecast_store, home_summary, inventory

Page = Literal["home", "records", "forecast", "whatif"]
PAGE_LABELS = {"home": "Home", "records": "Records", "forecast": "Forecast", "whatif": "What If"}
TOP_INGREDIENTS = 40


def _round(value, digits=2):
    return None if value is None else round(float(value), digits)


def forecast_context(run: dict) -> dict:
    """Compact view of a stored forecast run: only numbers the Forecast tab shows."""
    forecast = run["forecast"]
    data = forecast.get("data") or {}
    accuracy = forecast.get("accuracy") or {}
    methods = accuracy.get("methods") or {}
    coverage = accuracy.get("band_coverage") or {}
    savings = forecast.get("savings") or {}
    ingredients = []
    for item in (forecast.get("ingredients") or [])[:TOP_INGREDIENTS]:
        f, r = item.get("forecast") or {}, item.get("recommendation") or {}
        history = [h["usage"] for h in item.get("history") or [] if h.get("usage") is not None]
        ingredients.append({
            "name": safe_text(item["name"]),
            "unit": safe_text(item.get("unit"), 12),
            "last_week_usage": _round(history[-1]) if history else None,
            "forecast": {k: _round(f.get(k)) for k in ("p10", "p50", "p90")},
            "event_adjustment_pct": f.get("event_adjustment_pct"),
            "order": {
                "total": r.get("order_qty"),
                "deliveries": [{"day": d["day"], "qty": d["qty"]} for d in r.get("deliveries") or []],
                "packs": r.get("packs"),
                "pack_size": r.get("pack_size"),
            },
            "on_hand_at_start": r.get("on_hand"),
            "perishable": r.get("perishable"),
            "stockout_risk": r.get("stockout_risk"),
            "expected_leftover_cost": r.get("expected_waste_cost"),
            "habit_order": r.get("habit_order_qty"),
            "habit_stockout_risk": r.get("habit_stockout_risk"),
        })
    backtest = savings.get("order_backtest") or {}
    return {
        "forecast_run_at": run.get("run_at"),
        "target_week_start": data.get("target_week"),
        "based_on_sales_through": data.get("based_on_sales_through"),
        "weeks_of_history": data.get("weeks_of_history"),
        "data_status": data.get("message"),
        "method": data.get("method_reason"),
        "accuracy": {
            "wape_ours": (methods.get("xgboost") or {}).get("wape"),
            "wape_same_weekday_average": (methods.get("dish_baseline") or {}).get("wape"),
            "wape_same_as_last_week": (methods.get("naive_last_week") or {}).get("wape"),
            "range_hit_rate": coverage.get("inside_p10_p90"),
            "range_hit_target": coverage.get("target_inside"),
            "backtest_weeks": accuracy.get("backtest_weeks"),
        } if accuracy else None,
        "delivery_days": savings.get("delivery_days"),
        "savings": {
            "expected_weekly_vs_habit": savings.get("weekly_expected_vs_habit"),
            "order_backtest": {
                "weeks": backtest.get("weeks"),
                "our_leftover_cost": (backtest.get("ours") or {}).get("waste_cost"),
                "actual_leftover_cost": (backtest.get("actual") or {}).get("waste_cost"),
                "our_lost_profit": (backtest.get("ours") or {}).get("lost_margin"),
                "actual_lost_profit": (backtest.get("actual") or {}).get("lost_margin"),
                "leftover_reduction_pct": backtest.get("waste_reduction_pct"),
                "net_savings": backtest.get("total_savings"),
            } if backtest else None,
        } if savings else None,
        "events": [
            {**e, "name": safe_text(e.get("name"))} for e in forecast.get("events") or []
        ],
        "ingredients": ingredients,
    }


def home_context(summary: dict, inventory_report: dict) -> dict:
    rows = []
    for r in inventory_report.get("ingredients") or []:
        qty, daily = r.get("qty_on_hand"), r.get("avg_daily_consumption")
        runway = None if qty is None or not daily else round(qty / daily, 1)
        status = "no count" if qty is None else "out" if qty <= 0 else "low" if runway is not None and runway < 3 else "ok"
        rows.append({
            "name": safe_text(r["name"]), "unit": safe_text(r.get("unit"), 12),
            "on_hand": _round(qty, 3), "avg_used_per_day": _round(daily, 3),
            "runway_days": runway, "status": status,
        })
    revenue, waste, stock = summary.get("revenue") or {}, summary.get("waste") or {}, summary.get("stock") or {}
    event = summary.get("next_event")
    return {
        "revenue_last_7_days": {
            "total": revenue.get("last7"), "previous_7_days": revenue.get("prev7"),
            "change_pct": revenue.get("change_pct"), "through": revenue.get("as_of"), "daily": revenue.get("daily"),
        },
        "waste_cost_last_week": {
            "definition": "Measured from stock counts: start count + purchases - end count - theoretical usage, priced at cost.",
            "week_start": waste.get("week_start"), "cost": waste.get("last_week_cost"),
            "previous_week": waste.get("prev_week_cost"), "change_pct": waste.get("change_pct"),
            "biggest_ingredient": safe_text(waste.get("top_ingredient")), "last_8_weeks": waste.get("weekly"),
        },
        "stock_health": {
            "out": stock.get("out_count"), "low": stock.get("low_count"), "stock_value": stock.get("stock_value"),
            "most_urgent": safe_text(stock.get("most_urgent")), "most_urgent_days_left": stock.get("most_urgent_days"),
            "low_means": "less than 3 days of stock at the average daily usage",
        },
        "next_event": {**event, "name": safe_text(event.get("name"))} if event else None,
        "last_upload_at": summary.get("last_upload_at"),
        "inventory": rows,
    }


async def _records(restaurant_id: str) -> dict:
    pool = db.get_pool()
    async with pool.acquire() as conn:
        uploads = await conn.fetch(
            """
            SELECT DISTINCT ON (file_type) file_type::text AS file_type, file_name, status::text AS status,
                   row_count, uploaded_at, error_message
            FROM upload_batches WHERE restaurant_id = $1
            ORDER BY file_type, uploaded_at DESC
            """,
            restaurant_id,
        )
        counts = await conn.fetchrow(
            """
            SELECT
              (SELECT count(*) FROM ingredients WHERE restaurant_id = $1 AND current_id IS NULL) AS ingredients,
              (SELECT count(*) FROM menu_items WHERE restaurant_id = $1) AS menu_items,
              (SELECT count(*) FROM recipes r JOIN menu_items m ON m.id = r.menu_item_id
                 WHERE m.restaurant_id = $1 AND r.valid_to IS NULL) AS recipe_lines,
              (SELECT count(*) FROM sales WHERE restaurant_id = $1) AS sales_rows,
              (SELECT min(date) FROM sales WHERE restaurant_id = $1) AS sales_from,
              (SELECT max(date) FROM sales WHERE restaurant_id = $1) AS sales_to,
              (SELECT count(*) FROM purchases WHERE restaurant_id = $1) AS purchase_rows,
              (SELECT max(date) FROM purchases WHERE restaurant_id = $1) AS purchases_to,
              (SELECT count(*) FROM inventory_counts WHERE restaurant_id = $1) AS count_rows,
              (SELECT max(date) FROM inventory_counts WHERE restaurant_id = $1) AS last_count,
              (SELECT count(*) FROM events WHERE restaurant_id = $1) AS events
            """,
            restaurant_id,
        )
    return records_context([dict(u) for u in uploads], dict(counts) if counts else {})


def records_context(uploads: list[dict], counts: dict) -> dict:
    def iso(v):
        return v.isoformat() if hasattr(v, "isoformat") else v

    return {
        "latest_upload_per_file": [
            {
                "file_type": u["file_type"], "file_name": safe_text(u.get("file_name")), "status": u.get("status"),
                "rows": u.get("row_count"), "uploaded_at": iso(u.get("uploaded_at")),
                "errors": safe_text(u.get("error_message"), 300),
            }
            for u in uploads
        ],
        "stored_data": {k: iso(v) for k, v in counts.items()},
        "file_formats": guide(),
    }


async def _whatif(restaurant_id: str) -> dict:
    pool = db.get_pool()
    async with pool.acquire() as conn:
        events = await conn.fetch(
            "SELECT type::text AS type, name, start_date, end_date, discount_pct::float8 AS discount_pct, "
            "expected_lift::float8 AS expected_lift FROM events WHERE restaurant_id = $1 AND end_date >= CURRENT_DATE "
            "ORDER BY start_date LIMIT 10",
            restaurant_id,
        )
    return {
        "feature_status": "The What If simulation (deal slider and holiday toggle) is still being built and cannot "
        "run yet. The upcoming_events below are already uploaded, so the Forecast tab applies their lift when "
        "their dates fall in the forecast week (re-run the forecast after any change). A new or changed deal "
        "or holiday is added by uploading the full events list again under Records (Deals and holidays).",
        "upcoming_events": [
            {
                "type": e["type"], "name": safe_text(e["name"]), "start_date": e["start_date"].isoformat(),
                "end_date": e["end_date"].isoformat(), "discount_pct": e["discount_pct"], "expected_lift": e["expected_lift"],
            }
            for e in events
        ],
    }


async def build(page: Page, restaurant_id: str) -> dict:
    """The data for one tab of one restaurant (ownership is checked by the caller)."""
    if page == "forecast":
        run = await forecast_store.get_latest_run(db.get_pool(), restaurant_id)
        if run is None or not (run.get("forecast") or {}).get("ingredients"):
            return {"forecast": None, "note": "No forecast has been run yet: press 'Run forecast' on the Forecast tab."}
        return forecast_context(run)
    if page == "home":
        summary = await home_summary.compute_home_summary(restaurant_id)
        return home_context(summary, await inventory.compute_inventory(restaurant_id))
    if page == "records":
        return await _records(restaurant_id)
    return await _whatif(restaurant_id)
