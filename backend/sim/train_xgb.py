"""Train the next-week ingredient usage XGBoost model.

Usage (from backend/): python -m sim.train_xgb --restaurant-id "<restaurants.id>"

Chronological split by forecast week: last 2 weeks test, the 2 before that
validation (early stopping), everything earlier train. Compared against two
naive baselines so we can see whether the model earns its keep on thin data.
"""
import argparse
import asyncio
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

from app import db
from sim.dataset import load_frames
from sim.features import FEATURE_COLUMNS, TARGET, build_feature_matrix

MODEL_DIR = Path(__file__).resolve().parent.parent / "models"
TEST_WEEKS = 2
VAL_WEEKS = 2
SEED = 42

PARAMS = dict(
    n_estimators=300,
    learning_rate=0.05,
    max_depth=3,
    min_child_weight=3,
    subsample=0.8,
    colsample_bytree=0.8,
    reg_lambda=5.0,
    objective="reg:squarederror",
    early_stopping_rounds=20,
    random_state=SEED,
)


def split_by_week(matrix: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    usable = matrix[matrix["usage_lag_1w"].notna() & matrix[TARGET].notna()]
    weeks = sorted(usable["forecast_week"].unique())
    if len(weeks) <= TEST_WEEKS + VAL_WEEKS:
        raise ValueError(f"Need more than {TEST_WEEKS + VAL_WEEKS} usable weeks, have {len(weeks)}")
    test_weeks = weeks[-TEST_WEEKS:]
    val_weeks = weeks[-(TEST_WEEKS + VAL_WEEKS):-TEST_WEEKS]
    train = usable[usable["forecast_week"] < val_weeks[0]]
    val = usable[usable["forecast_week"].isin(val_weeks)]
    test = usable[usable["forecast_week"].isin(test_weeks)]
    return train, val, test


def metrics(actual: pd.Series, predicted: pd.Series) -> dict:
    err = (actual - predicted).abs()
    return {"mae": round(float(err.mean()), 4), "wape": round(float(err.sum() / actual.abs().sum()), 4)}


def report(test: pd.DataFrame, model_pred: np.ndarray) -> pd.DataFrame:
    y = test[TARGET]
    rows = {
        "xgboost": metrics(y, pd.Series(model_pred, index=y.index)),
        "naive_last_week": metrics(y, test["usage_lag_1w"]),
        "mean_4w": metrics(y, test["usage_mean_4w"].fillna(test["usage_lag_1w"])),
    }
    return pd.DataFrame(rows).T


async def main(restaurant_id: str) -> None:
    await db.connect()
    try:
        frames = await load_frames(restaurant_id)
    finally:
        await db.disconnect()

    matrix = build_feature_matrix(**frames)
    train, val, test = split_by_week(matrix)
    print(f"rows: train={len(train)} val={len(val)} test={len(test)}  features={len(FEATURE_COLUMNS)}")

    model = xgb.XGBRegressor(**PARAMS)
    model.fit(train[FEATURE_COLUMNS], train[TARGET], eval_set=[(val[FEATURE_COLUMNS], val[TARGET])], verbose=False)

    print("\nTest metrics (last 2 weeks):")
    print(report(test, model.predict(test[FEATURE_COLUMNS])).to_string())

    importance = pd.Series(model.feature_importances_, index=FEATURE_COLUMNS).sort_values(ascending=False)
    print("\nTop features:")
    print(importance.head(10).round(4).to_string())

    MODEL_DIR.mkdir(exist_ok=True)
    path = MODEL_DIR / "usage_xgb.json"
    model.save_model(path)
    print(f"\nsaved {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--restaurant-id", required=True, help="restaurants.id (UUID)")
    asyncio.run(main(parser.parse_args().restaurant_id))
