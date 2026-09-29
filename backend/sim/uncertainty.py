"""Monte Carlo forecast distribution from out-of-sample residuals.

The XGBoost forecast is one number per dish and week. Its uncertainty comes
from how wrong earlier out-of-sample forecasts were (sim/forecast_backtest.py),
resampled so that the structure of those errors is kept:

    log(actual / predicted) for dish d in week w  =  week effect  +  dish noise

- The week effect is shared by every dish in a week (a busy week runs high for
  everything at once), so ingredients that share dishes move together, and the
  total is not made artificially certain by adding up independent errors.
- Dish noise is drawn from the dish's own residuals when it has enough of them,
  else from all dishes pooled.

Each Monte Carlo draw multiplies every dish forecast by exp(scale x (week effect +
dish noise)) and converts dishes to ingredients with the recipes, giving usage
samples for every ingredient. `scale` widens or narrows the spread so that, on
past weeks, P10 to P90 contained the actual about 80% of the time. It is fit
out of sample: the scale used to score a week only sees earlier weeks.

The samples give any quantile, which the order recommendation needs (the
newsvendor quantile is rarely 0.5 or 0.9).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

from sim.dish_features import CENSORED, QTY

EPS = 0.5  # servings, keeps log ratios finite for tiny dish-weeks
N_SAMPLES = 1000
SEED = 7
TARGET_COVERAGE = 0.8
MIN_PER_DISH = 3
MIN_PRIOR_WEEKS = 2
MIN_CALIBRATION_WEEKS = 8  # below this the coverage estimate is too coarse to trust on its own
DEFAULT_SCALE = 1.0  # the raw out-of-sample residual spread, uncalibrated
SMALL_SAMPLE_BOUNDS = (1.0, 2.0)
SCALE_GRID = np.round(np.arange(0.5, 3.0001, 0.05), 2)
EVENT_LOG_SD = 0.15  # extra spread on dishes whose forecast carries an event lift
QUANTILES = (0.1, 0.5, 0.9)


@dataclass
class Residuals:
    week_effects: np.ndarray
    noise: dict[str, np.ndarray]
    pooled: np.ndarray


@dataclass
class Evaluation:
    week: pd.Timestamp
    log_mult: np.ndarray  # (N_SAMPLES, dishes)
    dish_totals: pd.Series  # predicted servings per dish for the week
    recipe: pd.DataFrame  # dishes x ingredients
    actual: pd.Series  # actual usage per ingredient


def dish_week_residuals(dish_bt: pd.DataFrame, pred_col: str = "xgboost") -> pd.DataFrame:
    """forecast_week, menu_item_id, log_ratio, pred over uncensored dish-days."""
    rows = dish_bt[~dish_bt[CENSORED] & dish_bt[pred_col].notna() & dish_bt[QTY].notna()]
    g = rows.groupby(["forecast_week", "menu_item_id"])[[QTY, pred_col]].sum()
    g = g[g[pred_col] > 0]
    out = pd.DataFrame({"log_ratio": np.log((g[QTY] + EPS) / (g[pred_col] + EPS)), "pred": g[pred_col]})
    return out.reset_index()


def fit_residuals(res: pd.DataFrame) -> Residuals | None:
    if res.empty:
        return None
    week = res.groupby("forecast_week").apply(
        lambda g: float(np.average(g["log_ratio"], weights=g["pred"])), include_groups=False
    )
    noise = res["log_ratio"] - res["forecast_week"].map(week)
    res = res.assign(noise=noise.values)
    by_dish = {d: g["noise"].to_numpy() for d, g in res.groupby("menu_item_id") if len(g) >= MIN_PER_DISH}
    return Residuals(week.to_numpy(), by_dish, res["noise"].to_numpy())


def _dish_rng(seed: int, dish: str) -> np.random.Generator:
    """An independent draw stream per dish, keyed by the dish rather than its position.

    Drawing every dish from one shared stream makes the answer depend on the
    order the menu happens to be listed in: the k-th dish consumes the k-th
    block of the stream, so re-sorting the menu re-draws every dish and moves
    every band, order quantity and saving. Keying the stream to the dish id
    makes a dish's draw depend only on that dish.
    """
    digest = hashlib.blake2b(str(dish).encode(), digest_size=8).digest()
    return np.random.default_rng([seed, int.from_bytes(digest, "big")])


def draw_log_multipliers(resid: Residuals | None, dishes: list[str], n: int = N_SAMPLES, seed: int = SEED) -> np.ndarray:
    """(n, len(dishes)) draws of week effect + dish noise; all zeros without residuals."""
    if resid is None:
        return np.zeros((n, len(dishes)))
    week = np.random.default_rng(seed).choice(resid.week_effects, n)
    noise = [_dish_rng(seed, d).choice(resid.noise.get(d, resid.pooled), n) for d in dishes]
    return week[:, None] + (np.column_stack(noise) if dishes else np.zeros((n, 0)))


def recipe_matrix(recipes: pd.DataFrame, dishes: list[str], at: pd.Timestamp | None = None) -> pd.DataFrame:
    """qty_per_serving as a dishes x ingredients matrix, lines in force at `at` (default: current)."""
    r = recipes
    if "valid_to" in r.columns:
        if at is None:
            r = r[r["valid_to"] == r["valid_to"].max()] if len(r) else r
        else:
            r = r[(r["valid_from"] <= at) & (at < r["valid_to"])]
    wide = r.pivot_table(index="menu_item_id", columns="ingredient_id", values="qty_per_serving", aggfunc="sum")
    return wide.reindex(index=dishes).fillna(0.0)


def usage_samples(dish_totals: pd.Series, log_mult: np.ndarray, scale: float, recipe: pd.DataFrame) -> pd.DataFrame:
    """(n, ingredients) usage samples. `scale` widens the draws around their median, never the bias."""
    center = np.median(log_mult, axis=0, keepdims=True) if len(log_mult) else 0.0
    dish_qty = np.exp(center + scale * (log_mult - center)) * dish_totals.to_numpy(dtype=float)[None, :]
    return pd.DataFrame(dish_qty @ recipe.to_numpy(), columns=recipe.columns)


def expanding_evaluations(dish_bt: pd.DataFrame, recipes: pd.DataFrame) -> list[Evaluation]:
    """One evaluation per backtest week, residuals from earlier weeks only."""
    weeks = sorted(dish_bt["forecast_week"].unique())
    evals = []
    for i, week in enumerate(weeks):
        if i < MIN_PRIOR_WEEKS:
            continue
        resid = fit_residuals(dish_week_residuals(dish_bt[dish_bt["forecast_week"] < week]))
        rows = dish_bt[(dish_bt["forecast_week"] == week) & ~dish_bt[CENSORED]]
        totals = rows.groupby("menu_item_id")["xgboost"].sum()
        dishes = list(totals.index)
        recipe = recipe_matrix(recipes, dishes, at=pd.Timestamp(week))
        actual = rows.groupby("menu_item_id")[QTY].sum().reindex(dishes).fillna(0.0) @ recipe
        evals.append(Evaluation(pd.Timestamp(week), draw_log_multipliers(resid, dishes, seed=SEED + i), totals, recipe, actual))
    return evals


def _bands(ev: Evaluation, scale: float) -> pd.DataFrame:
    q = usage_samples(ev.dish_totals, ev.log_mult, scale, ev.recipe).quantile(list(QUANTILES))
    return pd.DataFrame(
        {"actual": ev.actual, "p10": q.loc[0.1], "p50": q.loc[0.5], "p90": q.loc[0.9]}
    ).assign(forecast_week=ev.week)


def _coverage(evals: list[Evaluation], scale: float) -> float:
    banded = pd.concat([_bands(ev, scale) for ev in evals])
    return float(((banded["actual"] >= banded["p10"]) & (banded["actual"] <= banded["p90"])).mean())


def _crossing(coverage: np.ndarray, target: float) -> float:
    """Scale at which coverage first reaches `target`, linearly interpolated.

    Coverage rises with scale, but only in steps of 1/n: with a handful of
    backtest weeks several grid points tie for "closest to target", and picking
    the argmin among them turns rounding noise into a band width - the same
    data answering 1.55 or 1.35 depending on how the dishes happened to sort.
    Interpolating between the two grid points that bracket the crossing makes
    the scale a continuous function of the coverage curve instead.
    """
    reached = np.flatnonzero(coverage >= target)
    if not len(reached):
        return float(SCALE_GRID[-1])
    hi = int(reached[0])
    if hi == 0:
        return float(SCALE_GRID[0])
    lo = hi - 1
    span = coverage[hi] - coverage[lo]
    fraction = (target - coverage[lo]) / span if span > 0 else 0.0
    return float(SCALE_GRID[lo] + fraction * (SCALE_GRID[hi] - SCALE_GRID[lo]))


def fit_scale(evals: list[Evaluation], target: float = TARGET_COVERAGE) -> float:
    """Spread multiplier whose P10-P90 covers `target` of past weeks; DEFAULT_SCALE without evals.

    Under MIN_CALIBRATION_WEEKS the coverage is measured on so few weeks (and
    the ingredients within a week share one week effect, so they are far from
    independent) that the fit is bounded rather than taken at face value: it
    may not narrow the raw residual spread, nor inflate it beyond doubling.
    """
    if not evals:
        return DEFAULT_SCALE
    coverage = np.array([_coverage(evals, s) for s in SCALE_GRID])
    scale = _crossing(coverage, target)
    if len(evals) >= MIN_CALIBRATION_WEEKS:
        return scale
    return float(np.clip(scale, *SMALL_SAMPLE_BOUNDS))


def interval_metrics(banded: pd.DataFrame, level: float = 0.8) -> dict:
    """Coverage, relative Winkler interval score and relative pinball losses (lower is better)."""
    y, lo, mid, hi = (banded[c].astype(float) for c in ("actual", "p10", "p50", "p90"))
    alpha = 1 - level
    below, above = y < lo, y > hi
    winkler = (hi - lo) + (2 / alpha) * ((lo - y) * below + (y - hi) * above)
    denom = y.abs().where(y.abs() > 0)

    def pinball(q, pred):
        diff = y - pred
        return np.maximum(q * diff, (q - 1) * diff)

    return {
        "inside_p10_p90": round(float(1 - below.mean() - above.mean()), 3),
        "below_p10": round(float(below.mean()), 3),
        "above_p90": round(float(above.mean()), 3),
        "n": int(len(banded)),
        "relative_interval_score": round(float((winkler / denom).mean()), 4),
        "relative_pinball": round(
            float(np.mean([(pinball(q, p) / denom).mean() for q, p in ((0.1, lo), (0.5, mid), (0.9, hi))])), 4
        ),
    }


def score_bands(evals: list[Evaluation], target: float = TARGET_COVERAGE) -> tuple[pd.DataFrame, dict]:
    """Out-of-sample band quality: each week is scored with a scale fit on earlier weeks only."""
    if not evals:
        raise ValueError("Not enough backtest weeks to score bands")
    parts = [_bands(ev, fit_scale(evals[:k], target)) for k, ev in enumerate(evals)]
    banded = pd.concat(parts).rename_axis("ingredient_id").reset_index()
    return banded, interval_metrics(banded)


def forecast_samples(
    dish_bt: pd.DataFrame | None,
    recipes: pd.DataFrame,
    dish_totals: pd.Series,
    horizon_weeks: int = 1,
    event_dishes: set[str] | None = None,
    evals: list[Evaluation] | None = None,
) -> tuple[pd.DataFrame, float]:
    """(usage samples per ingredient, scale) for a live forecast.

    The spread grows with the horizon (x sqrt(weeks ahead), residuals are
    one-week-ahead errors) and dishes with an event lift get EVENT_LOG_SD extra.
    """
    dishes = list(dish_totals.index)
    recipe = recipe_matrix(recipes, dishes)
    if dish_bt is None or dish_bt.empty:
        return usage_samples(dish_totals, np.zeros((N_SAMPLES, len(dishes))), 1.0, recipe), 1.0
    evals = evals if evals is not None else expanding_evaluations(dish_bt, recipes)
    scale = fit_scale(evals)
    log_mult = draw_log_multipliers(fit_residuals(dish_week_residuals(dish_bt)), dishes)
    if event_dishes:
        rng = np.random.default_rng(SEED + 1)
        cols = [i for i, d in enumerate(dishes) if d in event_dishes]
        log_mult[:, cols] += rng.normal(0.0, EVENT_LOG_SD / max(scale, 1e-9), (len(log_mult), len(cols)))
    return usage_samples(dish_totals, log_mult, scale * np.sqrt(horizon_weeks), recipe), scale
