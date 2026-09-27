"""Rolling-origin backtest and P10 to P90 bands for the dish-level XGBoost model.

For every origin week T the model is retrained using only weeks before T
(early stopping on the 2 weeks just before T), predicts week T, and the result
is converted to ingredient usage. Errors from these out-of-sample forecasts
give (a) a more reliable accuracy estimate than one fixed test split and
(b) residual-based bands: the spread of actual / predicted from earlier origins
is applied to a new forecast.

Usage (from backend/):
  python -m sim.forecast_backtest --restaurant-id "<restaurants.id>"
  python -m sim.forecast_backtest --csv-dir data/demo        (offline)
"""
import argparse
import asyncio
import math

import numpy as np
import pandas as pd

from sim.dataset import load_frames, load_frames_from_csv
from sim.dish_features import build_dish_matrix
from sim.history import recipe_versions_of
from sim.train_dish_xgb import (
    fit,
    forecast_next_week,
    metrics,
    naive_baselines,
    predict_qty,
    to_ingredient_usage,
    usable_rows,
)

QUANTILES = (0.1, 0.5, 0.9)
METHODS = ["xgboost", "dish_baseline", "naive_last_week", "mean_4w"]


def rolling_backtest(
    matrix: pd.DataFrame, recipes: pd.DataFrame, min_train_weeks: int = 3, val_weeks: int = 2
) -> pd.DataFrame:
    """Out-of-sample ingredient-week forecasts, one origin per week.

    Returns columns: forecast_week, ingredient_id, actual, xgboost,
    dish_baseline, naive_last_week, mean_4w.
    """
    usable = usable_rows(matrix)
    weeks = sorted(usable["forecast_week"].unique())
    actual, last_week, mean_4w = naive_baselines(matrix, recipes)

    frames = []
    for i in range(min_train_weeks + val_weeks, len(weeks)):
        target_week = weeks[i]
        val_start = weeks[i - val_weeks]
        train = usable[usable["forecast_week"] < val_start]
        val = usable[(usable["forecast_week"] >= val_start) & (usable["forecast_week"] < target_week)]
        test = usable[usable["forecast_week"] == target_week]

        model = fit(train, val)
        test = test.assign(pred=predict_qty(model, test), base=predict_qty(None, test))
        pred = to_ingredient_usage(test, "pred", recipes)
        frame = pd.DataFrame(
            {
                "actual": actual.reindex(pred.index),
                "xgboost": pred,
                "dish_baseline": to_ingredient_usage(test, "base", recipes),
                "naive_last_week": last_week.reindex(pred.index),
                "mean_4w": mean_4w.reindex(pred.index),
            }
        )
        frames.append(frame.reset_index())
    if not frames:
        raise ValueError("Not enough weeks for a rolling backtest")
    return pd.concat(frames, ignore_index=True)


