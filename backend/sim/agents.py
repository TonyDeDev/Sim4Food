"""Small rule-based customer agents used by the what-if simulator.

The first production slice represents customer heterogeneity as vectorized
segment draws. It is deterministic for a supplied RNG and avoids creating
hundreds of heavyweight Python objects per Monte Carlo run.
"""
from __future__ import annotations

import numpy as np


def simulate_day(agents, date, events, rng) -> dict:
    """Choose dishes for one day from preference, price, budget and event rules.

    ``agents`` contains dish names/prices and customer segment settings; returns
    a dish-count mapping and the simulated number of visits.
    """
    dishes = agents["dishes"]
    customers = max(0, int(rng.poisson(agents["daily_customers"])))
    if not dishes or customers == 0:
        return {"demand": {}, "visits": customers}
    prices = np.asarray([d["price"] for d in dishes], dtype=float)
    prefs = np.asarray(agents["preferences"], dtype=float)
    sensitivity = rng.lognormal(mean=-0.15, sigma=0.45, size=customers)
    budgets = rng.lognormal(mean=np.log(max(agents["budget"], 1)), sigma=0.35, size=customers)
    logits = prefs[None, :] - sensitivity[:, None] * np.log1p(prices[None, :] / 10)
    discounts = np.asarray(agents.get("discounts", np.zeros(len(dishes))), dtype=float)
    logits += discounts[None, :]
    logits -= logits.max(axis=1, keepdims=True)
    probs = np.exp(logits)
    probs /= probs.sum(axis=1, keepdims=True)
    chosen = np.empty(customers, dtype=int)
    for i in range(customers):
        affordable = prices <= budgets[i]
        p = probs[i] * affordable
        if p.sum() <= 0:
            chosen[i] = int(np.argmin(prices))
        else:
            chosen[i] = int(rng.choice(len(dishes), p=p / p.sum()))
    counts = np.bincount(chosen, minlength=len(dishes))
    return {"demand": {d["id"]: int(counts[i]) for i, d in enumerate(dishes)}, "visits": customers}
