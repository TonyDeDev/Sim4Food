import numpy as np
import pandas as pd
import pytest

from sim.features import FEATURE_COLUMNS, TARGET, build_feature_matrix

# Two dishes; beef is used by burger (0.2) and wrap (0.1), bun only by burger (1).
RECIPES = pd.DataFrame(
    [
        ("burger", "beef", 0.2),
        ("wrap", "beef", 0.1),
        ("burger", "bun", 1.0),
    ],
    columns=["menu_item_id", "ingredient_id", "qty_per_serving"],
)
INGREDIENTS = pd.DataFrame(
    {"ingredient_id": ["beef", "bun"], "unit_cost": [10.0, 0.5], "pack_size": [5.0, 24.0], "shelf_life_days": [3.0, np.nan]}
)
MONDAYS = pd.date_range("2026-06-29", periods=10, freq="7D")


def make_sales(burger=None, wrap=None):
    burger = burger or [10 * (i + 1) for i in range(10)]
    wrap = wrap or [5] * 10
    rows = []
    for monday, b, w in zip(MONDAYS, burger, wrap):
        rows.append((monday + pd.Timedelta(days=1), "burger", b))
        rows.append((monday + pd.Timedelta(days=3), "wrap", w))
    return pd.DataFrame(rows, columns=["date", "menu_item_id", "qty_sold"])


def make_purchases():
    return pd.DataFrame(
        {"date": MONDAYS + pd.Timedelta(days=2), "ingredient_id": "beef", "qty": [20.0] * 10}
    )


def make_counts():
    return pd.DataFrame(
        {"date": MONDAYS + pd.Timedelta(days=6), "ingredient_id": "beef", "qty_on_hand": [50.0 - i for i in range(10)]}
    )


def build(sales=None, **kw):
    return build_feature_matrix(
        "r1",
        sales if sales is not None else make_sales(),
        RECIPES,
        INGREDIENTS,
        kw.get("purchases", make_purchases()),
        kw.get("counts", make_counts()),
        kw.get("events"),
        include_next_week=kw.get("include_next_week", False),
    )


def row(m, ing, week_idx):
    return m[(m.ingredient_id == ing) & (m.forecast_week == MONDAYS[week_idx])].iloc[0]


def test_target_is_qty_sold_times_recipe_qty():
    m = build()
    # week 2: burger 30 -> beef 6.0, wrap 5 -> 0.5
    assert row(m, "beef", 2)[TARGET] == pytest.approx(30 * 0.2 + 5 * 0.1)
    assert row(m, "bun", 2)[TARGET] == pytest.approx(30.0)


def test_lags_and_rolling_are_shifted():
    m = build()
    usage = [(10 * (i + 1)) * 0.2 + 0.5 for i in range(10)]
    r = row(m, "beef", 5)
    assert r.usage_lag_1w == pytest.approx(usage[4])
    assert r.usage_lag_2w == pytest.approx(usage[3])
    assert r.usage_lag_4w == pytest.approx(usage[1])
    assert r.usage_mean_4w == pytest.approx(np.mean(usage[1:5]))
    assert r.usage_trend_4w == pytest.approx(2.0)  # +10 burgers/wk x 0.2
    assert np.isnan(r.usage_lag_8w)
    assert np.isnan(r.usage_lag_52w)


def test_first_week_has_no_history():
    r = row(build(), "beef", 0)
    assert np.isnan(r.usage_lag_1w) and np.isnan(r.usage_mean_4w)


def test_dish_features():
    r = row(build(), "beef", 3)
    burger, wrap = 30 * 0.2, 0.5
    assert r.dish_demand_contribution == pytest.approx(burger / (burger + wrap))
    assert r.number_of_dishes_using_ingredient == 2
    assert row(build(), "bun", 3).number_of_dishes_using_ingredient == 1
    assert r.total_restaurant_sales_lag_1w == pytest.approx(30 + 5)


def test_inventory_and_purchase_features():
    r = row(build(), "beef", 5)
    # cutoff = Sunday of week 4, counts land on Sundays
    assert r.current_qty_on_hand == 46.0
    assert r.inventory_lag_1w == 47.0
    assert r.days_since_last_purchase == 4  # purchase Wed, cutoff Sun
    assert r.purchase_qty_lag_1w == 20.0
    usage = [(10 * (i + 1)) * 0.2 + 0.5 for i in range(10)]
    assert r.purchase_to_usage_ratio_4w == pytest.approx(80 / sum(usage[1:5]))
    # count at end of wk0 is 50, at end of wk4 is 46
    assert r.inventory_variance_4w == pytest.approx(46.0 - (50.0 + 80 - sum(usage[1:5])))


def test_events_flags_and_ingredient_flag():
    events = pd.DataFrame(
        [
            ("deal", MONDAYS[4] + pd.Timedelta(days=4), MONDAYS[4] + pd.Timedelta(days=6), ["wrap"], 0.3),
            ("holiday", MONDAYS[6], MONDAYS[6], [], 0.2),
        ],
        columns=["type", "start_date", "end_date", "items", "expected_lift"],
    )
    m = build(events=events)
    assert row(m, "beef", 4).deal_flag == 1 and row(m, "beef", 4).ingredient_event_flag == 1
    assert row(m, "beef", 4).event_expected_lift == pytest.approx(0.3)
    assert row(m, "bun", 4).ingredient_event_flag == 0  # wrap does not use bun
    assert row(m, "bun", 6).holiday_flag == 1
    assert row(m, "bun", 3).holiday_flag == 0 and row(m, "bun", 3).deal_flag == 0


def test_optional_inputs_missing():
    m = build(purchases=pd.DataFrame(columns=["date", "ingredient_id", "qty"]), counts=pd.DataFrame(columns=["date", "ingredient_id", "qty_on_hand"]))
    assert m["current_qty_on_hand"].isna().all()
    assert m["purchase_qty_lag_1w"].isna().all()
    assert (m["holiday_flag"] == 0).all()


def test_include_next_week_row_has_nan_target():
    m = build(include_next_week=True)
    last = m[m.forecast_week == MONDAYS[9] + pd.Timedelta(days=7)]
    assert len(last) == 2 and last[TARGET].isna().all()
    assert last.usage_lag_1w.notna().all()


@pytest.mark.parametrize("week_idx", [3, 5, 8])
def test_no_leakage_from_current_or_future_data(week_idx):
    """Mutating any data dated in week W or later must not change features of row W."""
    cutoff = MONDAYS[week_idx]
    base = build()

    sales = make_sales()
    sales.loc[sales.date >= cutoff, "qty_sold"] *= 7
    purchases = make_purchases()
    purchases.loc[purchases.date >= cutoff, "qty"] *= 7
    counts = make_counts()
    counts.loc[counts.date >= cutoff, "qty_on_hand"] += 999
    mutated = build(sales=sales, purchases=purchases, counts=counts)

    for ing in ("beef", "bun"):
        a, b = row(base, ing, week_idx), row(mutated, ing, week_idx)
        pd.testing.assert_series_equal(a[FEATURE_COLUMNS].astype(float), b[FEATURE_COLUMNS].astype(float))
    assert row(base, "beef", week_idx)[TARGET] != row(mutated, "beef", week_idx)[TARGET]