def summarize(bt: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({m: metrics(bt["actual"], bt[m]) for m in METHODS}).T


def relative_errors(bt: pd.DataFrame) -> pd.Series:
    """actual / predicted, for rows where the prediction is positive."""
    ok = bt["xgboost"] > 0
    return (bt.loc[ok, "actual"] / bt.loc[ok, "xgboost"]).rename("ratio")


def conformal_quantile(values: pd.Series, q: float) -> float:
    """Finite-sample corrected quantile (split conformal).

    A plain quantile of n past errors covers slightly less than q on new data.
    The corrected rank ceil((n + 1) q) for upper quantiles and floor((n + 1) q)
    for lower ones widens the interval when n is small, and falls back to the
    sample max or min when n is too small to reach the rank.
    """
    sorted_values = np.sort(values.to_numpy(dtype=float))
    n = len(sorted_values)
    if n == 0:
        raise ValueError("No errors to build bands from")
    if q >= 0.5:
        rank = math.ceil((n + 1) * q)
        return float(sorted_values[min(rank, n) - 1])
    rank = math.floor((n + 1) * q)
    return float(sorted_values[max(rank, 1) - 1])


def ratio_quantiles(ratios: pd.Series, quantiles=QUANTILES) -> dict[float, float]:
    """Multipliers on a forecast for each quantile (pooled across ingredients)."""
    return {q: conformal_quantile(ratios, q) for q in quantiles}


def apply_bands(forecast: pd.Series, multipliers: dict[float, float]) -> pd.DataFrame:
    lo, mid, hi = (multipliers[q] for q in QUANTILES)
    return pd.DataFrame({"p10": forecast * lo, "p50": forecast * mid, "p90": forecast * hi})


def expanding_bands(bt: pd.DataFrame, min_errors: int = 8) -> pd.DataFrame:
    """P10/P50/P90 for each origin week using only errors from earlier origins."""
    parts = []
    for week in sorted(bt["forecast_week"].unique()):
        prior = relative_errors(bt[bt["forecast_week"] < week])
        if len(prior) < min_errors:
            continue
        rows = bt[bt["forecast_week"] == week]
        bands = apply_bands(rows["xgboost"], ratio_quantiles(prior))
        parts.append(rows.join(bands))
    if not parts:
        raise ValueError("Not enough prior errors to build bands")
    return pd.concat(parts)


def coverage(banded: pd.DataFrame) -> dict:
    """Share of actuals inside P10 to P90 (ideal 0.80), below P10 and above P90 (ideal 0.10 each)."""
    below = (banded["actual"] < banded["p10"]).mean()
    above = (banded["actual"] > banded["p90"]).mean()
    return {
        "inside_p10_p90": round(float(1 - below - above), 3),
        "below_p10": round(float(below), 3),
        "above_p90": round(float(above), 3),
        "n": int(len(banded)),
    }


def forecast_next_week_with_bands(frames: dict, bt: pd.DataFrame) -> pd.DataFrame:
    """Next week's ingredient forecast with bands, model trained on all observed weeks."""
    matrix = build_dish_matrix(frames["restaurant_id"], frames["sales"], frames["events"])
    usable = usable_rows(matrix)
    weeks = sorted(usable["forecast_week"].unique())
    train = usable[usable["forecast_week"] < weeks[-2]]
    val = usable[usable["forecast_week"] >= weeks[-2]]
    model = fit(train, val)

    forecast = forecast_next_week(model, frames).set_index("ingredient_id")
    bands = apply_bands(forecast["predicted_usage"], ratio_quantiles(relative_errors(bt)))
    return forecast.join(bands, rsuffix="_band").round(2).reset_index()


async def _load(args) -> dict:
    if args.csv_dir:
        return load_frames_from_csv(args.csv_dir)
    from app import db

    await db.connect()
    try:
        return await load_frames(args.restaurant_id)
    finally:
        await db.disconnect()


async def main(args) -> None:
    frames = await _load(args)
    matrix = build_dish_matrix(frames["restaurant_id"], frames["sales"], frames["events"])
    bt = rolling_backtest(matrix, recipe_versions_of(frames))
    weeks = sorted(bt["forecast_week"].unique())
    print(f"origins: {len(weeks)} weeks ({weeks[0].date()} to {weeks[-1].date()}), {len(bt)} ingredient-weeks")

    print("\nOut-of-sample accuracy across all origins (ingredient-week):")
    print(summarize(bt).to_string())

    by_week = bt.groupby("forecast_week").apply(
        lambda g: pd.Series({m: metrics(g["actual"], g[m])["wape"] for m in METHODS}), include_groups=False
    )
    print("\nWAPE by origin week:")
    print(by_week.round(3).to_string())

    banded = expanding_bands(bt)
    print("\nBand coverage, bands built only from earlier origins (ideal 0.80 inside, 0.10 below, 0.10 above):")
    print(pd.Series(coverage(banded)).to_string())

    mult = ratio_quantiles(relative_errors(bt))
    print(f"\nPooled multipliers on forecast: P10 x{mult[0.1]:.3f}  P50 x{mult[0.5]:.3f}  P90 x{mult[0.9]:.3f}")

    forecast = forecast_next_week_with_bands(frames, bt)
    print("\nNext week forecast with bands:")
    print(forecast[["name", "p10", "p50", "p90", "predicted_usage", "unit"]].to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--restaurant-id", help="restaurants.id (UUID)")
    parser.add_argument("--csv-dir", help="use demo CSVs instead of the database")
    ns = parser.parse_args()
    if not ns.restaurant_id and not ns.csv_dir:
        parser.error("give --restaurant-id or --csv-dir")
    asyncio.run(main(ns))
