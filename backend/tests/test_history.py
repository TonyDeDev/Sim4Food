from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pytest

from sim import history
from sim.features import FEATURE_COLUMNS, TARGET, build_feature_matrix
from sim.train_dish_xgb import to_ingredient_usage
from sim.waste import build_waste_report

MONDAYS = pd.date_range("2026-06-29", periods=10, freq="7D")
START, END = history.OPEN_START, history.OPEN_END

# Current values (what the plain ingredients / recipes frames hold).
RECIPES = pd.DataFrame(
    [("burger", "beef", 0.3), ("burger", "bun", 1.0)],
    columns=["menu_item_id", "ingredient_id", "qty_per_serving"],
)
INGREDIENTS = pd.DataFrame(
    {"ingredient_id": ["beef", "bun"], "unit_cost": [12.0, 0.5], "pack_size": [5.0, 24.0], "shelf_life_days": [3.0, np.nan]}
)
# Beef recipe was 0.2 until Monday of week 5, then 0.3 (current). Bun never changed.
RECIPE_VERSIONS = pd.DataFrame(
    [
        ("burger", "beef", 0.2, START, MONDAYS[5]),
        ("burger", "beef", 0.3, MONDAYS[5], END),
        ("burger", "bun", 1.0, START, END),
    ],
    columns=history.RECIPE_VERSION_COLUMNS,
)
# Beef cost was 10.0, raised to 12.0 (current) from Monday of week 6. Bun never changed.
INGREDIENT_VERSIONS = pd.DataFrame(
    [
        ("beef", 10.0, 5.0, 3.0, START, MONDAYS[6]),
        ("beef", 12.0, 5.0, 3.0, MONDAYS[6], END),
        ("bun", 0.5, 24.0, np.nan, START, END),
    ],
    columns=history.INGREDIENT_VERSION_COLUMNS,
)


def make_sales():
    rows = [(m + pd.Timedelta(days=1), "burger", 10) for m in MONDAYS]
    return pd.DataFrame(rows, columns=["date", "menu_item_id", "qty_sold"])


def build(**kw):
    return build_feature_matrix(
        "r1",
        make_sales(),
        RECIPES,
        INGREDIENTS,
        include_next_week=kw.get("include_next_week", False),
        ingredient_versions=kw.get("ingredient_versions"),
        recipe_versions=kw.get("recipe_versions"),
    )


def row(m, ing, week_idx):
    return m[(m.ingredient_id == ing) & (m.forecast_week == MONDAYS[week_idx])].iloc[0]


def test_database_rows_become_version_frames():
    rows = [
        {"menu_item_id": "burger", "ingredient_id": "beef", "qty_per_serving": 0.2,
         "valid_from": datetime(1900, 1, 1, tzinfo=timezone.utc), "valid_to": datetime(2026, 8, 3, tzinfo=timezone.utc)},
        {"menu_item_id": "burger", "ingredient_id": "beef", "qty_per_serving": 0.3,
         "valid_from": datetime(2026, 8, 3, tzinfo=timezone.utc), "valid_to": None},
    ]
    v = history.to_recipe_versions(rows)
    assert v.valid_from.iloc[0] == history.OPEN_START
    assert v.valid_to.iloc[0] == pd.Timestamp("2026-08-03") and v.valid_to.iloc[1] == history.OPEN_END


def test_past_usage_is_not_rewritten_by_a_recipe_change():
    m = build(recipe_versions=RECIPE_VERSIONS)
    assert row(m, "beef", 4)[TARGET] == pytest.approx(10 * 0.2)  # before the change
    assert row(m, "beef", 5)[TARGET] == pytest.approx(10 * 0.3)  # from the change on
    # Without the history the current recipe is applied to every week (the old behaviour).
    assert row(build(), "beef", 4)[TARGET] == pytest.approx(10 * 0.3)


def test_dish_model_usage_uses_recipe_in_force():
    df = pd.DataFrame(
        {
            "date": [MONDAYS[4], MONDAYS[5]],
            "forecast_week": [MONDAYS[4], MONDAYS[5]],
            "menu_item_id": "burger",
            "qty": [10.0, 10.0],
        }
    )
    usage = to_ingredient_usage(df, "qty", RECIPE_VERSIONS)
    assert usage[(MONDAYS[4], "beef")] == pytest.approx(2.0)
    assert usage[(MONDAYS[5], "beef")] == pytest.approx(3.0)


