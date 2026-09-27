"""JSON-ready forecast payload for the frontend (charts, orders and data-quality status).

Everything the forecast page needs in one response: per-ingredient history,
the target week's forecast with P10/P50/P90 bands, the backtest (predicted vs
actual), an order recommendation per ingredient, the savings against the
owner's habit and against what they actually bought, and a summary of how much
data there is and how trustworthy the numbers have been.

Pipeline: complete weeks only -> dish matrix -> rolling backtest (champion
check) -> model fit -> recursive forecast up to the target week with explicit
event lift -> Monte Carlo usage samples -> newsvendor orders.
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

from sim import recommend, uncertainty
from sim.dish_features import CENSORED, QTY, build_dish_matrix
from sim.events_adjust import estimate_lifts
from sim.forecast_backtest import compare_band_methods, rolling_backtest_dish, summarize, to_ingredient_weeks
from sim.history import recipe_versions_of
from sim.train_dish_xgb import fit, forecast_weeks, to_ingredient_usage, usable_rows

LEARNING_WEEKS = 8
ESTABLISHED_WEEKS = 26
TARGET_COVERAGE = uncertainty.TARGET_COVERAGE
MAX_HORIZON_WEEKS = 6
WEEK = pd.Timedelta(days=7)


def data_status(weeks_of_history: int) -> dict:
    """Label for how much history the forecast is based on. A warning only, it never changes the forecast."""
    if weeks_of_history < LEARNING_WEEKS:
        return {
            "status": "learning",
            "message": f"Based on {weeks_of_history} weeks of data. Treat these as rough estimates. "
            "Upload older sales to improve them.",
        }
    if weeks_of_history < ESTABLISHED_WEEKS:
        return {
            "status": "improving",
            "message": f"Based on {weeks_of_history} weeks of data. Estimates are getting sharper. "
            "Upload older sales to unlock seasonal and holiday patterns.",
        }
    return {"status": "established", "message": f"Based on {weeks_of_history} weeks of data."}


def _num(value, digits: int = 3):
    if value is None or (isinstance(value, float) and math.isnan(value)) or pd.isna(value):
        return None
    return round(float(value), digits)


def _week(ts) -> str:
    return pd.Timestamp(ts).date().isoformat()


def _monday(ts) -> pd.Timestamp:
    ts = pd.Timestamp(ts).normalize()
    return ts - pd.Timedelta(days=ts.weekday())


def _complete_weeks_only(sales: pd.DataFrame) -> pd.DataFrame:
    """Drop the in-progress week, so a partial week is never read as a slow one."""
    dates = pd.to_datetime(sales["date"]).dt.normalize()
    max_date = dates.max()
    monday = max_date - pd.Timedelta(days=max_date.weekday())
    last_complete_end = max_date if max_date.weekday() == 6 else monday - pd.Timedelta(days=1)
    return sales[dates <= last_complete_end]


def _empty(message: str) -> dict:
    return {
        "data": {"weeks_of_history": 0, **data_status(0), "message": message},
        "accuracy": None,
        "events": [],
        "savings": None,
        "ingredients": [],
    }


def _frame(frames: dict, key: str, columns: list[str]) -> pd.DataFrame:
    df = frames.get(key)
    return df if df is not None else pd.DataFrame(columns=columns)


def _target(last_week: pd.Timestamp, today: date, target_week) -> tuple[pd.Timestamp, int, bool]:
    """(target Monday, weeks forecast after the last sales week, stale data)."""
    next_week = last_week + WEEK
    wanted = _monday(target_week) if target_week is not None else _monday(pd.Timestamp(today)) + WEEK
    wanted = max(wanted, next_week)
    ahead = int((wanted - next_week) / WEEK) + 1
    if ahead > MAX_HORIZON_WEEKS:
        return next_week, 1, True
    return wanted, ahead, False


def _usage_rows(dish_rows: pd.DataFrame, col: str, recipes: pd.DataFrame) -> pd.DataFrame:
    """date, ingredient_id, qty from dish-day rows."""
    joined = pd.merge(dish_rows[["date", "menu_item_id", col]], recipes, on="menu_item_id")
    if "valid_from" in joined.columns:
        joined = joined[(joined["valid_from"] <= joined["date"]) & (joined["date"] < joined["valid_to"])]
    joined["qty"] = joined[col] * joined["qty_per_serving"]
    return joined.groupby(["date", "ingredient_id"], as_index=False)["qty"].sum()


def _event_summary(target: pd.DataFrame, events: pd.DataFrame | None) -> list[dict]:
    """Events overlapping the target week, with the lift applied and where it came from."""
    if events is None or events.empty:
        return []
    start, end = target["date"].min(), target["date"].max()
    out = []
    for ev in events.itertuples(index=False):
        s, e = pd.Timestamp(ev.start_date), pd.Timestamp(ev.end_date)
        if e < start or s > end:
            continue
        days = target[(target["date"] >= s) & (target["date"] <= e) & target["event_day"]]
        sources = sorted(set(days["event_source"]) - {""})
        lifted = days[days["event_multiplier"] != 1.0]
        out.append({
            "name": getattr(ev, "name", None) or ev.type,
            "type": ev.type,
            "start_date": _week(s),
            "end_date": _week(e),
            "discount_pct": _num(ev.discount_pct),
            "lift_pct": _num((lifted["event_multiplier"].mean() - 1) * 100, 1) if not lifted.empty else None,
            "lift_source": sources[0] if sources else "none",
        })
    return out


def _order_backtest_weeks(dish_bt: pd.DataFrame, recipes: pd.DataFrame, frames: dict, days: list[int]) -> list[dict]:
    """Inputs for recommend.order_backtest: one entry per backtest week with enough earlier residuals."""
    counts = _frame(frames, "counts", ["date", "ingredient_id", "qty_on_hand"])
    purchases = _frame(frames, "purchases", ["date", "ingredient_id", "qty"])
    if counts.empty:
        return []
    counts = counts.assign(date=pd.to_datetime(counts["date"]).dt.normalize()).sort_values("date", kind="stable")
    purchases = purchases.assign(date=pd.to_datetime(purchases["date"]).dt.normalize(), qty=purchases["qty"].astype(float))
    out = []
    for week in sorted(dish_bt["forecast_week"].unique()):
        prior = dish_bt[dish_bt["forecast_week"] < week]
        if prior["forecast_week"].nunique() < uncertainty.MIN_PRIOR_WEEKS:
            continue
        rows = dish_bt[dish_bt["forecast_week"] == week]
        totals = rows.groupby("menu_item_id")["xgboost"].sum()
        samples, _ = uncertainty.forecast_samples(prior, recipes, totals)
        # Estimated demand: sales, with stockout days filled by the forecast.
        rows = rows.assign(demand=rows[QTY].where(~rows[CENSORED], rows["xgboost"]))
        demand = recommend.cycle_usage(_usage_rows(rows, "demand", recipes), days)
        forecast = recommend.cycle_usage(_usage_rows(rows, "xgboost", recipes), days)
        on_hand = counts[counts["date"] < week].groupby("ingredient_id")["qty_on_hand"].last().astype(float)
        in_week = purchases[(purchases["date"] >= week) & (purchases["date"] < week + WEEK)]
        purchased = recommend.cycle_usage(in_week, days)
        out.append({
            "week": week, "on_hand": on_hand, "purchased": purchased, "demand": demand,
            "samples": samples, "shares": forecast.div(forecast.sum(axis=1), axis=0).fillna(0.0),
        })
    return out


def build_forecast_payload(frames: dict, today: date | None = None, target_week=None) -> dict:
    today = today or date.today()
    sales_all = frames["sales"]
    if sales_all.empty:
        return _empty("Upload sales, recipes, and menu data, then run the forecast.")

    frames = {**frames, "sales": _complete_weeks_only(sales_all)}
    if frames["sales"].empty:
        return _empty("Upload at least one full week (Monday to Sunday) of sales to run the forecast.")
    recipes = recipe_versions_of(frames)
    if recipes.empty:
        return _empty("Upload recipes so dish sales can be turned into ingredient usage.")

    matrix = build_dish_matrix(frames["restaurant_id"], frames["sales"], frames["events"])
    observed = matrix[matrix[QTY].notna()]
    weeks = sorted(observed["forecast_week"].unique())
    weeks_of_history = len(weeks)
    history = to_ingredient_usage(observed, QTY, recipes)

    try:
        dish_bt = rolling_backtest_dish(matrix)
    except ValueError:
        dish_bt = None
    bt = to_ingredient_weeks(dish_bt, recipes) if dish_bt is not None else None
    summary = summarize(bt) if bt is not None else None

    usable = usable_rows(matrix)
    usable_weeks = sorted(usable["forecast_week"].unique())
    model, method = None, "baseline"
    reason = "Too little history to train a model yet, so the same-weekday average is used."
    if len(usable_weeks) >= 3:
        model = fit(usable[usable["forecast_week"] < usable_weeks[-2]], usable[usable["forecast_week"] >= usable_weeks[-2]])
        method, reason = "xgboost_blend", "XGBoost blended 50/50 with the same-weekday average."
    if model is not None and summary is not None and summary.loc["xgboost", "wape"] > summary.loc["dish_baseline", "wape"]:
        # Champion check: ship what has actually been more accurate on this restaurant's history.
        model, method = None, "weekday_baseline"
        reason = "The model has not beaten the same-weekday average on your history yet, so the average is used."
        dish_bt = dish_bt.assign(xgboost=dish_bt["dish_baseline"])
        bt = bt.assign(xgboost=bt["dish_baseline"])

    last_week = pd.Timestamp(weeks[-1])
    target_monday, ahead, stale = _target(last_week, today, target_week)
    steps = forecast_weeks(model, frames, ahead, estimate_lifts(matrix))
    target = steps[-1]

    dish_totals = target.groupby("menu_item_id")["pred"].sum()
    event_dishes = set(target.loc[target["event_multiplier"] != 1.0, "menu_item_id"])
    evals = uncertainty.expanding_evaluations(dish_bt, recipes) if dish_bt is not None else []
    samples, scale = uncertainty.forecast_samples(dish_bt, recipes, dish_totals, ahead, event_dishes, evals)
    point = to_ingredient_usage(target, "pred", recipes).droplevel(0)
    normal = to_ingredient_usage(target, "pred_normal", recipes).droplevel(0)
    quantiles = samples.quantile([0.1, 0.5, 0.9])
    has_bands = dish_bt is not None

    accuracy = None
    banded = None
    if bt is not None:
        quality = compare_band_methods(bt, evals) if evals else {"monte_carlo": None, "pooled_ratio": None}
        if evals:
            banded, _ = uncertainty.score_bands(evals)
        mc = quality["monte_carlo"]
        accuracy = {
            "backtest_weeks": int(bt["forecast_week"].nunique()),
            "methods": summary.to_dict("index"),
            "band_coverage": {**mc, "target_inside": TARGET_COVERAGE} if mc else None,
            "band_comparison": quality,
            "spread_scale": round(scale, 2),
            "stockout_days_excluded": int(dish_bt[CENSORED].sum()),
        }

    # Order recommendations, on the restaurant's own delivery days.
    ingredients = frames["ingredients"]
    purchases = _frame(frames, "purchases", ["date", "ingredient_id", "qty"])
    days = recommend.delivery_days(purchases)
    recipe_now = uncertainty.recipe_matrix(recipes, list(dish_totals.index))
    costs = recommend.unit_costs(ingredients, recipe_now, frames.get("menu"), dish_totals)
    actual_usage = recommend.daily_usage(sales_all, recipes)
    gap_usage = (
        pd.concat([_usage_rows(step, "pred", recipes) for step in steps[:-1]])
        if len(steps) > 1 else pd.DataFrame(columns=["date", "ingredient_id", "qty"])
    )
    on_hand = recommend.projected_on_hand(
        _frame(frames, "counts", ["date", "ingredient_id", "qty_on_hand"]), purchases, actual_usage, gap_usage, target_monday,
    )
    by_cycle = recommend.cycle_usage(_usage_rows(target, "pred", recipes), days)
    shares = by_cycle.div(by_cycle.sum(axis=1), axis=0).fillna(0.0)
    last_week_usage = history.xs(last_week, level="forecast_week")
    orders = recommend.recommend(samples, shares, costs, on_hand, last_week_usage, days).set_index("ingredient_id")

    savings = {
        "delivery_days": [recommend.WEEKDAYS[d] for d in days],
        "weekly_expected_vs_habit": _num(orders["expected_savings"].sum(), 2),
        "expected_waste_cost": _num(orders["expected_waste_cost"].sum(), 2),
        "habit_waste_cost": _num(orders["habit_waste_cost"].sum(), 2),
        "order_backtest": (
            recommend.order_backtest(_order_backtest_weeks(dish_bt, recipes, frames, days), costs)
            if dish_bt is not None else None
        ),
    }

    info = ingredients.set_index("ingredient_id")
    target_week_iso = _week(target_monday)
    out_ingredients = []
    for ingredient_id in samples.columns:
        o = orders.loc[ingredient_id]
        base_usage = normal.get(ingredient_id, 0.0)
        entry = {
            "ingredient_id": ingredient_id,
            "name": info.loc[ingredient_id, "name"] if ingredient_id in info.index else ingredient_id,
            "unit": info.loc[ingredient_id, "unit"] if ingredient_id in info.index else "",
            "history": [{"week": _week(w), "usage": _num(u)} for (w, i), u in history.items() if i == ingredient_id],
            "forecast": {
                "week": target_week_iso,
                "point": _num(point.get(ingredient_id)),
                # Without out-of-sample errors there is no honest range yet.
                "p10": _num(quantiles.loc[0.1, ingredient_id]) if has_bands else None,
                "p50": _num(quantiles.loc[0.5, ingredient_id]) if has_bands else None,
                "p90": _num(quantiles.loc[0.9, ingredient_id]) if has_bands else None,
                "event_adjustment_pct": (
                    _num((point.get(ingredient_id, 0.0) / base_usage - 1) * 100, 1) if base_usage > 0 else None
                ),
            },
            "recommendation": {
                "order_qty": _num(o["order_qty"], 2),
                "packs": None if o["packs"] is None or pd.isna(o["packs"]) else int(o["packs"]),
                "pack_size": _num(o["pack_size"], 3),
                "deliveries": [{**d, "qty": _num(d["qty"], 2)} for d in o["deliveries"]],
                "on_hand": _num(o["on_hand"], 2),
                "service_level": _num(o["service_level"], 2),
                "perishable": bool(o["perishable"]),
                "expected_leftover": _num(o["expected_leftover"], 2),
                "expected_waste_cost": _num(o["expected_waste_cost"], 2),
                "stockout_risk": _num(o["stockout_risk"], 3),
                "habit_order_qty": _num(o["habit_order_qty"], 2),
                "habit_stockout_risk": _num(o["habit_stockout_risk"], 3),
                "expected_savings": _num(o["expected_savings"], 2),
            },
            "backtest": [],
        }
        if bt is not None:
            band_rows = banded[banded["ingredient_id"] == ingredient_id].set_index("forecast_week") if banded is not None else None
            for r in bt[bt["ingredient_id"] == ingredient_id].itertuples(index=False):
                has_band = band_rows is not None and r.forecast_week in band_rows.index
                entry["backtest"].append({
                    "week": _week(r.forecast_week),
                    "actual": _num(r.actual),
                    "predicted": _num(r.xgboost),
                    "p10": _num(band_rows.loc[r.forecast_week, "p10"]) if has_band else None,
                    "p90": _num(band_rows.loc[r.forecast_week, "p90"]) if has_band else None,
                })
        out_ingredients.append(entry)
    out_ingredients.sort(key=lambda e: e["name"])

    last_sales = pd.to_datetime(sales_all["date"]).max()
    status = data_status(weeks_of_history)
    message = status["message"]
    if stale:
        message = (
            f"Your sales end on {last_sales.date().isoformat()}, more than {MAX_HORIZON_WEEKS} weeks ago. "
            "This forecast is for the week right after your data. Upload recent sales for a current order."
        )
    return {
        "data": {
            "weeks_of_history": weeks_of_history,
            "first_week": _week(weeks[0]),
            "last_week": _week(last_week),
            "forecast_week": target_week_iso,
            "target_week": target_week_iso,
            "based_on_sales_through": last_sales.date().isoformat(),
            "gap_weeks": ahead - 1,
            "stale": stale,
            "method": method,
            "method_reason": reason,
            "status": status["status"],
            "message": message,
        },
        "accuracy": accuracy,
        "events": _event_summary(target, frames["events"]),
        "savings": savings,
        "ingredients": out_ingredients,
    }
