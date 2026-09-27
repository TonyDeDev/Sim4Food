"""Builds the event log of one representative simulation run for the animation.

The animation is a replay, never a source of numbers: every customer, walkout,
substitution, delivery and expiry it draws happened in a real simulated week
under the recommended plan. Nothing in here feeds back into a recommendation.
"""
from __future__ import annotations

WALKED_OUT = -1


def new_record() -> dict:
    """The mutable collector ``sim.forecast._fulfil_week`` appends events to."""
    return {"orders": [], "arrivals": [], "expiries": []}


def build_replay_log(
    record: dict,
    dishes: list[dict],
    ingredients: list[dict],
    recipe_map: dict[str, dict[str, float]],
    opening_stock: dict[str, float],
    *,
    plan: str,
    run_index: int,
    days: int = 7,
) -> dict:
    """Shape one recorded week into the payload the canvas animation replays.

    Orders are ``[day, requested_dish_index, served_dish_index]`` triples, with
    ``-1`` served meaning the guest left rather than take a substitute. Sending
    indices plus one recipe table, rather than a quantity per order, keeps a
    2000-order week to a few tens of kilobytes.
    """
    orders = record.get("orders", [])
    served = substituted = walked_out = 0
    for _, requested, actual in orders:
        if actual == WALKED_OUT:
            walked_out += 1
        elif actual == requested:
            served += 1
        else:
            substituted += 1

    # Only ingredients a dish on this menu actually consumes can pop off the
    # shelf, so the animation never shows a tile that could not move.
    used_ids = {ingredient_id for requirements in recipe_map.values() for ingredient_id in requirements}
    return {
        "plan": plan,
        "run_index": run_index,
        "days": days,
        "dishes": [
            {"id": dish["id"], "name": dish["name"], "price": round(float(dish["price"]), 2)}
            for dish in dishes
        ],
        "ingredients": [
            {
                "id": ingredient["id"],
                "name": ingredient["name"],
                "unit": ingredient["unit"],
                "opening_stock": round(float(opening_stock.get(ingredient["id"], 0.0)), 4),
            }
            for ingredient in ingredients
            if ingredient["id"] in used_ids
        ],
        "recipes": {
            dish["id"]: {
                ingredient_id: round(float(quantity), 4)
                for ingredient_id, quantity in recipe_map.get(dish["id"], {}).items()
            }
            for dish in dishes
        },
        "arrivals": record.get("arrivals", []),
        "expiries": record.get("expiries", []),
        "orders": orders,
        "totals": {
            "orders": len(orders),
            "served_as_ordered": served,
            "substituted": substituted,
            "walked_out": walked_out,
        },
    }