def test_spec_features_follow_the_history():
    m = build(ingredient_versions=INGREDIENT_VERSIONS, recipe_versions=RECIPE_VERSIONS)
    assert row(m, "beef", 5).unit_cost == 10.0
    assert row(m, "beef", 6).unit_cost == 12.0
    assert row(m, "beef", 6).unit_cost_change_pct_4w == pytest.approx(0.2)
    assert row(m, "beef", 6).days_since_price_change == 0
    assert row(m, "beef", 7).days_since_price_change == 7
    assert row(m, "beef", 7).price_changed_recent_flag == 1
    assert row(m, "beef", 9).price_changed_recent_flag == 0  # 21 days on
    assert np.isnan(row(m, "beef", 5).days_since_price_change)
    assert row(m, "beef", 5).unit_cost_change_pct_4w == 0.0
    # bun has no history
    assert (m[m.ingredient_id == "bun"].unit_cost == 0.5).all()
    assert m[m.ingredient_id == "bun"].days_since_price_change.isna().all()

    assert row(m, "beef", 4).recipe_qty_per_dish_sum == pytest.approx(0.2)
    assert row(m, "beef", 5).recipe_qty_per_dish_sum == pytest.approx(0.3)
    assert row(m, "beef", 5).recipe_change_flag_4w == 1
    assert row(m, "beef", 9).recipe_change_flag_4w == 1  # exactly 28 days on is still flagged
    assert row(m, "beef", 9).days_since_recipe_change == 28
    assert row(m, "bun", 5).recipe_change_flag_4w == 0


def test_a_removed_line_stops_using_the_ingredient_and_counts_as_a_change():
    versions = pd.DataFrame(
        [("burger", "beef", 0.3, START, MONDAYS[3]), ("burger", "bun", 1.0, START, END)],
        columns=history.RECIPE_VERSION_COLUMNS,
    )
    m = build(recipe_versions=versions)
    assert row(m, "beef", 2)[TARGET] == pytest.approx(3.0)
    assert row(m, "beef", 3)[TARGET] == 0
    assert row(m, "beef", 4).days_since_recipe_change == 7


def test_no_history_gives_constant_spec_features():
    m = build()
    assert (m[m.ingredient_id == "beef"].unit_cost == 12.0).all()
    assert (m.price_changed_recent_flag == 0).all() and (m.recipe_change_flag_4w == 0).all()
    assert (m.unit_cost_change_pct_4w == 0).all()


@pytest.mark.parametrize("week_idx", [3, 6, 8])
def test_changes_after_the_week_do_not_leak_into_its_features(week_idx):
    """A change effective after week W starts must not alter row W's features."""
    later = MONDAYS[week_idx] + pd.Timedelta(days=1)
    base = build()
    price = pd.DataFrame(
        [
            ("beef", 12.0, 5.0, 3.0, START, later),
            ("beef", 99.0, 5.0, 3.0, later, END),
            ("bun", 0.5, 24.0, np.nan, START, END),
        ],
        columns=history.INGREDIENT_VERSION_COLUMNS,
    )
    recipe = pd.DataFrame(
        [
            ("burger", "beef", 0.3, START, later),
            ("burger", "beef", 0.9, later, END),
            ("burger", "bun", 1.0, START, END),
        ],
        columns=history.RECIPE_VERSION_COLUMNS,
    )
    mutated = build(ingredient_versions=price, recipe_versions=recipe)
    a, b = row(base, "beef", week_idx), row(mutated, "beef", week_idx)
    pd.testing.assert_series_equal(a[FEATURE_COLUMNS].astype(float), b[FEATURE_COLUMNS].astype(float))
    if week_idx + 1 < len(MONDAYS):
        assert row(mutated, "beef", week_idx + 1).unit_cost == 99.0


def test_next_week_row_uses_current_values_even_if_the_change_is_dated_later():
    far = MONDAYS[9] + pd.Timedelta(days=400)
    future = pd.DataFrame(
        [
            ("beef", 10.0, 5.0, 3.0, START, far),
            ("beef", 12.0, 5.0, 3.0, far, END),
            ("bun", 0.5, 24.0, np.nan, START, END),
        ],
        columns=history.INGREDIENT_VERSION_COLUMNS,
    )
    m = build(ingredient_versions=future, include_next_week=True)
    nxt = m[(m.ingredient_id == "beef") & (m.forecast_week == MONDAYS[9] + pd.Timedelta(days=7))].iloc[0]
    assert nxt.unit_cost == 12.0
    assert nxt.unit_cost_change_pct_4w == pytest.approx(0.2)


