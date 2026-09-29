"""Order recommendations from the forecast distribution (newsvendor rule).

For each ingredient and the target week:

    Co = cost of one unit left over   (unit cost if perishable, else a carry cost)
    Cu = cost of one unit short       (margin of the dishes that cannot be sold)
    q* = Cu / (Cu + Co)               (clipped to Q_BOUNDS)

Cu sizes each ingredient's own order, so it carries the whole margin of the
dishes it would block. Reported dollars use Cu_share instead, which splits a
dish's margin across the ingredients it needs - see unit_costs.

Orders follow the restaurant's own delivery rhythm, read from its purchase
history (e.g. Monday and Thursday). The first delivery is a firm order: the q*
quantile of that cycle's usage minus the stock on hand. Later deliveries are a
plan that adapts: before each one, the forecast for the rest of the week is
scaled by how the earlier days actually sold (half of the surprise is trusted,
ADAPT_WEIGHT) and topped up to its q* quantile. This mirrors what a good owner
does, so the comparison with them is fair.

Outcomes (leftover, waste, stockout risk) are simulated on the Monte Carlo
usage samples (sim/uncertainty.py) and compared, on the same samples, with the
owner's habit (last week's usage x 1.25 minus stock, rounded to packs, split
over the deliveries). order_backtest replays past weeks against what the owner
actually bought, delivery by delivery.

Pure pandas and numpy, no DB access.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from sim.history import attach_recipes

PERISHABLE_DAYS = 7
CARRY_COST_SHARE = 0.10  # leftover long-life stock is used next week, it only ties up cash
LOST_SALE_SHARE = 0.5  # about half the guests who miss a dish buy something else instead
Q_BOUNDS = (0.5, 0.95)
OWNER_MARKUP = 1.25
ADAPT_WEIGHT = 0.5
MIN_DELIVERY_SHARE = 0.15  # a weekday is a delivery day when it has this share of purchase rows
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def ceil_to_pack(qty, pack: float):
    """Round up to whole packs; works on floats and numpy arrays."""
    q = np.maximum(np.asarray(qty, dtype=float), 0.0)
    if pack and pack > 0 and not math.isnan(pack):
        q = np.ceil(q / pack - 1e-9) * pack
    return float(q) if q.ndim == 0 else q


def is_perishable(shelf_life_days) -> bool:
    return shelf_life_days is None or pd.isna(shelf_life_days) or float(shelf_life_days) <= PERISHABLE_DAYS


def delivery_days(purchases: pd.DataFrame | None) -> list[int]:
    """Weekdays (0 = Monday) the restaurant usually receives deliveries; Monday when unknown."""
    if purchases is None or purchases.empty:
        return [0]
    share = pd.to_datetime(purchases["date"]).dt.weekday.value_counts(normalize=True)
    days = sorted(int(d) for d, s in share.items() if s >= MIN_DELIVERY_SHARE)
    return days or [0]


def cycle_of(weekday: pd.Series, days: list[int]) -> pd.Series:
    """Delivery cycle index for each weekday; days before the first delivery belong to the last cycle."""
    starts = np.array(days)
    idx = np.searchsorted(starts, weekday.to_numpy(), side="right") - 1
    return pd.Series(np.where(idx < 0, len(days) - 1, idx), index=weekday.index)


def cycle_usage(usage_rows: pd.DataFrame, days: list[int]) -> pd.DataFrame:
    """ingredient x cycle usage from date, ingredient_id, qty rows."""
    if usage_rows.empty:
        return pd.DataFrame(columns=range(len(days)), dtype=float)
    cyc = cycle_of(pd.to_datetime(usage_rows["date"]).dt.weekday, days)
    wide = usage_rows.assign(cycle=cyc.values).pivot_table(
        index="ingredient_id", columns="cycle", values="qty", aggfunc="sum"
    )
    return wide.reindex(columns=range(len(days))).fillna(0.0)


def daily_usage(sales: pd.DataFrame, recipes: pd.DataFrame) -> pd.DataFrame:
    """date, ingredient_id, qty: theoretical usage per day, recipe in force on the day."""
    if sales.empty:
        return pd.DataFrame(columns=["date", "ingredient_id", "qty"])
    s = sales.assign(date=pd.to_datetime(sales["date"]).dt.normalize())
    joined = attach_recipes(s[["date", "menu_item_id", "qty_sold"]], recipes, "date")
    joined["qty"] = joined["qty_sold"].astype(float) * joined["qty_per_serving"].astype(float)
    return joined.groupby(["date", "ingredient_id"], as_index=False)["qty"].sum()


def unit_costs(
    ingredients: pd.DataFrame, recipe: pd.DataFrame, menu: pd.DataFrame | None, dish_totals: pd.Series
) -> pd.DataFrame:
    """Per ingredient: co, cu, cu_share, q_star, perishable, unit_cost, pack_size.

    recipe: dishes x ingredients qty_per_serving (sim.uncertainty.recipe_matrix).
    dish_totals: forecast servings per dish, used to weight the dishes an ingredient goes into.

    Two underage costs, because the ordering decision and the money report need
    different ones:

    - `cu` prices one unit short for *this* ingredient's own order. Running out
      of it blocks the whole dish, so the whole dish margin is what that unit
      was worth, and `q_star` is built from it.
    - `cu_share` splits each dish's margin across the ingredients the dish
      needs. Only this one may be summed across ingredients: a burger that is
      short is one lost burger, not one per ingredient in it, so adding up `cu`
      dollars would count the same stockout once per line of the recipe (six
      times over, for a six-ingredient dish).
    """
    ing = ingredients.set_index("ingredient_id")
    for col, default in (("unit_cost", 0.0), ("pack_size", np.nan), ("shelf_life_days", np.nan)):
        if col not in ing:
            ing[col] = default
    cost = ing["unit_cost"].astype(float).reindex(recipe.columns).fillna(0.0)
    food_cost = recipe @ cost
    price = (
        menu.set_index("menu_item_id")["price"].astype(float).reindex(recipe.index)
        if menu is not None and not menu.empty else pd.Series(np.nan, index=recipe.index)
    )
    margin = (price - food_cost).clip(lower=0.0)
    # How many ingredients each dish needs, i.e. how many lines of the recipe
    # would each claim the dish's margin for themselves.
    lines = (recipe > 0).sum(axis=1).clip(lower=1)

    rows = {}
    for i in recipe.columns:
        qps = recipe[i]
        used = qps > 0
        unit = float(cost[i])
        perishable = is_perishable(ing["shelf_life_days"].get(i))
        co = unit if perishable else CARRY_COST_SHARE * unit
        per_unit_margin = (margin[used] / qps[used]).dropna()
        shared_margin = (margin[used] / lines[used] / qps[used]).dropna()
        w = (dish_totals.reindex(recipe.index).fillna(0.0) * qps).reindex(per_unit_margin.index)
        if per_unit_margin.empty or w.sum() <= 0:
            # No prices: short and over cost the same, order the median.
            cu = cu_share = co
        else:
            cu = LOST_SALE_SHARE * float(np.average(per_unit_margin, weights=w))
            cu_share = LOST_SALE_SHARE * float(np.average(shared_margin, weights=w.reindex(shared_margin.index)))
        q = cu / (cu + co) if (cu + co) > 0 else 0.5
        pack = float(ing["pack_size"].get(i, np.nan))
        rows[i] = {
            "co": co, "cu": cu, "cu_share": cu_share, "q_star": float(np.clip(q, *Q_BOUNDS)),
            "perishable": perishable, "unit_cost": unit, "pack_size": pack,
        }
    return pd.DataFrame.from_dict(rows, orient="index")


def projected_on_hand(
    counts: pd.DataFrame,
    purchases: pd.DataFrame,
    usage: pd.DataFrame,
    forecast_usage: pd.DataFrame,
    until: pd.Timestamp,
) -> pd.Series:
    """Stock expected on hand at `until` (the target week's Monday), per ingredient.

    latest count + purchases after it - actual usage after it - forecast usage
    after the last actual sales day, floored at 0. Missing when never counted.
    usage / forecast_usage: date, ingredient_id, qty.
    """
    if counts is None or counts.empty:
        return pd.Series(dtype=float)
    c = counts.assign(date=pd.to_datetime(counts["date"]).dt.normalize())
    c = c[c["date"] < until].sort_values("date", kind="stable")
    latest = c.groupby("ingredient_id").last()
    last_actual = pd.to_datetime(usage["date"]).max() if not usage.empty else pd.NaT
    p = purchases.assign(date=pd.to_datetime(purchases["date"])) if purchases is not None and not purchases.empty else None
    out = {}
    for ing, row in latest.iterrows():
        since = row["date"]
        stock = float(row["qty_on_hand"])
        if p is not None:
            mine = p[(p["ingredient_id"] == ing) & (p["date"] > since) & (p["date"] < until)]
            stock += float(mine["qty"].astype(float).sum())
        u = usage[(usage["ingredient_id"] == ing) & (pd.to_datetime(usage["date"]) > since)]
        stock -= float(u["qty"].sum())
        f = forecast_usage[forecast_usage["ingredient_id"] == ing]
        fdates = pd.to_datetime(f["date"])
        keep = (fdates < until) & (fdates > since)
        if pd.notna(last_actual):
            keep &= fdates > last_actual
        stock -= float(f.loc[keep, "qty"].sum())
        out[ing] = max(stock, 0.0)
    return pd.Series(out, dtype=float)


def adaptive_policy(
    on_hand: float, demand: np.ndarray, forecast: np.ndarray, quantile_need: np.ndarray, pack: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Run our order rule through the delivery cycles of a week.

    demand: (n, cycles) realized usage per scenario (or one actual row).
    forecast: (cycles,) point usage per cycle. quantile_need: (cycles,) q* quantile per cycle.
    Returns (orders (n, cycles), end stock (n,), shortage (n,), any stockout (n,)).
    """
    n, cycles = demand.shape
    stock = np.full(n, float(on_hand))
    orders = np.zeros((n, cycles))
    short = np.zeros(n)
    out = np.zeros(n, dtype=bool)
    seen_actual, seen_forecast = np.zeros(n), 0.0
    for c in range(cycles):
        need = np.full(n, quantile_need[c])
        if c > 0 and seen_forecast > 0:
            surprise = seen_actual / seen_forecast
            need = need * (1.0 + ADAPT_WEIGHT * (surprise - 1.0))
        orders[:, c] = ceil_to_pack(need - stock, pack)
        stock = stock + orders[:, c] - demand[:, c]
        missing = np.maximum(-stock, 0.0)
        short += missing
        out |= missing > 1e-9
        stock = np.maximum(stock, 0.0)
        seen_actual = seen_actual + demand[:, c]
        seen_forecast += forecast[c]
    return orders, stock, short, out


def fixed_policy(on_hand: float, demand: np.ndarray, orders: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Given orders per cycle (cycles,) or (n, cycles): (end stock, shortage, any stockout)."""
    n, cycles = demand.shape
    orders = np.broadcast_to(orders, (n, cycles))
    stock = np.full(n, float(on_hand))
    short = np.zeros(n)
    out = np.zeros(n, dtype=bool)
    for c in range(cycles):
        stock = stock + orders[:, c] - demand[:, c]
        missing = np.maximum(-stock, 0.0)
        short += missing
        out |= missing > 1e-9
        stock = np.maximum(stock, 0.0)
    return stock, short, out


def recommend(
    samples: pd.DataFrame,
    shares: pd.DataFrame,
    costs: pd.DataFrame,
    on_hand: pd.Series,
    last_week_usage: pd.Series,
    days: list[int],
) -> pd.DataFrame:
    """One row per ingredient: firm first order, planned later ones, outcomes and the owner-habit comparison.

    samples: (n, ingredients) weekly usage. shares: ingredient x cycle share of the week's usage.
    """
    rows = []
    for i in samples.columns:
        week = samples[i].to_numpy(dtype=float)
        c = costs.loc[i]
        share = shares.loc[i].to_numpy(dtype=float) if i in shares.index else np.full(len(days), 1 / len(days))
        share = share / share.sum() if share.sum() > 0 else np.full(len(days), 1 / len(days))
        demand = week[:, None] * share[None, :]
        point = float(np.median(week)) * share
        need = np.quantile(demand, c["q_star"], axis=0)
        known = i in on_hand.index
        stock_now = float(on_hand[i]) if known else 0.0

        orders, end, short, out = adaptive_policy(stock_now, demand, point, need, c["pack_size"])
        planned = np.median(orders, axis=0)

        habit_total = max(float(last_week_usage.get(i, 0.0)) * OWNER_MARKUP - stock_now, 0.0)
        habit = np.array([ceil_to_pack(habit_total * s, c["pack_size"]) for s in share])
        h_end, h_short, h_out = fixed_policy(stock_now, demand, habit)

        def money(end_stock, shortage):
            waste = float(end_stock.mean()) * c["unit_cost"] if c["perishable"] else 0.0
            # cu_share, not cu: these rows get summed across ingredients.
            return waste, float(shortage.mean()) * c["cu_share"]

        our_waste, our_lost = money(end, short)
        their_waste, their_lost = money(h_end, h_short)
        pack = c["pack_size"]
        rows.append({
            "ingredient_id": i,
            "order_qty": float(planned.sum()),
            "deliveries": [
                {"day": WEEKDAYS[d], "qty": float(q), "firm": k == 0} for k, (d, q) in enumerate(zip(days, planned))
            ],
            "packs": int(round(planned.sum() / pack)) if pack and pack > 0 and not math.isnan(pack) else None,
            "pack_size": None if math.isnan(pack) else pack,
            "on_hand": stock_now if known else None,
            "service_level": c["q_star"],
            "perishable": bool(c["perishable"]),
            "expected_leftover": float(end.mean()),
            "expected_waste_cost": our_waste,
            "expected_lost_margin": our_lost,
            "stockout_risk": float(out.mean()),
            "habit_order_qty": float(habit.sum()),
            "habit_waste_cost": their_waste,
            "habit_lost_margin": their_lost,
            "habit_stockout_risk": float(h_out.mean()),
            "expected_savings": (their_waste + their_lost) - (our_waste + our_lost),
        })
    return pd.DataFrame(rows)


def order_backtest(weeks: list[dict], costs: pd.DataFrame) -> dict | None:
    """Replay past weeks: our adaptive orders vs what the owner actually bought, delivery by delivery.

    weeks: [{week, on_hand: Series, purchased: DataFrame ingredient x cycle,
             demand: DataFrame ingredient x cycle, samples: DataFrame (n, ingredients),
             shares: DataFrame ingredient x cycle}]
    demand is the estimated demand (sales, with stockout days filled by the forecast).
    Perishable stock left at the end of the week counts as waste at unit cost,
    shortages as lost margin.
    """
    if not weeks:
        return None
    rows = []
    for w in weeks:
        for i in w["samples"].columns:
            if i not in costs.index or i not in w["demand"].index:
                continue
            c = costs.loc[i]
            stock = float(w["on_hand"].get(i, 0.0))
            actual = w["demand"].loc[i].to_numpy(dtype=float)[None, :]
            share = w["shares"].loc[i].to_numpy(dtype=float) if i in w["shares"].index else np.ones(actual.shape[1])
            share = share / share.sum() if share.sum() > 0 else np.full(actual.shape[1], 1 / actual.shape[1])
            week = w["samples"][i].to_numpy(dtype=float)
            need = np.quantile(week[:, None] * share[None, :], c["q_star"], axis=0)
            point = float(np.median(week)) * share
            ours, end, short, _ = adaptive_policy(stock, actual, point, need, c["pack_size"])
            bought = (
                w["purchased"].loc[i].reindex(range(actual.shape[1])).fillna(0.0).to_numpy(dtype=float)
                if i in w["purchased"].index else np.zeros(actual.shape[1])
            )
            a_end, a_short, _ = fixed_policy(stock, actual, bought)
            for who, qty, e, s in (("ours", ours.sum(), end[0], short[0]), ("actual", bought.sum(), a_end[0], a_short[0])):
                rows.append({
                    "week": w["week"], "ingredient_id": i, "who": who,
                    "bought_cost": float(qty) * c["unit_cost"],
                    "waste_cost": float(e) * c["unit_cost"] if c["perishable"] else 0.0,
                    "lost_margin": float(s) * c["cu_share"],
                })
    df = pd.DataFrame(rows)
    totals = df.groupby("who")[["bought_cost", "waste_cost", "lost_margin"]].sum()
    weekly = df.groupby(["week", "who"])[["waste_cost", "lost_margin"]].sum().unstack("who")

    def side(who):
        return {k: round(float(totals.loc[who, k]), 2) for k in ("bought_cost", "waste_cost", "lost_margin")}

    ours, actual = side("ours"), side("actual")
    n = len(weeks)
    saved = (actual["waste_cost"] + actual["lost_margin"]) - (ours["waste_cost"] + ours["lost_margin"])
    return {
        "weeks": n,
        "ours": ours,
        "actual": actual,
        "total_savings": round(saved, 2),
        "weekly_savings": round(saved / n, 2),
        "waste_reduction_pct": (
            round((1 - ours["waste_cost"] / actual["waste_cost"]) * 100, 1) if actual["waste_cost"] > 0 else None
        ),
        "by_week": [
            {
                "week": pd.Timestamp(week).date().isoformat(),
                "ours_waste": round(float(r[("waste_cost", "ours")]), 2),
                "actual_waste": round(float(r[("waste_cost", "actual")]), 2),
                "ours_lost": round(float(r[("lost_margin", "ours")]), 2),
                "actual_lost": round(float(r[("lost_margin", "actual")]), 2),
            }
            for week, r in weekly.iterrows()
        ],
    }
