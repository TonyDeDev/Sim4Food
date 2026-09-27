"""Train the daily dish-level XGBoost model and convert it to ingredient usage.

Usage (from backend/): python -m sim.train_dish_xgb --restaurant-id "<restaurants.id>"

The model predicts each dish's daily quantity as a ratio to its same-weekday
baseline (see sim/dish_features.py). Predicted dish quantities are converted to
ingredient usage with recipes, then compared per ingredient and week against
naive baselines. Split is chronological: last 2 weeks test, the 2 before that
validation (early stopping), earlier weeks train.

Training follows a few rules that matter on thin data:
- Early stopping on the validation weeks only picks the number of trees; the
  model is then refit on train + validation, so the newest weeks shape it.
- Censored (stockout) days are never a training target.
- Event features are only used once there are enough event rows to learn from
  (MIN_EVENT_ROWS); until then event days are left out of training and the lift
  is applied explicitly (sim/events_adjust.py).
- Season features are only used with a year of history (MIN_WEEKS_FOR_SEASON).
- Deal features are constrained to never lower demand (monotone constraints).
- The shipped forecast is an equal-weight blend of the model and the weekday
  baseline (ENSEMBLE_WEIGHT), and sim/forecast_payload.py falls back to the
  baseline alone when the blend does not beat it in the rolling backtest.
"""
import argparse
import asyncio
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

from sim.dish_features import (
    BASELINE,
    CALENDAR_FEATURES,
    CENSORED,
    DISH_FEATURES,
    EVENT_DAY,
    EVENT_FEATURES,
    QTY,
    RATIO,
    RATIO_CLIP,
    build_dish_matrix,
)
from sim.events_adjust import multipliers
from sim.history import attach_recipes, recipe_versions_of

MODEL_DIR = Path(__file__).resolve().parent.parent / "models"
TEST_WEEKS = 2
VAL_WEEKS = 2
SEED = 42
MIN_EVENT_ROWS = 30
MIN_WEEKS_FOR_SEASON = 52
DEFAULT_TREES = 100
MIN_TREES = 10
# Equal-weight combination of the model and the weekday baseline. A fixed 0.5 is
# the robust choice on thin data (tuning the weight on a few weeks overfits); on
# the demo backtest it beats both the model alone and the baseline alone.
ENSEMBLE_WEIGHT = 0.5

PARAMS = dict(
    n_estimators=400,
    learning_rate=0.03,
    max_depth=3,
    min_child_weight=5,
    subsample=0.8,
    colsample_bytree=0.8,
    reg_lambda=5.0,
    objective="reg:squarederror",
    random_state=SEED,
)

# A bigger discount or a dish on a deal can only raise demand.
MONOTONE_UP = ("deal_flag", "dish_event_flag", "event_discount_pct", "event_expected_lift")


def usable_rows(matrix: pd.DataFrame) -> pd.DataFrame:
    """Observed rows with a baseline: the rows a week is forecast and scored on."""
    return matrix[matrix[QTY].notna() & matrix[BASELINE].notna()]


def select_features(rows: pd.DataFrame) -> list[str]:
    """Feature list for a training set, see the module docstring."""
    features = list(DISH_FEATURES)
    trainable = rows[rows[RATIO].notna()]
    if int(trainable[EVENT_DAY].sum()) < MIN_EVENT_ROWS:
        features = [f for f in features if f not in EVENT_FEATURES]
    if rows["forecast_week"].nunique() >= MIN_WEEKS_FOR_SEASON:
        features += CALENDAR_FEATURES
    return features


def uses_event_features(model: xgb.XGBRegressor | None) -> bool:
    return model is not None and "dish_event_flag" in model_features(model)


def model_features(model: xgb.XGBRegressor) -> list[str]:
    return list(model.feature_names_in_)


