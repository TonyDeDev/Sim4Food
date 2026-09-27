"""Rolling-origin backtest and P10 to P90 bands for the dish-level XGBoost model.

For every origin week T the model is retrained using only weeks before T
(early stopping on the 2 weeks just before T, then refit), predicts week T, and
the result is converted to ingredient usage. These out-of-sample forecasts give
(a) a more reliable accuracy estimate than one fixed test split and (b) the
residuals the forecast bands are built from (sim/uncertainty.py).

Accuracy is scored on uncensored dish-days only: on a stockout day the sales
figure is not the demand, so it would reward a model for predicting stockouts.
Every method is scored on exactly the same rows.

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
from sim.dish_features import CENSORED, QTY, build_dish_matrix
from sim.history import recipe_versions_of
from sim.events_adjust import estimate_lifts, multipliers
from sim.train_dish_xgb import fit, metrics, predict_qty, to_ingredient_usage, usable_rows, uses_event_features
from sim import uncertainty

QUANTILES = (0.1, 0.5, 0.9)
METHODS = ["xgboost", "dish_baseline", "naive_last_week", "mean_4w"]
MAX_ORIGINS = 12


def _naive_dish_forecasts(matrix: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Per dish-day: sales 7 days earlier, and the raw same-weekday mean of the last 4 weeks.

    These are what an owner would eyeball from the POS, zeros and stockouts included.
    """
    raw = matrix.pivot_table(index="date", columns="menu_item_id", values=QTY, aggfunc="sum", dropna=False)
    raw = raw.reindex(pd.date_range(raw.index.min(), raw.index.max(), freq="D"))
    last = raw.shift(7)
    mean_4w = pd.concat([raw.shift(7 * k) for k in (1, 2, 3, 4)]).groupby(level=0).mean()

    def long(wide):
        s = wide.stack(future_stack=True)
        s.index.names = ["date", "menu_item_id"]
        return s

    return long(last), long(mean_4w)


def rolling_backtest_dish(
    matrix: pd.DataFrame, min_train_weeks: int = 3, val_weeks: int = 2, max_origins: int = MAX_ORIGINS
) -> pd.DataFrame:
    """Out-of-sample dish-day forecasts, one origin per week (the last `max_origins`).

    Returns the usable matrix rows of each origin week plus columns xgboost
    (the shipped blend), dish_baseline (weekday baseline), both with the explicit
    event lift, and the owner-style naive_last_week and mean_4w.
    """
    usable = usable_rows(matrix)
    weeks = sorted(usable["forecast_week"].unique())
    origins = weeks[min_train_weeks + val_weeks:][-max_origins:]
    if not origins:
        raise ValueError("Not enough weeks for a rolling backtest")
    last, mean_4w = _naive_dish_forecasts(matrix)

    parts = []
    for target_week in origins:
        i = weeks.index(target_week)
        val_start = weeks[i - val_weeks]
        train = usable[usable["forecast_week"] < val_start]
        val = usable[(usable["forecast_week"] >= val_start) & (usable["forecast_week"] < target_week)]
        test = usable[usable["forecast_week"] == target_week]
        model = fit(train, val)
        pred, base = predict_qty(model, test), predict_qty(None, test)
        # Same as the live forecast: explicit event lift, estimated from earlier weeks only.
        lift = multipliers(test, estimate_lifts(matrix[matrix["forecast_week"] < target_week]))[0]
        if not uses_event_features(model):
            pred = pred * lift
        key = pd.MultiIndex.from_frame(test[["date", "menu_item_id"]])
        parts.append(
            test.assign(
                xgboost=pred.values,
                dish_baseline=(base * lift).values,
                naive_last_week=last.reindex(key).values,
                mean_4w=mean_4w.reindex(key).values,
            )
        )
    return pd.concat(parts, ignore_index=True)


def to_ingredient_weeks(dish_bt: pd.DataFrame, recipes: pd.DataFrame) -> pd.DataFrame:
    """Ingredient-week actual and forecasts over uncensored dish-days.

    Columns: forecast_week, ingredient_id, actual, xgboost, dish_baseline, naive_last_week, mean_4w.
    """
    scored = dish_bt[~dish_bt[CENSORED]].rename(columns={QTY: "actual"})
    cols = {c: to_ingredient_usage(scored, c, recipes) for c in ["actual"] + METHODS}
    return pd.DataFrame(cols).reset_index()


def rolling_backtest(
    matrix: pd.DataFrame, recipes: pd.DataFrame, min_train_weeks: int = 3, val_weeks: int = 2
) -> pd.DataFrame:
    """Out-of-sample ingredient-week forecasts, see to_ingredient_weeks."""
    return to_ingredient_weeks(rolling_backtest_dish(matrix, min_train_weeks, val_weeks), recipes)


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
    """Pooled-ratio P10/P50/P90 for each origin week using only errors from earlier origins.

    The first band method, kept as the comparison for sim.uncertainty.
    """
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


def compare_band_methods(bt: pd.DataFrame, evals: list) -> dict:
    """Out-of-sample quality of the Monte Carlo bands vs the pooled-ratio bands, on the same weeks."""
    mc_banded, mc = uncertainty.score_bands(evals)
    out = {"monte_carlo": mc, "pooled_ratio": None}
    try:
        pooled = expanding_bands(bt)
    except ValueError:
        return out
    pooled = pooled[pooled["forecast_week"].isin(set(mc_banded["forecast_week"]))]
    if not pooled.empty:
        out["pooled_ratio"] = uncertainty.interval_metrics(pooled)
    return out


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
    recipes = recipe_versions_of(frames)
    matrix = build_dish_matrix(frames["restaurant_id"], frames["sales"], frames["events"])
    dish_bt = rolling_backtest_dish(matrix)
    bt = to_ingredient_weeks(dish_bt, recipes)
    weeks = sorted(bt["forecast_week"].unique())
    print(f"origins: {len(weeks)} weeks ({weeks[0].date()} to {weeks[-1].date()}), {len(bt)} ingredient-weeks")
    print(f"stockout dish-days excluded from scoring: {int(dish_bt[CENSORED].sum())}")

    print("\nOut-of-sample accuracy across all origins (ingredient-week):")
    print(summarize(bt).to_string())

    by_week = bt.groupby("forecast_week").apply(
        lambda g: pd.Series({m: metrics(g["actual"], g[m])["wape"] for m in METHODS}), include_groups=False
    )
    print("\nWAPE by origin week:")
    print(by_week.round(3).to_string())

    evals = uncertainty.expanding_evaluations(dish_bt, recipes)
    print("\nBand quality, out of sample (ideal inside 0.80; interval score and pinball: lower is better):")
    print(pd.DataFrame(compare_band_methods(bt, evals)).T.to_string())
    print(f"\nMonte Carlo spread scale fit on all weeks: {uncertainty.fit_scale(evals):.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--restaurant-id", help="restaurants.id (UUID)")
    parser.add_argument("--csv-dir", help="use demo CSVs instead of the database")
    ns = parser.parse_args()
    if not ns.restaurant_id and not ns.csv_dir:
        parser.error("give --restaurant-id or --csv-dir")
    asyncio.run(main(ns))
