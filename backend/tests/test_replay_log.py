import numpy as np

from sim import replay
from sim.forecast import _fulfil_week, _recipe_map, forecast_demand


DISHES = [
    {"id": "chicken_burger", "name": "Chicken burger", "price": 14.0, "category": "burger", "baseline_weekly_demand": 40},
    {"id": "veggie_wrap", "name": "Veggie wrap", "price": 11.0, "category": "wrap", "baseline_weekly_demand": 20},
]
RECIPES = [
    {"dish_id": "chicken_burger", "ingredient_id": "chicken", "qty_per_serving": 1},
    {"dish_id": "chicken_burger", "ingredient_id": "bread", "qty_per_serving": 1},
    {"dish_id": "veggie_wrap", "ingredient_id": "vegetables", "qty_per_serving": 1},
]
INGREDIENTS = [
    {"id": "chicken", "name": "Chicken", "unit": "kg", "unit_cost": 5, "pack_size": 1, "shelf_life_days": 2, "qty_on_hand": 4},
    {"id": "bread", "name": "Bread", "unit": "each", "unit_cost": 1, "pack_size": 1, "qty_on_hand": 40},
    {"id": "vegetables", "name": "Vegetables", "unit": "kg", "unit_cost": 2, "pack_size": 1, "qty_on_hand": 40},
]
PARAMS = {"dishes": DISHES, "ingredients": INGREDIENTS, "recipes": RECIPES, "budget": 28.0, "calibration": {}}


def test_recorded_outcomes_reconcile_with_the_run_that_produced_them():
    """The animation may only show what the simulation actually served."""
    record = replay.new_record()
    recipe_map = _recipe_map(DISHES, RECIPES)
    # Chicken is deliberately short, so walkouts and substitutions both happen.
    result = _fulfil_week(
        np.array([60.0, 10.0]), DISHES, recipe_map, {"chicken": 3, "bread": 40, "vegetables": 40},
        np.array([0.7, 0.3]), np.random.default_rng(11), substitution_rate=0.5,
        shelf_life={"chicken": 2, "bread": None, "vegetables": None}, record=record,
    )
    log = replay.build_replay_log(
        record, DISHES, INGREDIENTS, recipe_map, {"chicken": 3, "bread": 40, "vegetables": 40},
        plan="recommended", run_index=7,
    )

    totals = log["totals"]
    assert totals["walked_out"] == result["lost_dish_sales"]
    assert totals["substituted"] == result["substitutions"]
    assert totals["served_as_ordered"] + totals["substituted"] == sum(result["dish_fulfilled"])
    assert totals["orders"] == len(log["orders"]) == sum(result["dish_demand"])
    # Some guest must actually have left, or this test proves nothing.
    assert totals["walked_out"] > 0


def test_every_recorded_order_is_drawable():
    record = replay.new_record()
    recipe_map = _recipe_map(DISHES, RECIPES)
    _fulfil_week(
        np.array([50.0, 20.0]), DISHES, recipe_map, {"chicken": 10, "bread": 40, "vegetables": 40},
        np.array([0.7, 0.3]), np.random.default_rng(3), substitution_rate=0.8,
        shelf_life={"chicken": 2, "bread": None, "vegetables": None}, record=record,
    )
    log = replay.build_replay_log(
        record, DISHES, INGREDIENTS, recipe_map, {"chicken": 10, "bread": 40, "vegetables": 40},
        plan="recommended", run_index=0,
    )

    for day, requested, served in log["orders"]:
        assert 0 <= day < log["days"]
        assert 0 <= requested < len(log["dishes"])
        # -1 is the guest who left; anything else must name a dish on the menu.
        assert served == replay.WALKED_OUT or 0 <= served < len(log["dishes"])
    # Only ingredients a recipe consumes get a shelf tile, and each needs a unit.
    used = {i for requirements in log["recipes"].values() for i in requirements}
    assert {row["id"] for row in log["ingredients"]} == used
    assert all(row["unit"] for row in log["ingredients"])


def test_forecast_attaches_a_replay_of_the_representative_week():
    result = forecast_demand(PARAMS, {"holiday": True}, 200)
    log = result["replay"]

    assert log["plan"] == "recommended"
    assert 0 <= log["run_index"] < result["runs"]
    assert log["totals"]["orders"] > 0
    # Deliveries the plan schedules have to reach the shelf during the week.
    assert all(0 <= arrival["day"] < log["days"] for arrival in log["arrivals"])
    assert all(arrival["qty"] > 0 for arrival in log["arrivals"])
    # Spoilage may land on the end-of-week sweep, which is day 7 of a 7 day week.
    assert all(0 <= expiry["day"] <= log["days"] for expiry in log["expiries"])
    assert forecast_demand(PARAMS, {"holiday": True}, 200)["replay"] == log


def test_recording_does_not_change_what_the_simulation_reports():
    """A replay is an observer: the week must play out the same either way."""
    recipe_map = _recipe_map(DISHES, RECIPES)
    stock = {"chicken": 5, "bread": 40, "vegetables": 40}
    shelf_life = {"chicken": 2, "bread": None, "vegetables": None}
    kwargs = dict(substitution_rate=0.6, shelf_life=shelf_life)

    without = _fulfil_week(np.array([45.0, 15.0]), DISHES, recipe_map, dict(stock),
                           np.array([0.7, 0.3]), np.random.default_rng(5), **kwargs)
    with_record = _fulfil_week(np.array([45.0, 15.0]), DISHES, recipe_map, dict(stock),
                               np.array([0.7, 0.3]), np.random.default_rng(5),
                               record=replay.new_record(), **kwargs)

    assert without == with_record
