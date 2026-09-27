import numpy as np
import pandas as pd
import pytest

from sim.dish_features import build_dish_matrix
from sim.forecast_backtest import (
    apply_bands,
    conformal_quantile,
    coverage,
    expanding_bands,
    ratio_quantiles,
    relative_errors,
    rolling_backtest,
)

WEEKS = 10
DAYS = pd.date_range("2026-06-29", periods=7 * WEEKS, freq="D")
RECIPES = pd.DataFrame(
    [("burger", "beef", 0.2), ("wrap", "beef", 0.1), ("burger", "bun", 1.0)],
    columns=["menu_item_id", "ingredient_id", "qty_per_serving"],
)


def make_sales(mult_from=None):
    rng = np.random.default_rng(0)
    rows = []
    for day in DAYS:
        for dish, base in (("burger", 20), ("wrap", 10)):
            q = round(base * (1 + 0.1 * day.weekday()) * rng.uniform(0.9, 1.1))
            if mult_from is not None and day >= mult_from:
                q *= 7
            rows.append((day, dish, q, 12.0))
    return pd.DataFrame(rows, columns=["date", "menu_item_id", "qty_sold", "avg_price"])


def synthetic_bt():
    weeks = pd.date_range("2026-08-03", periods=4, freq="7D")
    rows = []
    for k, w in enumerate(weeks):
        for ing in ("a", "b", "c"):
            rows.append((w, ing, 100.0 * (1 + 0.1 * k), 100.0))
    return pd.DataFrame(rows, columns=["forecast_week", "ingredient_id", "actual", "xgboost"])


def test_ratio_quantiles_and_bands():
    ratios = pd.Series(np.linspace(0.8, 1.2, 101))
    q = ratio_quantiles(ratios)
    # n=101: corrected ranks are floor(10.2)=10, ceil(51)=51, ceil(91.8)=92
    assert q[0.1] == pytest.approx(0.836) and q[0.5] == pytest.approx(1.0) and q[0.9] == pytest.approx(1.164)
    bands = apply_bands(pd.Series({"x": 50.0}), q)
    assert bands.loc["x", "p10"] == pytest.approx(41.8) and bands.loc["x", "p90"] == pytest.approx(58.2)


def test_conformal_quantile_widens_for_small_samples():
    values = pd.Series([0.9, 1.0, 1.1, 1.2, 1.3])
    # n=5: rank ceil(6 * 0.9)=6 exceeds n so it falls back to the max, floor(6 * 0.1)=0 falls back to the min
    assert conformal_quantile(values, 0.9) == 1.3
    assert conformal_quantile(values, 0.1) == 0.9
    assert values.quantile(0.9) < 1.3  # the plain quantile would be narrower


def test_relative_errors_skip_nonpositive_predictions():
    bt = pd.DataFrame({"actual": [10.0, 5.0], "xgboost": [20.0, 0.0]})
    assert list(relative_errors(bt)) == [0.5]


def test_expanding_bands_only_use_earlier_origins():
    bt = synthetic_bt()
    banded = expanding_bands(bt, min_errors=3)
    first = banded[banded.forecast_week == bt.forecast_week.unique()[1]]
    # Only week 0 errors (ratio 1.0) exist before week 1, so every band collapses to 1.0
    assert (first["p10"] == 100.0).all() and (first["p90"] == 100.0).all()
    assert bt.forecast_week.unique()[0] not in set(banded.forecast_week)


def test_coverage_counts():
    banded = pd.DataFrame(
        {"actual": [5.0, 15.0, 25.0, 12.0], "p10": [10.0] * 4, "p90": [20.0] * 4}
    )
    c = coverage(banded)
    assert c["inside_p10_p90"] == 0.5 and c["below_p10"] == 0.25 and c["above_p90"] == 0.25 and c["n"] == 4


def test_rolling_backtest_shape_and_origins():
    bt = rolling_backtest(build_dish_matrix("r1", make_sales()), RECIPES)
    # usable weeks 1..9; origins start after 3 train + 2 val weeks, so weeks 6..9 (4 origins) x 2 ingredients
    assert bt.forecast_week.nunique() == 4 and len(bt) == 8
    assert bt[["actual", "xgboost", "dish_baseline", "naive_last_week", "mean_4w"]].notna().all().all()


def test_rolling_backtest_has_no_leakage():
    """Changing sales dated in the last origin week or later must not change any prediction."""
    last_week_start = DAYS[(WEEKS - 1) * 7]
    base = rolling_backtest(build_dish_matrix("r1", make_sales()), RECIPES)
    mutated = rolling_backtest(build_dish_matrix("r1", make_sales(mult_from=last_week_start)), RECIPES)
    cols = ["xgboost", "dish_baseline", "naive_last_week", "mean_4w"]
    pd.testing.assert_frame_equal(base[cols], mutated[cols])
    assert (base["actual"].iloc[-2:].values != mutated["actual"].iloc[-2:].values).all()
