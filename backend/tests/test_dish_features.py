import numpy as np
import pandas as pd
import pytest

from sim.dish_features import BASELINE, DISH_FEATURES, QTY, RATIO, build_dish_matrix

DAYS = pd.date_range("2026-06-29", periods=42, freq="D")  # 6 full weeks, Monday start


def qty_for(day, dish):
    week = (day - DAYS[0]).days // 7
    if dish == "burger":
        return 10 + 2 * day.weekday() + week
    return 5


def make_sales(mult_from=None):
    rows = []
    for day in DAYS:
        for dish in ("burger", "wrap"):
            q = qty_for(day, dish)
            if mult_from is not None and day >= mult_from:
                q *= 7
            rows.append((day, dish, q, 12.0 if dish == "burger" else 10.0))
    return pd.DataFrame(rows, columns=["date", "menu_item_id", "qty_sold", "avg_price"])


def row(m, dish, day):
    return m[(m.menu_item_id == dish) & (m.date == day)].iloc[0]


def test_baseline_is_same_weekday_mean_of_prior_weeks():
    m = build_dish_matrix("r1", make_sales())
    day = DAYS[4 * 7 + 2]  # week 4, Wednesday
    prior = [qty_for(day - pd.Timedelta(days=7 * k), "burger") for k in (1, 2, 3, 4)]
    r = row(m, "burger", day)
    assert r[BASELINE] == pytest.approx(np.mean(prior))
    assert r[RATIO] == pytest.approx(r[QTY] / np.mean(prior))
    assert r.wd_lag_1w_ratio == pytest.approx(prior[0] / np.mean(prior))
    assert r.dow == 2


def test_first_week_has_no_baseline_and_partial_history_uses_available_weeks():
    m = build_dish_matrix("r1", make_sales())
    assert m[m.forecast_week == DAYS[0]][BASELINE].isna().all()
    day = DAYS[7 * 2 + 1]  # week 2 has only 2 prior weeks
    prior = [qty_for(day - pd.Timedelta(days=7 * k), "burger") for k in (1, 2)]
    assert row(m, "burger", day)[BASELINE] == pytest.approx(np.mean(prior))


def test_weekly_and_traffic_features_use_previous_week():
    m = build_dish_matrix("r1", make_sales())
    day = DAYS[3 * 7 + 1]
    prev_week = [qty_for(DAYS[2 * 7 + i], "burger") for i in range(7)]
    r = row(m, "burger", day)
    base = r[BASELINE]
    assert r.mean_7d_ratio == pytest.approx(np.mean(prev_week) / base)
    assert r.restaurant_traffic_ratio > 0
    assert r.price_vs_hist_4w == pytest.approx(1.0)


def test_events_are_dish_specific():
    events = pd.DataFrame(
        [("deal", DAYS[30], DAYS[31], ["wrap"], 0.2, 0.3), ("holiday", DAYS[35], DAYS[35], [], np.nan, 0.1)],
        columns=["type", "start_date", "end_date", "items", "discount_pct", "expected_lift"],
    )
    m = build_dish_matrix("r1", make_sales(), events)
    assert row(m, "wrap", DAYS[30]).dish_event_flag == 1
    assert row(m, "wrap", DAYS[30]).event_discount_pct == pytest.approx(0.2)
    assert row(m, "burger", DAYS[30]).dish_event_flag == 0
    assert row(m, "burger", DAYS[30]).deal_flag == 1
    assert row(m, "burger", DAYS[35]).holiday_flag == 1
    assert row(m, "burger", DAYS[35]).event_expected_lift == pytest.approx(0.1)
    assert row(m, "burger", DAYS[29]).deal_flag == 0


def test_missing_optional_inputs():
    m = build_dish_matrix("r1", make_sales().drop(columns="avg_price"))
    assert m["price_vs_hist_4w"].isna().all()
    assert (m["holiday_flag"] == 0).all()


def test_include_next_week_has_nan_target_and_features():
    m = build_dish_matrix("r1", make_sales(), include_next_week=True)
    future = m[m.forecast_week == DAYS[0] + pd.Timedelta(days=42)]
    assert len(future) == 14 and future[QTY].isna().all() and future[BASELINE].notna().all()
    assert future.wd_lag_1w_ratio.notna().all()


def test_partial_last_week_is_dropped_not_zero_filled():
    sales = make_sales()
    sales = sales[sales.date <= DAYS[-1] - pd.Timedelta(days=3)]  # week 5 only Mon-Thu
    m = build_dish_matrix("r1", sales)
    assert m[QTY].notna().all()
    assert m.date.max() == DAYS[-1] - pd.Timedelta(days=3)


@pytest.mark.parametrize("week_idx", [2, 4])
def test_no_leakage_from_current_or_future_days(week_idx):
    cutoff_week_start = DAYS[week_idx * 7]
    base = build_dish_matrix("r1", make_sales())
    mutated = build_dish_matrix("r1", make_sales(mult_from=cutoff_week_start))
    a = base[base.forecast_week == cutoff_week_start].reset_index(drop=True)
    b = mutated[mutated.forecast_week == cutoff_week_start].reset_index(drop=True)
    pd.testing.assert_frame_equal(a[DISH_FEATURES + [BASELINE]].astype(float), b[DISH_FEATURES + [BASELINE]].astype(float))
    assert (a[QTY] != b[QTY]).all()
