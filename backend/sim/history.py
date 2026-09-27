"""Point-in-time views of ingredient specs and recipes.

`ingredients` and `recipes` keep their own history: when a versioned value
changes, the old values stay in the table as a row with `valid_to` set, and the
new values become the current row (see db/migrations/001_versioned_rows.sql).
A row was in force for valid_from <= t < valid_to. The very first version of a
row has valid_from = 1900-01-01, so it covers all earlier history.

This module turns those rows into "what was in force at time T" lookups so a
price or recipe change never rewrites history.

Version frames (ids are strings, timestamps are naive UTC, valid_to is
OPEN_END for the current row):
  ingredient versions: ingredient_id, unit_cost, pack_size, shelf_life_days, valid_from, valid_to
  recipe versions: menu_item_id, ingredient_id, qty_per_serving, valid_from, valid_to

With plain current-only frames (no history, or the offline demo CSVs) everything
falls back to the current value, so behaviour is unchanged.

Pure pandas, no DB access.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

OPEN_START = pd.Timestamp("1900-01-01")
OPEN_END = pd.Timestamp("2200-01-01")

INGREDIENT_VERSION_COLUMNS = ["ingredient_id", "unit_cost", "pack_size", "shelf_life_days", "valid_from", "valid_to"]
RECIPE_VERSION_COLUMNS = ["menu_item_id", "ingredient_id", "qty_per_serving", "valid_from", "valid_to"]


def _naive_utc(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, utc=True).dt.tz_localize(None)


def _version_frame(rows: list[dict], columns: list[str], numeric: list[str]) -> pd.DataFrame:
    df = pd.DataFrame([dict(r) for r in rows], columns=columns)
    df["valid_from"] = _naive_utc(df["valid_from"])
    df["valid_to"] = _naive_utc(df["valid_to"]).fillna(OPEN_END)
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def to_ingredient_versions(rows: list[dict]) -> pd.DataFrame:
    """Database rows (all versions of every ingredient) as a version frame."""
    return _version_frame(rows, INGREDIENT_VERSION_COLUMNS, ["unit_cost", "pack_size", "shelf_life_days"])


def to_recipe_versions(rows: list[dict]) -> pd.DataFrame:
    """Database rows (all versions of every recipe line) as a version frame."""
    return _version_frame(rows, RECIPE_VERSION_COLUMNS, ["qty_per_serving"])


def open_recipe_versions(recipes: pd.DataFrame) -> pd.DataFrame:
    """A current-only recipes frame as versions that are always in force."""
    current = recipes[["menu_item_id", "ingredient_id", "qty_per_serving"]]
    return current.assign(valid_from=OPEN_START, valid_to=OPEN_END)[RECIPE_VERSION_COLUMNS]


def open_ingredient_versions(ingredients: pd.DataFrame) -> pd.DataFrame:
    current = ingredients[["ingredient_id", "unit_cost", "pack_size", "shelf_life_days"]]
    return current.assign(valid_from=OPEN_START, valid_to=OPEN_END)[INGREDIENT_VERSION_COLUMNS]


def recipe_versions_of(frames: dict) -> pd.DataFrame:
    """The recipe versions in a frames dict, or the current recipes as always-in-force."""
    versions = frames.get("recipe_versions")
    return versions if versions is not None else open_recipe_versions(frames["recipes"])


def attach_recipes(df: pd.DataFrame, recipes: pd.DataFrame, date_col: str) -> pd.DataFrame:
    """Join df to recipe lines on menu_item_id, keeping the line in force at df[date_col].

    `recipes` may be the plain current frame (no valid_from / valid_to columns),
    in which case every line applies to every date.
    """
    joined = df.merge(recipes, on="menu_item_id")
    if "valid_from" in joined.columns:
        when = pd.to_datetime(joined[date_col])
        joined = joined[(joined["valid_from"] <= when) & (when < joined["valid_to"])]
    return joined


def recipe_stats_asof(
    versions: pd.DataFrame, times: pd.DatetimeIndex, ingredient_ids: list[str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(sum of qty_per_serving, number of dishes) per ingredient, in force at each time."""
    total = pd.DataFrame(0.0, index=times, columns=ingredient_ids)
    count = total.copy()
    for t in times:
        live = versions[(versions["valid_from"] <= t) & (t < versions["valid_to"])]
        g = live.groupby("ingredient_id")["qty_per_serving"].agg(["sum", "count"])
        g = g.reindex(ingredient_ids).fillna(0.0)
        total.loc[t] = g["sum"].values
        count.loc[t] = g["count"].values
    return total, count


def field_versions(versions: pd.DataFrame, field: str) -> pd.DataFrame:
    """Intervals an ingredient field held each value: ingredient_id, value, valid_from, valid_to."""
    out = versions[["ingredient_id", "valid_from", "valid_to"]].copy()
    out["value"] = versions[field].astype(float)
    return out[["ingredient_id", "value", "valid_from", "valid_to"]]