def test_field_unset_before_first_value():
    v = pd.DataFrame(
        [("bun", 0.5, 24.0, np.nan, START, MONDAYS[2]), ("bun", 0.5, 24.0, 5.0, MONDAYS[2], END)],
        columns=history.INGREDIENT_VERSION_COLUMNS,
    )
    wide = history.asof_wide(
        history.field_versions(v, "shelf_life_days"), pd.DatetimeIndex([MONDAYS[1], MONDAYS[2]]), ["bun"]
    )
    assert np.isnan(wide.iloc[0, 0]) and wide.iloc[1, 0] == 5.0


def test_cost_changes_only_lists_real_price_changes():
    def t(d):
        return datetime(2026, 1, d, tzinfo=timezone.utc)

    first = datetime(1900, 1, 1, tzinfo=timezone.utc)
    rows = [
        {"ingredient_id": "a", "unit_cost": 1, "valid_from": first},
        {"ingredient_id": "a", "unit_cost": 2, "valid_from": t(10)},
        {"ingredient_id": "a", "unit_cost": 2, "valid_from": t(20)},  # a pack_size edit, same price
        {"ingredient_id": "b", "unit_cost": 5, "valid_from": first},
    ]
    assert history.cost_changes(rows) == [
        {"ingredient_id": "a", "old_value": 1.0, "new_value": 2.0, "effective_at": t(10)}
    ]


def test_consumption_uses_the_recipe_line_in_force_on_the_sale_date():
    def at(d):
        return datetime(2026, 7, d, tzinfo=timezone.utc)

    recipe_rows = [
        {"menu_item_id": "m1", "ingredient_id": "i1", "qty_per_serving": 0.2,
         "valid_from": datetime(1900, 1, 1, tzinfo=timezone.utc), "valid_to": at(6)},
        {"menu_item_id": "m1", "ingredient_id": "i1", "qty_per_serving": 0.3, "valid_from": at(6), "valid_to": None},
    ]
    sales = [
        {"menu_item_id": "m1", "date": date(2026, 7, 1), "qty_sold": 10.0},
        {"menu_item_id": "m1", "date": date(2026, 7, 8), "qty_sold": 10.0},
    ]
    out = history.consumption_rows([{"id": "i1"}], sales, recipe_rows)
    assert [round(r["qty"], 6) for r in out] == [2.0, 3.0]


def test_value_at():
    def t(d):
        return datetime(2026, 1, d, tzinfo=timezone.utc)

    log = [(t(10), 1.0, 2.0), (t(20), 2.0, 3.0)]
    assert history.value_at(3.0, log, t(5)) == 1.0
    assert history.value_at(3.0, log, t(10)) == 2.0
    assert history.value_at(3.0, log, t(25)) == 3.0
    assert history.value_at(7.0, [], t(1)) == 7.0


def waste_report(cost_changes):
    ingredients = [{"id": "i1", "external_id": "beef", "name": "Beef", "unit_cost": 12.0}]
    purchases = [
        {"ingredient_id": "i1", "date": date(2026, 7, 1), "qty": 10.0},
        {"ingredient_id": "i1", "date": date(2026, 7, 8), "qty": 10.0},
    ]
    consumption = [
        {"ingredient_id": "i1", "date": date(2026, 7, 1), "qty": 4.0},
        {"ingredient_id": "i1", "date": date(2026, 7, 8), "qty": 4.0},
    ]
    return build_waste_report(ingredients, purchases, [], consumption, cost_changes)["by_ingredient"][0]["weeks"]


def test_waste_cost_prices_each_week_at_the_cost_then():
    changes = [
        {"ingredient_id": "i1", "old_value": 10.0, "new_value": 12.0, "effective_at": datetime(2026, 7, 6, tzinfo=timezone.utc)}
    ]
    weeks = waste_report(changes)
    assert [w["waste_qty"] for w in weeks] == [6.0, 6.0]
    assert weeks[0]["waste_cost"] == 60.0  # week of 2026-06-29, cost was 10
    assert weeks[1]["waste_cost"] == 72.0  # week of 2026-07-06, cost is 12


def test_waste_cost_without_history_uses_current_cost():
    assert [w["waste_cost"] for w in waste_report(None)] == [72.0, 72.0]
