"""Point-in-time feature matrix for next-week ingredient usage forecasting.

Grain: one row per ingredient x forecast_week (weeks run Monday to Sunday).
Target: next_week_usage = sum over the forecast week of qty_sold x qty_per_serving.

Leakage rule: a row for forecast week W only sees data dated on or before the
cutoff (the Sunday ending week W-1). Every lag and rolling feature is computed
on a series shifted by one week. Only calendar and event features look at week
W itself, because holidays and planned deals are known ahead of time.

Pure pandas, no DB access. See docs/xgboost-forecasting.md.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

WEEK = pd.Timedelta(days=7)

FEATURE_COLUMNS = [
    "usage_lag_1w",
    "usage_lag_2w",
    "usage_lag_4w",
    "usage_lag_8w",
    "usage_lag_52w",
    "usage_mean_4w",
    "usage_mean_8w",
    "usage_std_8w",
    "usage_trend_4w",
    "dish_demand_contribution",
    "number_of_dishes_using_ingredient",
    "total_restaurant_sales_lag_1w",
    "purchase_qty_lag_1w",
    "purchase_qty_mean_4w",
    "days_since_last_purchase",
    "purchase_to_usage_ratio_4w",
    "current_qty_on_hand",
    "inventory_lag_1w",
    "inventory_to_usage_ratio",
    "inventory_variance_4w",
    "week_of_year",
    "month",
    "holiday_flag",
    "deal_flag",
    "ingredient_event_flag",
    "event_expected_lift",
    "unit_cost",
    "pack_size",
    "shelf_life_days",
]

TARGET = "next_week_usage"
KEY_COLUMNS = ["restaurant_id", "ingredient_id", "forecast_week"]


def _week_start(s: pd.Series) -> pd.Series:
    d = pd.to_datetime(s).dt.normalize()
    return d - pd.to_timedelta(d.dt.weekday, unit="D")


def _lag(wide: pd.DataFrame, k: int) -> pd.DataFrame:
    """Value of the series k weeks before each forecast week (k >= 1)."""
    return wide.shift(k)


def _roll(wide: pd.DataFrame, window: int, fn: str, min_periods: int) -> pd.DataFrame:
    """Rolling stat over the `window` weeks ending at W-1 (shifted, so W is excluded)."""
    return getattr(wide.shift(1).rolling(window, min_periods=min_periods), fn)()


def _slope(values: np.ndarray) -> float:
    x = np.arange(len(values), dtype=float)
    x -= x.mean()
    return float((x * (values - values.mean())).sum() / (x * x).sum())


def _asof(dates: np.ndarray, values: np.ndarray, query: pd.Timestamp) -> float:
    """Latest value with date <= query, NaN when there is none."""
    if len(dates) == 0:
        return np.nan
    idx = np.searchsorted(dates, np.datetime64(query), side="right") - 1
    return float(values[idx]) if idx >= 0 else np.nan


def _stack(wide: pd.DataFrame, name: str) -> pd.Series:
    s = wide.stack(future_stack=True)
    s.index.names = ["forecast_week", "ingredient_id"]
    return s.rename(name)


def weekly_usage(sales: pd.DataFrame, recipes: pd.DataFrame) -> pd.DataFrame:
    """Long frame: week, ingredient_id, menu_item_id, usage (qty_sold x qty_per_serving).

    recipes.qty_per_serving is implicitly in the ingredient's own unit (no unit
    column exists), so no conversion is applied.
    """
    joined = sales.merge(recipes, on="menu_item_id", how="inner")
    joined["usage"] = joined["qty_sold"].astype(float) * joined["qty_per_serving"].astype(float)
    joined["week"] = _week_start(joined["date"])
    return joined.groupby(["week", "ingredient_id", "menu_item_id"], as_index=False)["usage"].sum()


def _event_frames(
    events: pd.DataFrame, recipes: pd.DataFrame, weeks: pd.DatetimeIndex, ingredient_ids: list[str]
) -> dict[str, pd.DataFrame]:
    holiday = pd.DataFrame(0.0, index=weeks, columns=ingredient_ids)
    deal = holiday.copy()
    ing_flag = holiday.copy()
    lift = holiday.copy()
    if events is None or events.empty:
        return {"holiday_flag": holiday, "deal_flag": deal, "ingredient_event_flag": ing_flag, "event_expected_lift": lift}

    items_to_ingredients = recipes.groupby("menu_item_id")["ingredient_id"].apply(set).to_dict()
    for ev in events.itertuples(index=False):
        start = pd.Timestamp(ev.start_date).normalize()
        end = pd.Timestamp(ev.end_date).normalize()
        overlap = (weeks + pd.Timedelta(days=6) >= start) & (weeks <= end)
        if not overlap.any():
            continue
        if ev.type == "holiday":
            holiday.loc[overlap, :] = 1.0
        else:
            deal.loc[overlap, :] = 1.0
        affected: set[str] = set()
        for item in ev.items if ev.items is not None else []:
            affected |= items_to_ingredients.get(str(item), set())
        cols = [c for c in ingredient_ids if c in affected]
        expected = 0.0 if pd.isna(ev.expected_lift) else float(ev.expected_lift)
        if cols:
            ing_flag.loc[overlap, cols] = 1.0
            lift.loc[overlap, cols] = np.maximum(lift.loc[overlap, cols], expected)
        elif ev.type == "holiday":
            # A holiday without an item list affects every ingredient.
            lift.loc[overlap, :] = np.maximum(lift.loc[overlap, :], expected)
    return {"holiday_flag": holiday, "deal_flag": deal, "ingredient_event_flag": ing_flag, "event_expected_lift": lift}


def build_feature_matrix(
    restaurant_id: str,
    sales: pd.DataFrame,
    recipes: pd.DataFrame,
    ingredients: pd.DataFrame,
    purchases: pd.DataFrame | None = None,
    counts: pd.DataFrame | None = None,
    events: pd.DataFrame | None = None,
    include_next_week: bool = False,
) -> pd.DataFrame:
    """Build the training matrix (KEY_COLUMNS + FEATURE_COLUMNS + TARGET).

    Frames (ids are strings):
      sales: date, menu_item_id, qty_sold
      recipes: menu_item_id, ingredient_id, qty_per_serving
      ingredients: ingredient_id, unit_cost, pack_size, shelf_life_days
      purchases: date, ingredient_id, qty            (optional)
      counts: date, ingredient_id, qty_on_hand       (optional)
      events: type, start_date, end_date, items, expected_lift (optional)

    include_next_week adds one extra row per ingredient for the week after the
    last sales week, with a NaN target, for inference.
    """
    purchases = purchases if purchases is not None else pd.DataFrame(columns=["date", "ingredient_id", "qty"])
    counts = counts if counts is not None else pd.DataFrame(columns=["date", "ingredient_id", "qty_on_hand"])

    usage_long = weekly_usage(sales, recipes)
    if usage_long.empty:
        return pd.DataFrame(columns=KEY_COLUMNS + FEATURE_COLUMNS + [TARGET])

    first_week = usage_long["week"].min()
    last_week = _week_start(pd.Series([sales["date"].max()])).iloc[0]
    weeks = pd.date_range(first_week, last_week + (WEEK if include_next_week else pd.Timedelta(0)), freq="7D")
    ingredient_ids = sorted(recipes["ingredient_id"].unique())

    def wide(long: pd.DataFrame, value: str, fill: float | None = 0.0) -> pd.DataFrame:
        w = long.pivot_table(index="week", columns="ingredient_id", values=value, aggfunc="sum")
        w = w.reindex(index=weeks, columns=ingredient_ids)
        return w if fill is None else w.fillna(fill)

    usage = wide(usage_long, "usage")
    if include_next_week:
        usage.loc[weeks[-1], :] = np.nan  # unknown future week, never a feature source

    # Dish-level share: top dish's share of each ingredient's usage.
    by_ing = usage_long.groupby(["week", "ingredient_id"])["usage"]
    top_share = (by_ing.max() / by_ing.sum()).rename("share").reset_index()
    top_share_w = wide(top_share, "share", fill=np.nan)

    total_sales = (
        sales.assign(week=_week_start(sales["date"]))
        .groupby("week")["qty_sold"].sum().astype(float).reindex(weeks)
    )
    total_sales = total_sales.fillna(0.0)
    if include_next_week:
        total_sales.iloc[-1] = np.nan
    total_sales_w = pd.DataFrame({c: total_sales for c in ingredient_ids})

    # Purchases (NaN everywhere when there are none: missing data, not zero buying).
    if purchases.empty:
        purch = pd.DataFrame(np.nan, index=weeks, columns=ingredient_ids)
    else:
        p = purchases.assign(week=_week_start(purchases["date"]), qty=purchases["qty"].astype(float))
        purch = wide(p, "qty")
        if include_next_week:
            purch.loc[weeks[-1], :] = np.nan

    cutoffs = weeks - pd.Timedelta(days=1)  # Sunday ending the previous week

    days_since = pd.DataFrame(np.nan, index=weeks, columns=ingredient_ids)
    on_hand = days_since.copy()
    on_hand_prev_week = days_since.copy()
    on_hand_4w_ago = days_since.copy()
    for ing in ingredient_ids:
        pd_ing = np.sort(pd.to_datetime(purchases.loc[purchases["ingredient_id"] == ing, "date"]).values)
        c_ing = counts.loc[counts["ingredient_id"] == ing].assign(date=lambda d: pd.to_datetime(d["date"]))
        c_ing = c_ing.sort_values("date", kind="stable")
        c_dates = c_ing["date"].values
        c_vals = c_ing["qty_on_hand"].astype(float).values
        for wk, cutoff in zip(weeks, cutoffs):
            if len(pd_ing):
                i = np.searchsorted(pd_ing, np.datetime64(cutoff), side="right") - 1
                if i >= 0:
                    days_since.loc[wk, ing] = float((cutoff - pd.Timestamp(pd_ing[i])).days)
            on_hand.loc[wk, ing] = _asof(c_dates, c_vals, cutoff)
            on_hand_prev_week.loc[wk, ing] = _asof(c_dates, c_vals, cutoff - WEEK)
            on_hand_4w_ago.loc[wk, ing] = _asof(c_dates, c_vals, cutoff - 4 * WEEK)

    usage_mean_4w = _roll(usage, 4, "mean", 1)
    purch_sum_4w = _roll(purch, 4, "sum", 4)
    usage_sum_4w = _roll(usage, 4, "sum", 4)

    with np.errstate(divide="ignore", invalid="ignore"):
        purchase_ratio = (purch_sum_4w / usage_sum_4w).replace([np.inf, -np.inf], np.nan)
        inv_ratio = (on_hand / usage_mean_4w).replace([np.inf, -np.inf], np.nan)

    # actual end - (beginning + purchases - theoretical usage), over the last 4 weeks.
    # Not labelled waste: it also holds count errors, unrecorded usage, transfers.
    inventory_variance = on_hand - (on_hand_4w_ago + purch_sum_4w - usage_sum_4w)

    ev = _event_frames(events, recipes, weeks, ingredient_ids)

    n_dishes = recipes.groupby("ingredient_id")["menu_item_id"].nunique()
    n_dishes_w = pd.DataFrame({c: n_dishes[c] for c in ingredient_ids}, index=weeks).astype(float)

    static = ingredients.set_index("ingredient_id")
    calendar_week = pd.Series(weeks.isocalendar().week.values.astype(float), index=weeks)
    calendar_month = pd.Series(weeks.month.values.astype(float), index=weeks)

    frames: dict[str, pd.DataFrame] = {
        "usage_lag_1w": _lag(usage, 1),
        "usage_lag_2w": _lag(usage, 2),
        "usage_lag_4w": _lag(usage, 4),
        "usage_lag_8w": _lag(usage, 8),
        "usage_lag_52w": _lag(usage, 52),
        "usage_mean_4w": usage_mean_4w,
        "usage_mean_8w": _roll(usage, 8, "mean", 1),
        "usage_std_8w": _roll(usage, 8, "std", 2),
        "usage_trend_4w": usage.shift(1).rolling(4, min_periods=4).apply(_slope, raw=True),
        "dish_demand_contribution": _lag(top_share_w, 1),
        "number_of_dishes_using_ingredient": n_dishes_w,
        "total_restaurant_sales_lag_1w": _lag(total_sales_w, 1),
        "purchase_qty_lag_1w": _lag(purch, 1),
        "purchase_qty_mean_4w": _roll(purch, 4, "mean", 1),
        "days_since_last_purchase": days_since,
        "purchase_to_usage_ratio_4w": purchase_ratio,
        "current_qty_on_hand": on_hand,
        "inventory_lag_1w": on_hand_prev_week,
        "inventory_to_usage_ratio": inv_ratio,
        "inventory_variance_4w": inventory_variance,
        **ev,
    }

    parts = [_stack(f, name) for name, f in frames.items()]
    parts.append(_stack(usage, TARGET))
    matrix = pd.concat(parts, axis=1).reset_index()

    matrix["week_of_year"] = matrix["forecast_week"].map(calendar_week)
    matrix["month"] = matrix["forecast_week"].map(calendar_month)
    for col in ("unit_cost", "pack_size", "shelf_life_days"):
        matrix[col] = matrix["ingredient_id"].map(static[col].astype(float))
    matrix.insert(0, "restaurant_id", restaurant_id)

    return matrix[KEY_COLUMNS + FEATURE_COLUMNS + [TARGET]].sort_values(
        ["forecast_week", "ingredient_id"], ignore_index=True
    )