def asof_wide(versions: pd.DataFrame, times: pd.DatetimeIndex, ingredient_ids: list[str]) -> pd.DataFrame:
    """Value in force at each time (rows) for each ingredient (columns); NaN when unset."""
    out = pd.DataFrame(np.nan, index=times, columns=ingredient_ids)
    at = times.values
    for ing, g in versions.groupby("ingredient_id"):
        if ing not in out.columns:
            continue
        g = g.sort_values("valid_from", kind="stable")
        starts, ends, values = g["valid_from"].values, g["valid_to"].values, g["value"].values
        idx = np.searchsorted(starts, at, side="right") - 1
        safe = np.clip(idx, 0, len(g) - 1)
        ok = (idx >= 0) & (at < ends[safe])
        out[ing] = np.where(ok, values[safe], np.nan)
    return out


def price_change_times(versions: pd.DataFrame) -> pd.DataFrame:
    """ingredient_id, effective_at for every version whose unit_cost differs from the one before it."""
    v = versions.sort_values(["ingredient_id", "valid_from"], kind="stable")
    prev = v.groupby("ingredient_id")["unit_cost"].shift(1)
    changed = prev.notna() & (prev != v["unit_cost"])
    return v.loc[changed, ["ingredient_id", "valid_from"]].rename(columns={"valid_from": "effective_at"})


def recipe_change_times(versions: pd.DataFrame) -> pd.DataFrame:
    """ingredient_id, effective_at for every recipe line added, changed or removed after the start."""
    added = versions.loc[versions["valid_from"] > OPEN_START, ["ingredient_id", "valid_from"]]
    ended = versions.loc[versions["valid_to"] < OPEN_END, ["ingredient_id", "valid_to"]]
    return pd.concat(
        [
            added.rename(columns={"valid_from": "effective_at"}),
            ended.rename(columns={"valid_to": "effective_at"}),
        ],
        ignore_index=True,
    )


def days_since_change(
    times: pd.DatetimeIndex,
    ingredient_ids: list[str],
    events: pd.DataFrame | None,
) -> pd.DataFrame:
    """Days from the latest change effective at or before each time; NaN when none yet.

    events: ingredient_id, effective_at (one row per change).
    """
    out = pd.DataFrame(np.nan, index=times, columns=ingredient_ids)
    if events is None or events.empty:
        return out
    at = times.values
    for ing, g in events.groupby("ingredient_id"):
        if ing not in out.columns:
            continue
        eff = np.sort(g["effective_at"].values)
        idx = np.searchsorted(eff, at, side="right") - 1
        days = (at - eff[np.clip(idx, 0, len(eff) - 1)]) / np.timedelta64(1, "D")
        out[ing] = np.where(idx >= 0, np.floor(days), np.nan)
    return out


def value_at(current: float, changes: list[tuple], ts) -> float:
    """Pure-python as-of lookup for one ingredient field (used by the waste report).

    changes: [(effective_at, old_value, new_value)] sorted by effective_at.
    """
    if not changes:
        return current
    if ts < changes[0][0]:
        return changes[0][1]
    value = changes[0][1]
    for effective_at, _old, new in changes:
        if effective_at <= ts:
            value = new
        else:
            break
    return value


def cost_changes(version_rows: list[dict]) -> list[dict]:
    """unit_cost changes derived from ingredient version rows, for the waste report.

    version_rows: [{ingredient_id, unit_cost, valid_from}] for every version of every ingredient.
    Returns [{ingredient_id, old_value, new_value, effective_at}], one per cost change.
    """
    by_ingredient: dict = {}
    for row in version_rows:
        by_ingredient.setdefault(row["ingredient_id"], []).append(row)
    changes = []
    for ingredient_id, rows in by_ingredient.items():
        rows.sort(key=lambda r: r["valid_from"])
        for before, after in zip(rows, rows[1:]):
            if float(before["unit_cost"]) != float(after["unit_cost"]):
                changes.append({
                    "ingredient_id": ingredient_id,
                    "old_value": float(before["unit_cost"]),
                    "new_value": float(after["unit_cost"]),
                    "effective_at": after["valid_from"],
                })
    return changes


def consumption_rows(ingredients: list[dict], sales: list[dict], recipe_rows: list[dict]) -> list[dict]:
    """qty_sold x qty_per_serving per sale, using the recipe line in force on the sale date.

    ingredients: [{id, ...}] (id is the database key, kept as-is in the output)
    sales: [{menu_item_id, date, qty_sold}], recipe_rows: every version of every recipe line.
    """
    if not sales or not recipe_rows:
        return []
    ingredient_key = {str(r["id"]): r["id"] for r in ingredients}
    sales_df = pd.DataFrame([dict(r) for r in sales])
    versions = to_recipe_versions(recipe_rows)
    joined = attach_recipes(sales_df, versions, "date")
    joined["qty"] = joined["qty_sold"] * joined["qty_per_serving"]
    return [
        {"ingredient_id": ingredient_key[ing], "date": d, "qty": q}
        for ing, d, q in zip(joined["ingredient_id"], joined["date"], joined["qty"])
        if ing in ingredient_key
    ]
