import json
from datetime import date

import numpy as np
import pandas as pd

from sim.forecast_payload import build_forecast_payload, data_status

RECIPES = pd.DataFrame(
    [("burger", "beef", 0.2), ("wrap", "beef", 0.1), ("burger", "bun", 1.0)],
    columns=["menu_item_id", "ingredient_id", "qty_per_serving"],
)
INGREDIENTS = pd.DataFrame({
    "ingredient_id": ["beef", "bun"], "name": ["Beef", "Bun"], "unit": ["kg", "each"],
    "unit_cost": [10.0, 0.5], "pack_size": [5.0, 12.0], "shelf_life_days": [4.0, 5.0],
})
MENU = pd.DataFrame({"menu_item_id": ["burger", "wrap"], "name": ["Burger", "Wrap"], "price": [15.0, 12.0]})
EVENTS = pd.DataFrame(columns=["type", "name", "start_date", "end_date", "items", "discount_pct", "expected_lift"])
START = pd.Timestamp("2026-06-29")  # a Monday


def frames(weeks: int, extra_days: int = 0, events=EVENTS):
    days = pd.date_range(START, periods=7 * weeks + extra_days, freq="D")
    rng = np.random.default_rng(1)
    rows = [
        (d, dish, round(base * (1 + 0.1 * d.weekday()) * rng.uniform(0.9, 1.1)), 12.0)
        for d in days
        for dish, base in (("burger", 20), ("wrap", 10))
    ]
    sales = pd.DataFrame(rows, columns=["date", "menu_item_id", "qty_sold", "avg_price"])
    sundays = [d for d in days if d.weekday() == 6]
    counts = pd.DataFrame([(d, i, 5.0) for d in sundays for i in ("beef", "bun")], columns=["date", "ingredient_id", "qty_on_hand"])
    purchases = pd.DataFrame(
        [(d, i, q) for d in days if d.weekday() in (0, 3) for i, q in (("beef", 25.0), ("bun", 72.0))],
        columns=["date", "ingredient_id", "qty"],
    )
    return {
        "restaurant_id": "r1", "sales": sales, "recipes": RECIPES, "ingredients": INGREDIENTS,
        "events": events, "menu": MENU, "counts": counts, "purchases": purchases,
    }


def week_after(weeks: int) -> date:
    """A 'today' in the last sales week, so the target is the week right after the data."""
    return (START + pd.Timedelta(days=7 * weeks - 1)).date()


def test_data_status_thresholds():
    assert data_status(3)["status"] == "learning"
    assert data_status(8)["status"] == "improving"
    assert data_status(25)["status"] == "improving"
    assert data_status(26)["status"] == "established"
    assert "12 weeks" in data_status(12)["message"]


def test_full_payload_shape_and_strict_json():
    p = build_forecast_payload(frames(10), today=week_after(10))
    json.dumps(p, allow_nan=False)  # no NaN or numpy types
    assert p["data"]["weeks_of_history"] == 10
    assert p["data"]["status"] == "improving"
    assert p["data"]["method"] in {"xgboost_blend", "weekday_baseline"}
    assert p["data"]["forecast_week"] == p["data"]["target_week"] == "2026-09-07"
    assert p["data"]["gap_weeks"] == 0 and p["data"]["stale"] is False
    assert p["accuracy"]["backtest_weeks"] == 4
    assert set(p["accuracy"]["methods"]) == {"xgboost", "dish_baseline", "naive_last_week", "mean_4w"}
    assert p["accuracy"]["band_coverage"]["target_inside"] == 0.8
    assert [i["name"] for i in p["ingredients"]] == ["Beef", "Bun"]
    beef = p["ingredients"][0]
    assert len(beef["history"]) == 10 and len(beef["backtest"]) == 4
    f = beef["forecast"]
    assert f["p10"] <= f["p50"] <= f["p90"] and f["point"] > 0
    assert beef["backtest"][0]["p10"] is None  # the first origins have no earlier errors for a band


def test_recommendation_follows_delivery_days_and_packs():
    p = build_forecast_payload(frames(10), today=week_after(10))
    assert p["savings"]["delivery_days"] == ["Monday", "Thursday"]
    rec = p["ingredients"][0]["recommendation"]
    assert [d["day"] for d in rec["deliveries"]] == ["Monday", "Thursday"]
    assert rec["deliveries"][0]["firm"] and not rec["deliveries"][1]["firm"]
    assert all(d["qty"] % 5 == 0 for d in rec["deliveries"])  # whole 5 kg packs
    assert 0 <= rec["stockout_risk"] <= 1 and 0.5 <= rec["service_level"] <= 0.95
    assert p["savings"]["order_backtest"]["weeks"] >= 1


def test_target_week_is_anchored_to_today_and_rolls_forward():
    p = build_forecast_payload(frames(10), today=week_after(10) + pd.Timedelta(days=7))
    assert p["data"]["last_week"] == "2026-08-31"
    assert p["data"]["target_week"] == "2026-09-14" and p["data"]["gap_weeks"] == 1


def test_stale_data_forecasts_the_week_after_the_data():
    p = build_forecast_payload(frames(10), today=date(2027, 3, 1))
    assert p["data"]["stale"] is True and p["data"]["target_week"] == "2026-09-07"
    assert "Upload recent sales" in p["data"]["message"]


def test_partial_week_is_not_history():
    p = build_forecast_payload(frames(10, extra_days=3), today=week_after(10))  # week 11 only Mon to Wed
    assert p["data"]["weeks_of_history"] == 10
    assert p["data"]["last_week"] == "2026-08-31"
    assert p["data"]["based_on_sales_through"] == "2026-09-09"
    assert p["data"]["forecast_week"] == "2026-09-07"  # the in-progress week is the one being forecast


def test_short_history_falls_back_without_error():
    p = build_forecast_payload(frames(2), today=week_after(2))
    json.dumps(p, allow_nan=False)
    assert p["data"]["status"] == "learning" and p["data"]["method"] == "baseline"
    assert p["accuracy"] is None
    assert p["ingredients"][0]["forecast"]["p10"] is None


def test_upcoming_deal_gets_an_explicit_lift():
    events = pd.DataFrame(
        [("deal", "Wrap Weekend", START + pd.Timedelta(days=18), START + pd.Timedelta(days=20), ["wrap"], 0.2, np.nan),
         ("deal", "Wrap Again", START + pd.Timedelta(days=74), START + pd.Timedelta(days=76), ["wrap"], 0.2, 0.5)],
        columns=EVENTS.columns,
    )
    p = build_forecast_payload(frames(10, events=events), today=week_after(10))
    (ev,) = p["events"]
    assert ev["name"] == "Wrap Again" and ev["lift_source"] == "owner" and ev["lift_pct"] == 50.0
    beef = p["ingredients"][0]
    assert beef["forecast"]["event_adjustment_pct"] > 0


def test_empty_sales():
    f = frames(2)
    f["sales"] = f["sales"].iloc[0:0]
    p = build_forecast_payload(f)
    assert p["ingredients"] == [] and p["data"]["weeks_of_history"] == 0


def test_less_than_a_full_week_returns_a_message_not_an_error():
    p = build_forecast_payload(frames(0, extra_days=4))
    assert p["ingredients"] == [] and "full week" in p["data"]["message"]


def test_missing_recipes_returns_a_message_not_an_error():
    f = frames(4)
    f["recipes"] = RECIPES.iloc[0:0]
    p = build_forecast_payload(f)
    assert p["ingredients"] == [] and "recipes" in p["data"]["message"]
