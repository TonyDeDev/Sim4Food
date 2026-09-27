import json

import numpy as np
import pandas as pd

from sim.forecast_payload import build_forecast_payload, data_status

RECIPES = pd.DataFrame(
    [("burger", "beef", 0.2), ("wrap", "beef", 0.1), ("burger", "bun", 1.0)],
    columns=["menu_item_id", "ingredient_id", "qty_per_serving"],
)
INGREDIENTS = pd.DataFrame(
    {"ingredient_id": ["beef", "bun"], "name": ["Beef", "Bun"], "unit": ["kg", "each"]}
)
EVENTS = pd.DataFrame(columns=["type", "start_date", "end_date", "items", "discount_pct", "expected_lift"])


def frames(weeks: int, extra_days: int = 0):
    days = pd.date_range("2026-06-29", periods=7 * weeks + extra_days, freq="D")
    rng = np.random.default_rng(1)
    rows = [
        (d, dish, round(base * (1 + 0.1 * d.weekday()) * rng.uniform(0.9, 1.1)), 12.0)
        for d in days
        for dish, base in (("burger", 20), ("wrap", 10))
    ]
    sales = pd.DataFrame(rows, columns=["date", "menu_item_id", "qty_sold", "avg_price"])
    return {"restaurant_id": "r1", "sales": sales, "recipes": RECIPES, "ingredients": INGREDIENTS, "events": EVENTS}


def test_data_status_thresholds():
    assert data_status(3)["status"] == "learning"
    assert data_status(8)["status"] == "improving"
    assert data_status(25)["status"] == "improving"
    assert data_status(26)["status"] == "established"
    assert "12 weeks" in data_status(12)["message"]


def test_full_payload_shape_and_strict_json():
    p = build_forecast_payload(frames(10))
    json.dumps(p, allow_nan=False)  # no NaN or numpy types
    assert p["data"]["weeks_of_history"] == 10
    assert p["data"]["status"] == "improving"
    assert p["data"]["method"] == "xgboost"
    assert p["data"]["forecast_week"] == "2026-09-07"
    assert p["accuracy"]["backtest_weeks"] == 4
    assert set(p["accuracy"]["methods"]) == {"xgboost", "dish_baseline", "naive_last_week", "mean_4w"}
    assert [i["name"] for i in p["ingredients"]] == ["Beef", "Bun"]
    beef = p["ingredients"][0]
    assert len(beef["history"]) == 10 and len(beef["backtest"]) == 4
    f = beef["forecast"]
    assert f["p10"] <= f["p50"] <= f["p90"] and f["point"] > 0
    assert beef["backtest"][0]["p10"] is None  # first origin has no earlier errors for a band


def test_partial_week_is_not_history():
    p = build_forecast_payload(frames(10, extra_days=3))  # week 11 only Mon to Wed
    assert p["data"]["weeks_of_history"] == 10
    assert p["data"]["last_week"] == "2026-08-31"
    assert p["data"]["forecast_week"] == "2026-09-07"  # the in-progress week is the one being forecast


def test_short_history_falls_back_without_error():
    p = build_forecast_payload(frames(2))
    json.dumps(p, allow_nan=False)
    assert p["data"]["status"] == "learning" and p["data"]["method"] == "baseline"
    assert p["accuracy"] is None
    assert p["ingredients"][0]["forecast"]["p10"] is None


def test_empty_sales():
    f = frames(2)
    f["sales"] = f["sales"].iloc[0:0]
    p = build_forecast_payload(f)
    assert p["ingredients"] == [] and p["data"]["weeks_of_history"] == 0
