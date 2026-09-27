"""Point-in-time daily dish feature matrix for the dish-level XGBoost model.

Grain: one row per menu item x day. Rows are grouped in forecast weeks
(Monday to Sunday). For every day in week W the cutoff is the Sunday ending
week W-1, so all rows of a week are a 7-day-ahead forecast made at one time.

Target: qty_sold for that dish and day, modelled as a ratio to a baseline:

    baseline_qty = mean of the same weekday over the last (up to) 4 weeks
    ratio        = qty_sold / baseline_qty

Ingredient usage is recovered afterwards as sum(qty x recipes.qty_per_serving).

Leakage rule: same-weekday lags are at least 7 days back, weekly stats are
shifted by one week, and only calendar and event features look at the forecast
day itself. See docs/xgboost-forecasting.md.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DISH_FEATURES = [
    "dow",
    "week_of_year",
    "month",
    "wd_lag_1w_ratio",
    "wd_lag_2w_ratio",
    "wd_lag_4w_ratio",
    "wd_cv",
    "mean_7d_ratio",
    "mean_28d_ratio",
    "dish_trend_ratio",
    "restaurant_traffic_ratio",
    "price_vs_hist_4w",
    "holiday_flag",
    "deal_flag",
    "dish_event_flag",
    "event_discount_pct",
    "event_expected_lift",
]

QTY = "qty_sold"
BASELINE = "baseline_qty"
RATIO = "ratio"
RATIO_CLIP = (0.0, 3.0)
KEY_COLUMNS = ["restaurant_id", "menu_item_id", "date", "forecast_week"]


def _monday(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return index.normalize() - pd.to_timedelta(index.weekday, unit="D")


def _stack(wide: pd.DataFrame, name: str) -> pd.Series:
    s = wide.stack(future_stack=True)
    s.index.names = ["date", "menu_item_id"]
    return s.rename(name)


def _safe_ratio(num: pd.DataFrame, den: pd.DataFrame) -> pd.DataFrame:
    return num.where(den > 0) / den.where(den > 0)


def _event_frames(events: pd.DataFrame | None, days: pd.DatetimeIndex, dishes: list[str]) -> dict[str, pd.DataFrame]:
    zeros = pd.DataFrame(0.0, index=days, columns=dishes)
    holiday, deal = zeros.copy(), zeros.copy()
    dish_event, discount, lift = zeros.copy(), zeros.copy(), zeros.copy()
    if events is not None and not events.empty:
        for ev in events.itertuples(index=False):
            cover = (days >= pd.Timestamp(ev.start_date).normalize()) & (days <= pd.Timestamp(ev.end_date).normalize())
            if not cover.any():
                continue
            if ev.type == "holiday":
                holiday.loc[cover, :] = 1.0
            else:
                deal.loc[cover, :] = 1.0
            items = [str(i) for i in (ev.items if ev.items is not None else []) if str(i) in dishes]
            d = 0.0 if pd.isna(ev.discount_pct) else float(ev.discount_pct)
            lf = 0.0 if pd.isna(ev.expected_lift) else float(ev.expected_lift)
            if items:
                dish_event.loc[cover, items] = 1.0
                discount.loc[cover, items] = np.maximum(discount.loc[cover, items], d)
                lift.loc[cover, items] = np.maximum(lift.loc[cover, items], lf)
            elif ev.type == "holiday":
                lift.loc[cover, :] = np.maximum(lift.loc[cover, :], lf)  # holiday without items hits all dishes
    return {
        "holiday_flag": holiday,
        "deal_flag": deal,
        "dish_event_flag": dish_event,
        "event_discount_pct": discount,
        "event_expected_lift": lift,
    }


def build_dish_matrix(
    restaurant_id: str,
    sales: pd.DataFrame,
    events: pd.DataFrame | None = None,
    include_next_week: bool = False,
) -> pd.DataFrame:
    """Daily dish matrix: KEY_COLUMNS + DISH_FEATURES + [QTY, BASELINE, RATIO].

    sales: date, menu_item_id, qty_sold, avg_price (optional)
    events: type, start_date, end_date, items, discount_pct, expected_lift (optional)

    Days with no sales row on or before the last sales date count as 0 sold.
    include_next_week adds the 7 days after the last sales week with NaN target.
    """
    columns = KEY_COLUMNS + DISH_FEATURES + [QTY, BASELINE, RATIO]
    if sales.empty:
        return pd.DataFrame(columns=columns)

    s = sales.copy()
    s["date"] = pd.to_datetime(s["date"]).dt.normalize()
    max_date = s["date"].max()
    first_monday = _monday(pd.DatetimeIndex([s["date"].min()]))[0]
    last_week = _monday(pd.DatetimeIndex([max_date]))[0]
    end = last_week + pd.Timedelta(days=6 + (7 if include_next_week else 0))
    days = pd.date_range(first_monday, end, freq="D")
    dishes = sorted(s["menu_item_id"].unique())
    wk = _monday(days)

    qty = (
        s.pivot_table(index="date", columns="menu_item_id", values="qty_sold", aggfunc="sum")
        .reindex(index=days, columns=dishes)
        .fillna(0.0)
    )
    qty.loc[days > max_date, :] = np.nan  # not observed yet, never a feature source

    def broadcast(weekly: pd.DataFrame) -> pd.DataFrame:
        return weekly.reindex(wk).set_axis(days, axis=0)

    # Same-weekday baseline and lags (all >= 7 days back, so <= cutoff).
    stack = np.stack([qty.shift(7 * k).values for k in (1, 2, 3, 4)])
    count = (~np.isnan(stack)).sum(axis=0)
    total = np.nansum(stack, axis=0)
    mean_sq = np.nansum(stack**2, axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        base = np.where(count > 0, total / np.maximum(count, 1), np.nan)
        var = np.maximum(mean_sq / np.maximum(count, 1) - base**2, 0.0)
        std = np.where(count >= 2, np.sqrt(var), np.nan)
    baseline = pd.DataFrame(base, index=days, columns=dishes)
    wd_std = pd.DataFrame(std, index=days, columns=dishes)

    # Weekly stats of the previous weeks (NaN for partial or unobserved weeks).
    weekly = qty.groupby(wk).sum(min_count=7)
    prev = weekly.shift(1)
    mean_7d = broadcast(prev / 7)
    mean_28d = broadcast(prev.rolling(4, min_periods=1).mean() / 7)

    totals = weekly.sum(axis=1, min_count=len(dishes)).shift(1)
    traffic = totals / totals.rolling(4, min_periods=1).mean()
    traffic_w = broadcast(pd.DataFrame({d: traffic for d in dishes}))

    if "avg_price" in s.columns:
        price = (
            s.pivot_table(index="date", columns="menu_item_id", values="avg_price", aggfunc="mean")
            .reindex(index=days, columns=dishes)
        )
        price_weekly = price.groupby(wk).mean().shift(1)
        price_vs_hist = broadcast(price_weekly / price_weekly.rolling(4, min_periods=1).mean())
    else:
        price_vs_hist = pd.DataFrame(np.nan, index=days, columns=dishes)

    frames: dict[str, pd.DataFrame] = {
        "wd_lag_1w_ratio": _safe_ratio(qty.shift(7), baseline),
        "wd_lag_2w_ratio": _safe_ratio(qty.shift(14), baseline),
        "wd_lag_4w_ratio": _safe_ratio(qty.shift(28), baseline),
        "wd_cv": _safe_ratio(wd_std, baseline),
        "mean_7d_ratio": _safe_ratio(mean_7d, baseline),
        "mean_28d_ratio": _safe_ratio(mean_28d, baseline),
        "dish_trend_ratio": _safe_ratio(mean_7d, mean_28d),
        "restaurant_traffic_ratio": traffic_w,
        "price_vs_hist_4w": price_vs_hist,
        **_event_frames(events, days, dishes),
    }

    parts = [_stack(f, name) for name, f in frames.items()]
    parts += [_stack(qty, QTY), _stack(baseline, BASELINE)]
    m = pd.concat(parts, axis=1).reset_index()

    m["forecast_week"] = _monday(pd.DatetimeIndex(m["date"]))
    m["dow"] = m["date"].dt.weekday.astype(float)
    m["week_of_year"] = m["forecast_week"].dt.isocalendar().week.astype(float)
    m["month"] = m["date"].dt.month.astype(float)
    m["restaurant_id"] = restaurant_id

    unobserved = m["date"] > max_date
    m = m[~unobserved | (m["forecast_week"] > last_week)]

    ok = m[BASELINE] > 0
    m[RATIO] = (m[QTY] / m[BASELINE].where(ok)).clip(*RATIO_CLIP)
    return m[columns].sort_values(["date", "menu_item_id"], ignore_index=True)