def _training_rows(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    rows = df[df[RATIO].notna() & (df[BASELINE] > 0) & ~df[CENSORED]]
    if "dish_event_flag" not in features:
        rows = rows[~rows[EVENT_DAY]]  # the lift is applied explicitly, keep the normal week clean
    return rows


def _params(features: list[str]) -> dict:
    constraints = {f: 1 for f in MONOTONE_UP if f in features}
    return {**PARAMS, "monotone_constraints": constraints} if constraints else dict(PARAMS)


def split_by_week(matrix: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    usable = usable_rows(matrix)
    weeks = sorted(usable["forecast_week"].unique())
    if len(weeks) <= TEST_WEEKS + VAL_WEEKS:
        raise ValueError(f"Need more than {TEST_WEEKS + VAL_WEEKS} usable weeks, have {len(weeks)}")
    val_weeks, test_weeks = weeks[-(TEST_WEEKS + VAL_WEEKS):-TEST_WEEKS], weeks[-TEST_WEEKS:]
    train = usable[usable["forecast_week"] < val_weeks[0]]
    return train, usable[usable["forecast_week"].isin(val_weeks)], usable[usable["forecast_week"].isin(test_weeks)]


def fit(train: pd.DataFrame, val: pd.DataFrame) -> xgb.XGBRegressor | None:
    """Pick the tree count by early stopping on `val`, then refit on train + val.

    Rows are weighted by baseline so the ratio loss tracks absolute error in
    servings. Returns None when there is nothing to train on (baseline only).
    """
    features = select_features(pd.concat([train, val]))
    tr, va = _training_rows(train, features), _training_rows(val, features)
    params = _params(features)

    def weights(df):
        return df[BASELINE] / df[BASELINE].mean()

    n_trees = DEFAULT_TREES
    if not tr.empty and not va.empty:
        probe = xgb.XGBRegressor(**params, early_stopping_rounds=30)
        probe.fit(
            tr[features], tr[RATIO], sample_weight=weights(tr),
            eval_set=[(va[features], va[RATIO])], sample_weight_eval_set=[weights(va)], verbose=False,
        )
        n_trees = max(int(probe.best_iteration) + 1, MIN_TREES)

    full = pd.concat([tr, va])
    if full.empty:
        return None
    model = xgb.XGBRegressor(**{**params, "n_estimators": n_trees})
    model.fit(full[features], full[RATIO], sample_weight=weights(full), verbose=False)
    return model


def predict_qty(model: xgb.XGBRegressor | None, df: pd.DataFrame, weight: float = ENSEMBLE_WEIGHT) -> pd.Series:
    """Dish quantity forecast: baseline x (1 + weight x (model ratio - 1)).

    weight=1 is the pure model, model=None the baseline (ratio fixed at 1).
    """
    ratio = pd.Series(1.0, index=df.index)
    if model is not None:
        positive = df[BASELINE] > 0
        if positive.any():
            raw = np.clip(model.predict(df.loc[positive, model_features(model)]), *RATIO_CLIP)
            ratio[positive] = 1.0 + weight * (raw - 1.0)
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


def metrics(actual: pd.Series, predicted: pd.Series) -> dict:
    err = (actual - predicted).abs()
    return {"mae": round(float(err.mean()), 4), "wape": round(float(err.sum() / actual.abs().sum()), 4)}


def forecast_weeks(model: xgb.XGBRegressor | None, frames: dict, n_weeks: int, lifts: dict | None) -> list[pd.DataFrame]:
    """Dish-day forecasts for the n_weeks after the last sales week, one frame per week.

    Each week is forecast from the one before it (recursive): the predicted week
    is appended to the sales history before building the next week's features.
    Columns: date, menu_item_id, forecast_week, baseline_qty, pred_normal,
    event_multiplier, event_source, pred. With `lifts` the explicit event lift is
    applied, unless the model already learned events itself.
    """
    sales = frames["sales"].copy()
    sales["date"] = pd.to_datetime(sales["date"]).dt.normalize()
    last_price = (
        sales.sort_values("date").groupby("menu_item_id")["avg_price"].last()
        if "avg_price" in sales.columns else None
    )
    apply_events = lifts is not None and not uses_event_features(model)
    weeks = []
    for _ in range(n_weeks):
        matrix = build_dish_matrix(frames["restaurant_id"], sales, frames["events"], include_next_week=True)
        last_observed = matrix.loc[matrix[QTY].notna(), "forecast_week"].max()
        future = matrix[matrix["forecast_week"] > last_observed].copy()
        future["pred_normal"] = predict_qty(model, future)
        if apply_events:
            future["event_multiplier"], future["event_source"] = multipliers(future, lifts)
        else:
            future["event_multiplier"], future["event_source"] = 1.0, ""
        future["pred"] = future["pred_normal"] * future["event_multiplier"]
        weeks.append(future.reset_index(drop=True))

        rolled = future[["date", "menu_item_id"]].assign(qty_sold=future["pred"].fillna(0.0).values)
        if last_price is not None:
            rolled["avg_price"] = rolled["menu_item_id"].map(last_price).values
        sales = pd.concat([sales, rolled], ignore_index=True)
    return weeks


def forecast_next_week(
    model: xgb.XGBRegressor | None, frames: dict, recipes: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Ingredient usage forecast for the week after the last sales week (no event lift)."""
    future = forecast_weeks(model, frames, 1, lifts=None)[0]
    usage = to_ingredient_usage(future, "pred", recipes if recipes is not None else frames["recipes"])
    out = usage.reset_index().rename(columns={"usage": "predicted_usage"})
    out = out.merge(frames["ingredients"][["ingredient_id", "name", "unit"]], on="ingredient_id", how="left")
    return out.round(2)


def evaluate(model: xgb.XGBRegressor, matrix: pd.DataFrame, test: pd.DataFrame, recipes: pd.DataFrame) -> pd.DataFrame:
    test = test[~test[CENSORED]]
    test = test.assign(pred=predict_qty(model, test), base=predict_qty(None, test))
    truth = to_ingredient_usage(test, QTY, recipes)
    rows = {
        "xgboost_dish_ratio": to_ingredient_usage(test, "pred", recipes),
        "dish_baseline_only": to_ingredient_usage(test, "base", recipes),
    }
    table = pd.DataFrame({name: metrics(truth, pred.reindex(truth.index)) for name, pred in rows.items()}).T
    dish = {
        "xgboost_dish_ratio": metrics(test[QTY], test["pred"]),
        "dish_baseline_only": metrics(test[QTY], test["base"]),
    }
    print("\nDish-day metrics (servings, test weeks, stockout days excluded):")
    print(pd.DataFrame(dish).T.to_string())
    return table


async def main(restaurant_id: str) -> None:
    from app import db
    from sim.dataset import load_frames

    await db.connect()
    try:
        frames = await load_frames(restaurant_id)
    finally:
        await db.disconnect()

    matrix = build_dish_matrix(frames["restaurant_id"], frames["sales"], frames["events"])
    train, val, test = split_by_week(matrix)
    print(f"dish-day rows: train={len(train)} val={len(val)} test={len(test)}")

    model = fit(train, val)
    print(f"features: {model_features(model)}  trees: {model.n_estimators}")

    print("\nIngredient-week metrics (test weeks):")
    print(evaluate(model, matrix, test, recipe_versions_of(frames)).to_string())

    importance = pd.Series(model.feature_importances_, index=model_features(model)).sort_values(ascending=False)
    print("\nTop features:")
    print(importance.head(10).round(4).to_string())

    MODEL_DIR.mkdir(exist_ok=True)
    path = MODEL_DIR / "dish_ratio_xgb.json"
    model.save_model(path)
    print(f"\nsaved {path} (inspection only, the API always retrains)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--restaurant-id", required=True, help="restaurants.id (UUID)")
    asyncio.run(main(parser.parse_args().restaurant_id))
