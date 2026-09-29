import numpy as np
import pandas as pd
import pytest

from sim import recommend, uncertainty
from sim.dish_features import BASELINE, CENSORED, EVENT_DAY, QTY, RATIO, build_dish_matrix
from sim.events_adjust import estimate_lifts, multipliers
from sim.train_dish_xgb import (
    DEFAULT_TREES,
    fit,
    forecast_weeks,
    model_features,
    predict_qty,
    select_features,
    usable_rows,
)

DAYS = pd.date_range("2026-06-29", periods=7 * 8, freq="D")  # 8 full weeks, Monday start


def sales(sunday_sellout=False, launch=None, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for day in DAYS:
        for dish, base in (("burger", 20), ("fish", 12), ("wrap", 8)):
            if launch and dish == "wrap" and day < launch:
                continue
            q = round(base * (1 + 0.1 * day.weekday()) * rng.uniform(0.9, 1.1))
            if sunday_sellout and dish == "fish" and day.weekday() == 6:
                q = 0
            rows.append((day, dish, q, 12.0))
    return pd.DataFrame(rows, columns=["date", "menu_item_id", "qty_sold", "avg_price"])


def row(m, dish, day):
    return m[(m.menu_item_id == dish) & (m.date == day)].iloc[0]


# --- dish_features ---------------------------------------------------------

def test_sold_out_days_are_censored_and_the_baseline_estimates_demand():
    m = build_dish_matrix("r1", sales(sunday_sellout=True))
    sunday = DAYS[7 * 6 + 6]
    r = row(m, "fish", sunday)
    assert r[CENSORED] and r[QTY] == 0 and np.isnan(r[RATIO])
    # Every earlier Sunday sold out too, yet the fallback baseline is a real demand estimate.
    assert r[BASELINE] > 5
    assert not row(m, "burger", sunday)[CENSORED]


def test_a_closed_day_is_not_a_stockout():
    s = sales()
    closed = DAYS[7 * 5 + 2]
    s.loc[s.date == closed, "qty_sold"] = 0
    m = build_dish_matrix("r1", s)
    assert not m[m.date == closed][CENSORED].any()


def test_days_before_a_dish_launches_are_unknown_not_zero():
    launch = DAYS[21]
    m = build_dish_matrix("r1", sales(launch=launch))
    before = m[(m.menu_item_id == "wrap") & (m.date < launch)]
    assert before[QTY].isna().all() and not before[CENSORED].any()


def test_event_days_do_not_inflate_the_normal_baseline():
    s = sales()
    deal_day = DAYS[7 * 5 + 4]
    s.loc[(s.date == deal_day) & (s.menu_item_id == "wrap"), "qty_sold"] *= 5
    events = pd.DataFrame(
        [("deal", deal_day, deal_day, ["wrap"], 0.2, np.nan)],
        columns=["type", "start_date", "end_date", "items", "discount_pct", "expected_lift"],
    )
    with_event = build_dish_matrix("r1", s, events)
    later = deal_day + pd.Timedelta(days=7)
    assert row(with_event, "wrap", deal_day)[EVENT_DAY]
    # The deal day is left out: the baseline is the mean of the other three same weekdays.
    others = [row(with_event, "wrap", later - pd.Timedelta(days=7 * k))[QTY] for k in (2, 3, 4)]
    assert row(with_event, "wrap", later)[BASELINE] == pytest.approx(np.mean(others))


# --- training --------------------------------------------------------------

def test_select_features_drops_events_and_season_on_thin_data():
    m = build_dish_matrix("r1", sales())
    features = select_features(usable_rows(m))
    assert "dish_event_flag" not in features and "week_of_year" not in features
    assert "dow" in features


def test_fit_refits_on_train_and_validation():
    u = usable_rows(build_dish_matrix("r1", sales()))
    weeks = sorted(u.forecast_week.unique())
    train, val = u[u.forecast_week < weeks[-2]], u[u.forecast_week >= weeks[-2]]
    model = fit(train, val)
    trained_rows = model.get_booster().num_boosted_rounds()
    assert trained_rows == model.n_estimators and model.n_estimators <= 400
    assert set(model_features(model)) == set(select_features(pd.concat([train, val])))
    assert fit(train, val.iloc[0:0]).n_estimators == DEFAULT_TREES


def test_prediction_is_a_blend_of_model_and_baseline():
    u = usable_rows(build_dish_matrix("r1", sales()))
    weeks = sorted(u.forecast_week.unique())
    model = fit(u[u.forecast_week < weeks[-2]], u[u.forecast_week >= weeks[-2]])
    rows = u[u.forecast_week == weeks[-1]]
    pure, blend, base = predict_qty(model, rows, 1.0), predict_qty(model, rows), predict_qty(None, rows)
    assert np.allclose(blend, (pure + base) / 2)


def test_recursive_forecast_covers_consecutive_weeks():
    frames = {"restaurant_id": "r1", "sales": sales(), "events": None}
    weeks = forecast_weeks(None, frames, 3, lifts=None)
    starts = [w["forecast_week"].iloc[0] for w in weeks]
    assert starts == [DAYS[-1] + pd.Timedelta(days=1 + 7 * k) for k in range(3)]
    assert all(len(w) == 7 * 3 for w in weeks) and all(w["pred"].notna().all() for w in weeks)


# --- event lift ------------------------------------------------------------

def test_lift_is_estimated_from_history_and_shrunk():
    s = sales()
    deal_days = [DAYS[7 * 5 + 4], DAYS[7 * 5 + 5]]
    s.loc[s.date.isin(deal_days) & (s.menu_item_id == "wrap"), "qty_sold"] *= 2
    events = pd.DataFrame(
        [("deal", deal_days[0], deal_days[-1], ["wrap"], 0.2, np.nan)],
        columns=["type", "start_date", "end_date", "items", "discount_pct", "expected_lift"],
    )
    m = build_dish_matrix("r1", s, events)
    lifts = estimate_lifts(m)
    assert lifts["deal"]["days"] == 2 and lifts["holiday"]["days"] == 0
    assert 1.0 < lifts["deal"]["lift"] < 2.0  # about 2x observed, shrunk toward 1 with only 2 days

    future = m[(m.date.isin(deal_days)) & (m.menu_item_id == "wrap")].copy()
    future["event_discount_pct"] = 0.4  # twice the historical discount
    mult, source = multipliers(future, lifts)
    assert (source == "history").all()
    assert mult.iloc[0] == pytest.approx(1 + (lifts["deal"]["lift"] - 1) * 2)


def test_owner_expected_lift_wins():
    m = build_dish_matrix("r1", sales()).head(3).copy()
    m[EVENT_DAY] = True
    m["event_expected_lift"] = 0.3
    mult, source = multipliers(m, {"deal": {"lift": 5.0, "days": 10, "discount": 0.2}})
    assert (mult == 1.3).all() and (source == "owner").all()


# --- uncertainty -----------------------------------------------------------

def dish_bt(weeks=6, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for w in pd.date_range("2026-07-06", periods=weeks, freq="7D"):
        week_effect = rng.normal(0, 0.1)
        for dish in ("burger", "wrap"):
            for d in range(7):
                pred = 20.0 if dish == "burger" else 10.0
                actual = pred * np.exp(week_effect + rng.normal(0, 0.05))
                rows.append((w, w + pd.Timedelta(days=d), dish, actual, pred, False))
    return pd.DataFrame(rows, columns=["forecast_week", "date", "menu_item_id", QTY, "xgboost", CENSORED])


RECIPES = pd.DataFrame(
    [("burger", "beef", 0.2), ("wrap", "beef", 0.1), ("burger", "bun", 1.0)],
    columns=["menu_item_id", "ingredient_id", "qty_per_serving"],
)


def test_samples_are_reproducible_and_quantiles_ordered():
    bt = dish_bt()
    totals = pd.Series({"burger": 140.0, "wrap": 70.0})
    a, scale = uncertainty.forecast_samples(bt, RECIPES, totals)
    b, _ = uncertainty.forecast_samples(bt, RECIPES, totals)
    pd.testing.assert_frame_equal(a, b)
    q = a.quantile([0.1, 0.5, 0.9])
    assert (q.loc[0.1] <= q.loc[0.5]).all() and (q.loc[0.5] <= q.loc[0.9]).all()
    assert uncertainty.SCALE_GRID.min() <= scale <= uncertainty.SCALE_GRID.max()


def test_week_effect_moves_ingredients_that_share_dishes_together():
    samples, _ = uncertainty.forecast_samples(dish_bt(), RECIPES, pd.Series({"burger": 140.0, "wrap": 70.0}))
    assert samples["beef"].corr(samples["bun"]) > 0.5


def test_horizon_widens_the_band():
    bt = dish_bt()
    totals = pd.Series({"burger": 140.0, "wrap": 70.0})
    one, _ = uncertainty.forecast_samples(bt, RECIPES, totals, horizon_weeks=1)
    three, _ = uncertainty.forecast_samples(bt, RECIPES, totals, horizon_weeks=3)
    width = lambda s: s["beef"].quantile(0.9) - s["beef"].quantile(0.1)
    assert width(three) > width(one)


def test_scored_bands_use_only_earlier_weeks():
    evals = uncertainty.expanding_evaluations(dish_bt(), RECIPES)
    assert len(evals) == 6 - uncertainty.MIN_PRIOR_WEEKS
    banded, metrics = uncertainty.score_bands(evals)
    assert metrics["n"] == len(banded) and 0 <= metrics["inside_p10_p90"] <= 1


# --- recommendations -------------------------------------------------------

def test_pack_rounding():
    assert recommend.ceil_to_pack(11.0, 5.0) == 15.0
    assert recommend.ceil_to_pack(10.0, 5.0) == 10.0
    assert recommend.ceil_to_pack(-3.0, 5.0) == 0.0
    assert recommend.ceil_to_pack(2.5, np.nan) == 2.5


def test_delivery_days_and_cycles():
    p = pd.DataFrame({"date": pd.to_datetime(["2026-07-06", "2026-07-09", "2026-07-13", "2026-07-16", "2026-07-15"])})
    assert recommend.delivery_days(p.head(4)) == [0, 3]
    assert recommend.delivery_days(None) == [0]
    cyc = recommend.cycle_of(pd.Series(range(7)), [0, 3])
    assert list(cyc) == [0, 0, 0, 1, 1, 1, 1]


def test_newsvendor_service_level_follows_costs():
    recipe = pd.DataFrame({"beef": [0.2, 0.1], "bun": [1.0, 0.0]}, index=["burger", "wrap"])
    ingredients = pd.DataFrame({
        "ingredient_id": ["beef", "bun"], "unit_cost": [10.0, 0.5], "pack_size": [5.0, 12.0], "shelf_life_days": [4, 30],
    })
    menu = pd.DataFrame({"menu_item_id": ["burger", "wrap"], "price": [15.0, 12.0]})
    costs = recommend.unit_costs(ingredients, recipe, menu, pd.Series({"burger": 100.0, "wrap": 50.0}))
    # beef: perishable, Co = 10; burger margin 15 - 2.5 = 12.5 per serving -> 62.5/kg, wrap 11/0.1 = 110/kg
    cu = 0.5 * np.average([62.5, 110.0], weights=[20.0, 5.0])
    assert costs.loc["beef", "cu"] == pytest.approx(cu)
    assert costs.loc["beef", "q_star"] == pytest.approx(cu / (cu + 10.0))
    assert not costs.loc["bun", "perishable"] and costs.loc["bun", "co"] == pytest.approx(0.05)
    assert costs.loc["bun", "q_star"] == 0.95  # clipped


def test_shared_lost_margin_is_not_counted_once_per_recipe_line():
    """A burger short is one lost burger, not one per ingredient in it."""
    recipe = pd.DataFrame({"beef": [0.2], "bun": [1.0], "cheese": [0.05]}, index=["burger"])
    ingredients = pd.DataFrame({
        "ingredient_id": ["beef", "bun", "cheese"], "unit_cost": [10.0, 0.5, 12.0],
        "pack_size": [5.0, 12.0, 1.0], "shelf_life_days": [4, 30, 30],
    })
    menu = pd.DataFrame({"menu_item_id": ["burger"], "price": [15.0]})
    totals = pd.Series({"burger": 100.0})
    costs = recommend.unit_costs(ingredients, recipe, menu, totals)

    # One serving short of each ingredient at once is still one lost burger.
    margin = 15.0 - (0.2 * 10.0 + 1.0 * 0.5 + 0.05 * 12.0)
    servings_worth = sum(costs.loc[i, "cu_share"] * recipe.loc["burger", i] for i in recipe.columns)
    assert servings_worth == pytest.approx(recommend.LOST_SALE_SHARE * margin)
    # cu still prices the whole dish against each ingredient's own order.
    for i in recipe.columns:
        assert costs.loc[i, "cu"] == pytest.approx(costs.loc[i, "cu_share"] * len(recipe.columns))


def test_adaptive_policy_tops_up_after_a_busy_first_half():
    demand = np.array([[30.0, 40.0]])
    forecast = np.array([20.0, 20.0])
    need = np.array([22.0, 22.0])
    orders, end, short, out = recommend.adaptive_policy(0.0, demand, forecast, need, 1.0)
    assert orders[0, 0] == 22.0
    # First half ran 50% hot, half of that surprise is trusted: 22 x 1.25 = 27.5 -> 28 packs, stock was 0.
    assert orders[0, 1] == 28.0
    assert short[0] == pytest.approx(8.0 + 12.0) and out[0]


def test_order_backtest_compares_with_actual_purchases():
    costs = pd.DataFrame({"co": [1.0], "cu": [4.0], "cu_share": [2.0], "q_star": [0.8], "perishable": [True], "unit_cost": [1.0], "pack_size": [1.0]}, index=["beef"])
    week = {
        "week": pd.Timestamp("2026-08-03"),
        "on_hand": pd.Series({"beef": 0.0}),
        "purchased": pd.DataFrame({0: [30.0], 1: [30.0]}, index=["beef"]),
        "demand": pd.DataFrame({0: [20.0], 1: [20.0]}, index=["beef"]),
        "samples": pd.DataFrame({"beef": np.linspace(36, 44, 101)}),
        "shares": pd.DataFrame({0: [0.5], 1: [0.5]}, index=["beef"]),
    }
    result = recommend.order_backtest([week], costs)
    assert result["actual"]["waste_cost"] == 20.0  # bought 60, used 40
    assert result["ours"]["waste_cost"] < result["actual"]["waste_cost"]
    assert result["total_savings"] > 0
