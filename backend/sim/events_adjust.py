"""Explicit deal and holiday lift on top of the normal-week forecast.

A small restaurant has a handful of past event days, far too few for trees to
learn a lift from. So while history is thin the XGBoost model forecasts the
normal week (event days are left out of its training rows, see
train_dish_xgb.select_features), and the event effect is applied here:

    lift = 1 + (mean(actual / baseline) - 1) * n / (n + SHRINK_DAYS)

measured on past uncensored event days of the same kind, shrunk toward 1 when
there are few of them. The owner's expected_lift, when given, wins over the
estimate. A deal's lift is scaled by its discount relative to past deals.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from sim.dish_features import BASELINE, CENSORED, EVENT_DAY, QTY

SHRINK_DAYS = 3.0


def _kind(rows: pd.DataFrame) -> pd.Series:
    """'holiday' for holiday days not tied to a dish-specific deal, else 'deal'."""
    holiday = (rows["holiday_flag"] > 0) & (rows["dish_event_flag"] == 0)
    return pd.Series(np.where(holiday, "holiday", "deal"), index=rows.index)


def estimate_lifts(matrix: pd.DataFrame) -> dict[str, dict]:
    """{kind: {lift, days, discount}} from past event days with an observed demand."""
    past = matrix[
        matrix[EVENT_DAY] & ~matrix[CENSORED] & matrix[QTY].notna() & (matrix[BASELINE] > 0)
    ]
    out = {}
    kinds = _kind(past)
    for kind in ("deal", "holiday"):
        rows = past[kinds == kind]
        n = len(rows)
        if n == 0:
            out[kind] = {"lift": 1.0, "days": 0, "discount": 0.0}
            continue
        raw = float((rows[QTY] / rows[BASELINE]).mean())
        out[kind] = {
            "lift": 1.0 + (raw - 1.0) * n / (n + SHRINK_DAYS),
            "days": int(n),
            "discount": float(rows["event_discount_pct"].mean()),
        }
    return out


def multipliers(rows: pd.DataFrame, lifts: dict[str, dict]) -> tuple[pd.Series, pd.Series]:
    """(multiplier, source) per row; 1.0 and '' on normal days.

    source is 'owner' (expected_lift given), 'history' (estimated) or 'none'
    (an event with no history and no owner estimate).
    """
    mult = pd.Series(1.0, index=rows.index)
    source = pd.Series("", index=rows.index)
    if rows.empty:
        return mult, source
    kinds = _kind(rows)
    for idx in rows.index[rows[EVENT_DAY].to_numpy(dtype=bool)]:
        r = rows.loc[idx]
        if r["event_expected_lift"] > 0:
            mult[idx], source[idx] = 1.0 + float(r["event_expected_lift"]), "owner"
            continue
        info = lifts.get(kinds[idx], {"lift": 1.0, "days": 0, "discount": 0.0})
        if info["days"] == 0:
            source[idx] = "none"
            continue
        lift = info["lift"]
        if kinds[idx] == "deal" and info["discount"] > 0 and r["event_discount_pct"] > 0:
            lift = 1.0 + (lift - 1.0) * float(r["event_discount_pct"]) / info["discount"]
        mult[idx], source[idx] = max(lift, 0.0), "history"
    return mult, source
