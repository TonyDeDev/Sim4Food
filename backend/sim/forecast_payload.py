"""JSON-ready forecast payload for the frontend (charts plus data-quality status).

Everything the forecast page needs in one response: per-ingredient history,
next week forecast with P10/P50/P90 bands, backtest predicted vs actual, and a
summary of how much data there is and how trustworthy the bands have been.

Order quantities, expected waste and savings are not included yet. They need
the recommendation step (stock on hand, newsvendor, pack rounding).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from sim.dish_features import QTY, build_dish_matrix
from sim.forecast_backtest import (
    METHODS,
    apply_bands,
    coverage,
    expanding_bands,
    ratio_quantiles,
    relative_errors,
    rolling_backtest,
    summarize,
)
from sim.history import recipe_versions_of
from sim.train_dish_xgb import fit, forecast_next_week, to_ingredient_usage, usable_rows

LEARNING_WEEKS = 8
ESTABLISHED_WEEKS = 26
TARGET_COVERAGE = 0.8


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


def _complete_weeks_only(sales: pd.DataFrame) -> pd.DataFrame:
    """Drop the in-progress week, so a partial week is never read as a slow one."""
    dates = pd.to_datetime(sales["date"]).dt.normalize()
    max_date = dates.max()
    monday = max_date - pd.Timedelta(days=max_date.weekday())
    last_complete_end = max_date if max_date.weekday() == 6 else monday - pd.Timedelta(days=1)
    return sales[dates <= last_complete_end]


def build_forecast_payload(frames: dict) -> dict:
    sales = frames["sales"]
    if sales.empty:
        return {"data": {"weeks_of_history": 0, **data_status(0)}, "accuracy": None, "ingredients": []}

    frames = {**frames, "sales": _complete_weeks_only(sales)}
    recipes = recipe_versions_of(frames)
    matrix = build_dish_matrix(frames["restaurant_id"], frames["sales"], frames["events"])
    observed = matrix[matrix[QTY].notna()]
    weeks = sorted(observed["forecast_week"].unique())
    weeks_of_history = len(weeks)

    history = to_ingredient_usage(observed, QTY, recipes)

    try:
        bt = rolling_backtest(matrix, recipes)
    except ValueError:
        bt = None

    usable_weeks = sorted(usable_rows(matrix)["forecast_week"].unique())
    if len(usable_weeks) >= 3:
        usable = usable_rows(matrix)
        model = fit(usable[usable["forecast_week"] < usable_weeks[-2]], usable[usable["forecast_week"] >= usable_weeks[-2]])
        method = "xgboost"
    else:
        model, method = None, "baseline"  # too little history to train, uses the same weekday average

    forecast = forecast_next_week(model, frames).set_index("ingredient_id")
    bands = None
    banded = None
    accuracy = None
    if bt is not None:
        bands = apply_bands(forecast["predicted_usage"], ratio_quantiles(relative_errors(bt)))
        try:
            banded = expanding_bands(bt)
            band_coverage = {**coverage(banded), "target_inside": TARGET_COVERAGE}
        except ValueError:
            band_coverage = None
        accuracy = {
            "backtest_weeks": int(bt["forecast_week"].nunique()),
            "methods": {m: v for m, v in summarize(bt).to_dict("index").items()},
            "band_coverage": band_coverage,
        }

    names = frames["ingredients"].set_index("ingredient_id")
    forecast_week = _week(forecast["forecast_week"].iloc[0])

    ingredients = []
    for ingredient_id, row in forecast.iterrows():
        entry = {
            "ingredient_id": ingredient_id,
            "name": names.loc[ingredient_id, "name"] if "name" in names else ingredient_id,
            "unit": row["unit"],
            "history": [
                {"week": _week(w), "usage": _num(u)}
                for (w, i), u in history.items()
                if i == ingredient_id
            ],
            "forecast": {
                "week": forecast_week,
                "point": _num(row["predicted_usage"]),
                "p10": _num(bands.loc[ingredient_id, "p10"]) if bands is not None else None,
                "p50": _num(bands.loc[ingredient_id, "p50"]) if bands is not None else None,
                "p90": _num(bands.loc[ingredient_id, "p90"]) if bands is not None else None,
            },
            "backtest": [],
        }
        if bt is not None:
            rows = bt[bt["ingredient_id"] == ingredient_id]
            band_rows = banded[banded["ingredient_id"] == ingredient_id].set_index("forecast_week") if banded is not None else None
            for r in rows.itertuples(index=False):
                has_band = band_rows is not None and r.forecast_week in band_rows.index
                entry["backtest"].append(
                    {
                        "week": _week(r.forecast_week),
                        "actual": _num(r.actual),
                        "predicted": _num(r.xgboost),
                        "p10": _num(band_rows.loc[r.forecast_week, "p10"]) if has_band else None,
                        "p90": _num(band_rows.loc[r.forecast_week, "p90"]) if has_band else None,
                    }
                )
        ingredients.append(entry)
    ingredients.sort(key=lambda e: e["name"])

    return {
        "data": {
            "weeks_of_history": weeks_of_history,
            "first_week": _week(weeks[0]),
            "last_week": _week(weeks[-1]),
            "forecast_week": forecast_week,
            "method": method,
            **data_status(weeks_of_history),
        },
        "accuracy": accuracy,
        "ingredients": ingredients,
    }
