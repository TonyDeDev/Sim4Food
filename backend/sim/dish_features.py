"""Point-in-time daily dish feature matrix for the dish-level XGBoost model.

Grain: one row per menu item x day. Rows are grouped in forecast weeks
(Monday to Sunday). For every day in week W the cutoff is the Sunday ending
week W-1, so all rows of a week are a 7-day-ahead forecast made at one time.

Target: qty_sold for that dish and day, modelled as a ratio to a baseline:

    baseline_qty = mean of the same weekday over the last (up to) 4 weeks
    ratio        = qty_sold / baseline_qty

Ingredient usage is recovered afterwards as sum(qty x recipes.qty_per_serving).

Sales are not demand. Two kinds of days are cleaned out of the history the
baseline and lag features are built from:

- Censored days: a dish that normally sells (trailing mean >= MIN_DAILY_FOR_ZERO)
  sold 0 on a day the restaurant was open. That is a stockout (or the dish was
  off the menu), not zero demand. These days are never a training target.
- Event days: a deal or holiday covered the dish. Their lift is estimated
  separately (sim/events_adjust.py), so they do not inflate the normal baseline.

When every same-weekday lag is censored (a dish that sells out every Sunday),
the baseline falls back to the dish's recent daily level times the restaurant's
weekday index, so the forecast estimates demand instead of repeating the zero.

Leakage rule: same-weekday lags are at least 7 days back, weekly stats are
shifted by one week, and only calendar and event features look at the forecast
day itself. See docs/xgboost-forecasting.md.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

EVENT_FEATURES = [
    "holiday_flag",
    "deal_flag",
    "dish_event_flag",
    "event_discount_pct",
    "event_expected_lift",
]

DISH_FEATURES = [
    "dow",
    "wd_lag_1w_ratio",
    "wd_lag_2w_ratio",
    "wd_lag_4w_ratio",
    "wd_cv",
    "mean_7d_ratio",
    "mean_28d_ratio",
    "dish_trend_ratio",
    "restaurant_traffic_ratio",
    "price_vs_hist_4w",
    *EVENT_FEATURES,
]

# Season features. With under a year of history every week has its own
# week_of_year, so trees would use it as a time index; see select_features.
CALENDAR_FEATURES = ["week_of_year", "month"]

QTY = "qty_sold"
BASELINE = "baseline_qty"
RATIO = "ratio"
CENSORED = "censored"
EVENT_DAY = "event_day"
RATIO_CLIP = (0.0, 3.0)
MIN_DAILY_FOR_ZERO = 3.0
KEY_COLUMNS = ["restaurant_id", "menu_item_id", "date", "forecast_week"]
OUTPUT_COLUMNS = KEY_COLUMNS + DISH_FEATURES + CALENDAR_FEATURES + [QTY, BASELINE, RATIO, CENSORED, EVENT_DAY]


def _monday(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return index.normalize() - pd.to_timedelta(index.weekday, unit="D")


def _stack(wide: pd.DataFrame, name: str) -> pd.Series:
    s = wide.stack(future_stack=True)
    s.index.names = ["date", "menu_item_id"]
    return s.rename(name)


def _safe_ratio(num: pd.DataFrame, den: pd.DataFrame) -> pd.DataFrame:
    return num.where(den > 0) / den.where(den > 0)


def _weekday_lags(wide: pd.DataFrame, weeks=(1, 2, 3, 4)) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(count, mean, std) of the same weekday 1..4 weeks back, ignoring NaN."""
    stack = np.stack([wide.shift(7 * k).values for k in weeks])
    count = (~np.isnan(stack)).sum(axis=0)
    total = np.nansum(stack, axis=0)
    sq = np.nansum(stack**2, axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(count > 0, total / np.maximum(count, 1), np.nan)
        var = np.maximum(sq / np.maximum(count, 1) - mean**2, 0.0)
        std = np.where(count >= 2, np.sqrt(var), np.nan)
    return count, mean, std


def _event_frames(events: pd.DataFrame | None, days: pd.DatetimeIndex, dishes: list[str]) -> dict[str, pd.DataFrame]:
    zeros = pd.DataFrame(0.0, index=days, columns=dishes)
    holiday, deal = zeros.copy(), zeros.copy()
    dish_event, discount, lift, affected = zeros.copy(), zeros.copy(), zeros.copy(), zeros.copy()
    if events is not None and not events.empty:
        for ev in events.itertuples(index=False):
            cover = (days >= pd.Timestamp(ev.start_date).normalize()) & (days <= pd.Timestamp(ev.end_date).normalize())
            if not cover.any():
                continue
            if ev.type == "holiday":
                holiday.loc[cover, :] = 1.0
            else:
                deal.loc[cover, :] = 1.0
            raw_items = ev.items if isinstance(ev.items, (list, tuple, np.ndarray)) else []
            items = [str(i) for i in raw_items if str(i) in dishes]
            d = 0.0 if pd.isna(ev.discount_pct) else float(ev.discount_pct)
            lf = 0.0 if pd.isna(ev.expected_lift) else float(ev.expected_lift)
            if items:
                dish_event.loc[cover, items] = 1.0
                discount.loc[cover, items] = np.maximum(discount.loc[cover, items], d)
                lift.loc[cover, items] = np.maximum(lift.loc[cover, items], lf)
                affected.loc[cover, items] = 1.0
            else:
                # An event without an item list (every holiday, a store-wide deal) hits all dishes.
                lift.loc[cover, :] = np.maximum(lift.loc[cover, :], lf)
                affected.loc[cover, :] = 1.0
    return {
        "holiday_flag": holiday,
        "deal_flag": deal,
        "dish_event_flag": dish_event,
        "event_discount_pct": discount,
        "event_expected_lift": lift,
        EVENT_DAY: affected,
    }


def build_dish_matrix(
    restaurant_id: str,
    sales: pd.DataFrame,
    events: pd.DataFrame | None = None,
    include_next_week: bool = False,
) -> pd.DataFrame:
    """Daily dish matrix: OUTPUT_COLUMNS.

    sales: date, menu_item_id, qty_sold, avg_price (optional)
    events: type, start_date, end_date, items, discount_pct, expected_lift (optional)

    Days with no sales row on or before the last sales date count as 0 sold,
    except before a dish's first sale (not on the menu yet: NaN).
    include_next_week adds the 7 days after the last sales week with NaN target.
    """
    if sales.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

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
    observed = days <= max_date
    qty.loc[~observed, :] = np.nan  # not observed yet, never a feature source
    first_row = s.groupby("menu_item_id")["date"].min()
    first_sale = s[s["qty_sold"] > 0].groupby("menu_item_id")["date"].min().reindex(first_row.index).fillna(first_row)
    for dish in dishes:
        qty.loc[days < first_sale[dish], dish] = np.nan  # not on the menu yet

    ev = _event_frames(events, days, dishes)
    affected = ev.pop(EVENT_DAY) > 0

    day_total = qty.sum(axis=1, min_count=1)
    open_day = day_total > 0
    trailing = qty.rolling(28, min_periods=3).mean().shift(1)
    censored = (qty == 0) & (trailing >= MIN_DAILY_FOR_ZERO) & open_day.values[:, None]
    qty_obs = qty.where(~censored)  # demand is unknown on a stockout day
    qty_base = qty_obs.where(~affected)  # the normal-week history

    def broadcast(weekly: pd.DataFrame | pd.Series) -> pd.DataFrame:
        out = weekly.reindex(wk)
        out.index = days
        return out

    # Same-weekday baseline and lags (all >= 7 days back, so <= cutoff).
    count, mean, std = _weekday_lags(qty_base)
    # Fallback when every same-weekday lag is censored: recent daily level x weekday index.
    # The weekday index is the median over the other dishes of (same-weekday mean / daily
    # level), so the sold-out dish's own zeros do not drag its fallback down.
    level = qty_base.shift(7).rolling(28, min_periods=7).mean().values
    with np.errstate(invalid="ignore", divide="ignore"):
        dish_index = np.where((count > 0) & (level > 0), mean / level, np.nan)
        all_nan = np.isnan(dish_index).all(axis=1)
        weekday_index = np.full(len(days), np.nan)
        weekday_index[~all_nan] = np.nanmedian(dish_index[~all_nan], axis=1)
    fallback = level * weekday_index[:, None]
    baseline = pd.DataFrame(np.where(count > 0, mean, fallback), index=days, columns=dishes)
    wd_std = pd.DataFrame(std, index=days, columns=dishes)

    # Weekly stats of the previous weeks: mean per observed normal day, NaN when too few.
    grouped = qty_base.groupby(wk)
    weekly_mean = grouped.mean().where(grouped.count() >= 4)
    prev = weekly_mean.shift(1)
    mean_7d = broadcast(prev)
    mean_28d = broadcast(prev.rolling(4, min_periods=1).mean())

    complete = pd.Series(observed, index=days).groupby(wk).all()
    totals = qty.fillna(0.0).sum(axis=1).groupby(wk).sum().where(complete).shift(1)
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
        "wd_lag_1w_ratio": _safe_ratio(qty_base.shift(7), baseline),
        "wd_lag_2w_ratio": _safe_ratio(qty_base.shift(14), baseline),
        "wd_lag_4w_ratio": _safe_ratio(qty_base.shift(28), baseline),
        "wd_cv": _safe_ratio(wd_std, baseline),
        "mean_7d_ratio": _safe_ratio(mean_7d, baseline),
        "mean_28d_ratio": _safe_ratio(mean_28d, baseline),
        "dish_trend_ratio": _safe_ratio(mean_7d, mean_28d),
        "restaurant_traffic_ratio": traffic_w,
        "price_vs_hist_4w": price_vs_hist,
        **ev,
    }

    parts = [_stack(f, name) for name, f in frames.items()]
    parts += [
        _stack(qty, QTY),
        _stack(baseline, BASELINE),
        _stack(qty_obs, "_qty_obs"),
        _stack(censored.astype(float), CENSORED),
        _stack(affected.astype(float), EVENT_DAY),
    ]
    m = pd.concat(parts, axis=1).reset_index()

    m["forecast_week"] = _monday(pd.DatetimeIndex(m["date"]))
    m["dow"] = m["date"].dt.weekday.astype(float)
    m["week_of_year"] = m["forecast_week"].dt.isocalendar().week.astype(float)
    m["month"] = m["date"].dt.month.astype(float)
    m["restaurant_id"] = restaurant_id
    m[CENSORED] = m[CENSORED] > 0
    m[EVENT_DAY] = m[EVENT_DAY] > 0

    unobserved = m["date"] > max_date
    m = m[~unobserved | (m["forecast_week"] > last_week)]

    ok = m[BASELINE] > 0
    m[RATIO] = (m["_qty_obs"] / m[BASELINE].where(ok)).clip(*RATIO_CLIP)
    return m[OUTPUT_COLUMNS].sort_values(["date", "menu_item_id"], ignore_index=True)
