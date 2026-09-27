"""Train the daily dish-level XGBoost model and convert it to ingredient usage.

Usage (from backend/): python -m sim.train_dish_xgb --restaurant-id "<restaurants.id>"

The model predicts each dish's daily quantity as a ratio to its same-weekday
baseline (see sim/dish_features.py). Predicted dish quantities are converted to
ingredient usage with recipes, then compared per ingredient and week against
naive baselines. Split is chronological: last 2 weeks test, the 2 before that
validation (early stopping), earlier weeks train.
"""
import argparse
import asyncio
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

from app import db
from sim.dataset import load_frames
from sim.dish_features import BASELINE, DISH_FEATURES, QTY, RATIO, RATIO_CLIP, build_dish_matrix
from sim.history import attach_recipes, recipe_versions_of

MODEL_DIR = Path(__file__).resolve().parent.parent / "models"
TEST_WEEKS = 2
VAL_WEEKS = 2
SEED = 42

PARAMS = dict(
    n_estimators=400,
    learning_rate=0.03,
    max_depth=3,
    min_child_weight=5,
    subsample=0.8,
    colsample_bytree=0.8,
    reg_lambda=5.0,
    objective="reg:squarederror",
    early_stopping_rounds=30,
    random_state=SEED,
)


def usable_rows(matrix: pd.DataFrame) -> pd.DataFrame:
    return matrix[matrix[QTY].notna() & matrix[BASELINE].notna()]


def split_by_week(matrix: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    usable = usable_rows(matrix)
    weeks = sorted(usable["forecast_week"].unique())
    if len(weeks) <= TEST_WEEKS + VAL_WEEKS:
        raise ValueError(f"Need more than {TEST_WEEKS + VAL_WEEKS} usable weeks, have {len(weeks)}")
    val_weeks, test_weeks = weeks[-(TEST_WEEKS + VAL_WEEKS):-TEST_WEEKS], weeks[-TEST_WEEKS:]
    train = usable[usable["forecast_week"] < val_weeks[0]]
    return train, usable[usable["forecast_week"].isin(val_weeks)], usable[usable["forecast_week"].isin(test_weeks)]


def fit(train: pd.DataFrame, val: pd.DataFrame) -> xgb.XGBRegressor:
    """Fit on the ratio target, weighting rows by baseline so big dishes count more.

    Weighting by baseline makes the ratio loss track absolute error in servings.
    """
    def prep(df):
        df = df[df[BASELINE] > 0]
        return df[DISH_FEATURES], df[RATIO], df[BASELINE] / df[BASELINE].mean()

    x_tr, y_tr, w_tr = prep(train)
    x_va, y_va, w_va = prep(val)
    model = xgb.XGBRegressor(**PARAMS)
    model.fit(x_tr, y_tr, sample_weight=w_tr, eval_set=[(x_va, y_va)], sample_weight_eval_set=[w_va], verbose=False)
    return model


def predict_qty(model: xgb.XGBRegressor | None, df: pd.DataFrame) -> pd.Series:
    """Dish quantity forecast. model=None returns the baseline (ratio fixed at 1)."""
    ratio = pd.Series(1.0, index=df.index)
    if model is not None:
        positive = df[BASELINE] > 0
        if positive.any():
            ratio[positive] = np.clip(model.predict(df.loc[positive, DISH_FEATURES]), *RATIO_CLIP)
    return df[BASELINE] * ratio


def to_ingredient_usage(df: pd.DataFrame, qty_col: str, recipes: pd.DataFrame) -> pd.Series:
    """Weekly ingredient usage = sum over dishes and days of qty x qty_per_serving.

    `recipes` may be a recipe version frame (see sim.history), in which case each
    day uses the recipe line in force on that day.
    """
    date_col = "date" if "date" in df.columns else "forecast_week"
    cols = ["forecast_week", "menu_item_id", qty_col] + ([date_col] if date_col == "date" else [])
    joined = attach_recipes(df[cols], recipes, date_col)
    joined["usage"] = joined[qty_col] * joined["qty_per_serving"]
    return joined.groupby(["forecast_week", "ingredient_id"])["usage"].sum()


def naive_baselines(matrix: pd.DataFrame, recipes: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Actual weekly ingredient usage plus last-week and 4-week-mean forecasts."""
    observed = matrix[matrix[QTY].notna()]
    actual = to_ingredient_usage(observed, QTY, recipes).unstack("ingredient_id").fillna(0.0)
    last_week = actual.shift(1)
    mean_4w = actual.shift(1).rolling(4, min_periods=1).mean().fillna(last_week)
    stack = lambda w: w.stack(future_stack=True)
    return stack(actual), stack(last_week), stack(mean_4w)


def metrics(actual: pd.Series, predicted: pd.Series) -> dict:
    err = (actual - predicted).abs()
    return {"mae": round(float(err.mean()), 4), "wape": round(float(err.sum() / actual.abs().sum()), 4)}


def evaluate(model: xgb.XGBRegressor, matrix: pd.DataFrame, test: pd.DataFrame, recipes: pd.DataFrame) -> pd.DataFrame:
    test = test.assign(pred=predict_qty(model, test), base=predict_qty(None, test))
    actual, last_week, mean_4w = naive_baselines(matrix, recipes)
    index = to_ingredient_usage(test, "pred", recipes).index
    rows = {
        "xgboost_dish_ratio": to_ingredient_usage(test, "pred", recipes),
        "dish_baseline_only": to_ingredient_usage(test, "base", recipes),
        "naive_last_week": last_week.reindex(index),
        "mean_4w": mean_4w.reindex(index),
    }
    truth = actual.reindex(index)
    table = pd.DataFrame({name: metrics(truth, pred) for name, pred in rows.items()}).T
    dish = {
        "xgboost_dish_ratio": metrics(test[QTY], test["pred"]),
        "dish_baseline_only": metrics(test[QTY], test["base"]),
    }
    print("\nDish-day metrics (servings, test weeks):")
    print(pd.DataFrame(dish).T.to_string())
    return table


def forecast_next_week(
    model: xgb.XGBRegressor, frames: dict, recipes: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Ingredient usage forecast for the week after the last sales week."""
    matrix = build_dish_matrix(frames["restaurant_id"], frames["sales"], frames["events"], include_next_week=True)
    last_observed = matrix.loc[matrix[QTY].notna(), "forecast_week"].max()
    future = matrix[matrix["forecast_week"] > last_observed]
    future = future.assign(pred=predict_qty(model, future))
    usage = to_ingredient_usage(future, "pred", recipes if recipes is not None else frames["recipes"])
    out = usage.reset_index().rename(columns={"usage": "predicted_usage"})
    out = out.merge(frames["ingredients"][["ingredient_id", "name", "unit"]], on="ingredient_id", how="left")
    return out.round(2)


async def main(restaurant_id: str) -> None:
    await db.connect()
    try:
        frames = await load_frames(restaurant_id)
    finally:
        await db.disconnect()

    matrix = build_dish_matrix(frames["restaurant_id"], frames["sales"], frames["events"])
    train, val, test = split_by_week(matrix)
    print(f"dish-day rows: train={len(train)} val={len(val)} test={len(test)}  features={len(DISH_FEATURES)}")

    model = fit(train, val)
    print(f"best iteration: {model.best_iteration}")

    print("\nIngredient-week metrics (test weeks):")
    print(evaluate(model, matrix, test, recipe_versions_of(frames)).to_string())

    importance = pd.Series(model.feature_importances_, index=DISH_FEATURES).sort_values(ascending=False)
    print("\nTop features:")
    print(importance.head(10).round(4).to_string())

    forecast = forecast_next_week(model, frames)
    week = matrix["forecast_week"].max() + pd.Timedelta(days=7)
    print(f"\nNext week forecast (week of {week.date()}):")
    print(forecast.drop(columns="ingredient_id")[["name", "predicted_usage", "unit"]].to_string(index=False))

    MODEL_DIR.mkdir(exist_ok=True)
    path = MODEL_DIR / "dish_ratio_xgb.json"
    model.save_model(path)
    print(f"\nsaved {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--restaurant-id", required=True, help="restaurants.id (UUID)")
    asyncio.run(main(parser.parse_args().restaurant_id))
