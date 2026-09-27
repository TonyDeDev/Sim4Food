import numpy as np

from sim.forecast import _delivery_schedule, _fulfil_week, _recipe_map, forecast_demand


DISHES = [
    {"id": "chicken_burger", "name": "Chicken burger", "price": 14.0, "category": "burger", "baseline_weekly_demand": 30},
    {"id": "chicken_wrap", "name": "Chicken wrap", "price": 13.0, "category": "wrap", "baseline_weekly_demand": 30},
    {"id": "veggie_wrap", "name": "Veggie wrap", "price": 11.0, "category": "wrap", "baseline_weekly_demand": 10},
]
RECIPES = [
    {"dish_id": "chicken_burger", "ingredient_id": "chicken", "qty_per_serving": 1},
    {"dish_id": "chicken_burger", "ingredient_id": "bread", "qty_per_serving": 1},
    {"dish_id": "chicken_wrap", "ingredient_id": "chicken", "qty_per_serving": 1},
    {"dish_id": "chicken_wrap", "ingredient_id": "tortilla", "qty_per_serving": 1},
    {"dish_id": "veggie_wrap", "ingredient_id": "vegetables", "qty_per_serving": 1},
    {"dish_id": "veggie_wrap", "ingredient_id": "tortilla", "qty_per_serving": 1},
]
INGREDIENTS = [
    {"id": "chicken", "name": "Chicken", "unit": "kg", "unit_cost": 5, "pack_size": 1, "qty_on_hand": 2},
    {"id": "bread", "name": "Bread", "unit": "each", "unit_cost": 1, "pack_size": 1, "qty_on_hand": 20},
    {"id": "tortilla", "name": "Tortilla", "unit": "each", "unit_cost": 1, "pack_size": 1, "qty_on_hand": 20},
    {"id": "vegetables", "name": "Vegetables", "unit": "kg", "unit_cost": 2, "pack_size": 1, "qty_on_hand": 20},
]


def test_shared_ingredient_stockout_substitutes_and_preserves_unconstrained_demand():
    result = _fulfil_week(
        np.array([3.0, 3.0, 0.0]), DISHES, _recipe_map(DISHES, RECIPES),
        {ingredient["id"]: ingredient["qty_on_hand"] for ingredient in INGREDIENTS},
        np.array([0.4, 0.4, 0.2]), np.random.default_rng(4), substitution_rate=1.0,
    )

    assert result["dish_demand"] == [3, 3, 0]  # first choice is never erased
    assert result["ingredient_demand"]["chicken"] == 6
    assert result["ingredient_usage"]["chicken"] == 2  # burger and wrap share it
    assert sum(result["dish_fulfilled"]) == 6
    assert result["substitutions"] == 4
    assert result["lost_dish_sales"] == 0
    assert result["ingredient_stockout"]["chicken"] == 1


def test_stock_override_changes_fulfilled_sales_without_relabeling_demand():
    params = {"dishes": DISHES, "ingredients": INGREDIENTS, "recipes": RECIPES}
    result = forecast_demand(params, {"stock_overrides": {"chicken": 0}, "substitution_rate": 0, "seed": 3}, 200)

    assert result["scenario"]["unconstrained_demand"]["p50"] > result["scenario"]["fulfilled_sales"]["p50"]
    chicken = next(row for row in result["scenario"]["ingredients"] if row["ingredient_id"] == "chicken")
    assert chicken["demand"]["p50"] > chicken["fulfilled_usage"]["p50"]
    assert chicken["stockout_probability"] == 1.0


def test_shelf_life_shorter_than_a_week_is_split_into_several_drops():
    perishable = _delivery_schedule(target=70, opening_stock=0, shelf_life_days=3, pack=0)
    keeps = _delivery_schedule(target=70, opening_stock=0, shelf_life_days=30, pack=0)

    # A 3-day ingredient cannot be covered by one weekly drop without spoiling.
    assert [lot["day"] for lot in perishable] == [0, 3, 6]
    assert sum(lot["qty"] for lot in perishable) == 70
    # Anything that outlasts the week still arrives once.
    assert [lot["day"] for lot in keeps] == [0]
    assert keeps[0]["qty"] == 70


def test_delivery_schedule_nets_off_stock_already_on_the_shelf():
    schedule = _delivery_schedule(target=70, opening_stock=10, shelf_life_days=30, pack=0)

    assert schedule == [{"day": 0, "qty": 60}]


def test_scheduled_lot_is_unavailable_before_the_day_it_arrives():
    recipe_map = _recipe_map(DISHES, RECIPES)
    late = _fulfil_week(
        np.array([7.0, 0.0, 0.0]), DISHES, recipe_map, {"chicken": 0.0, "bread": 7.0},
        np.array([1.0, 0.0, 0.0]), np.random.default_rng(1), substitution_rate=0.0,
        deliveries={"chicken": [{"day": 6, "qty": 7.0}]},
    )
    early = _fulfil_week(
        np.array([7.0, 0.0, 0.0]), DISHES, recipe_map, {"chicken": 0.0, "bread": 7.0},
        np.array([1.0, 0.0, 0.0]), np.random.default_rng(1), substitution_rate=0.0,
        deliveries={"chicken": [{"day": 0, "qty": 7.0}]},
    )

    assert early["dish_fulfilled"][0] == 7
    assert late["dish_fulfilled"][0] < 7  # the week is mostly over before it lands
    assert late["lost_dish_sales"] > 0


def test_recommended_plan_cuts_waste_without_losing_service_on_perishables():
    dishes = [{"id": "salad", "name": "Salad", "price": 12.0, "category": "salad",
               "baseline_weekly_demand": 70}]
    recipes = [{"dish_id": "salad", "ingredient_id": "greens", "qty_per_serving": 1.0}]
    # Greens spoil in 2 days, so one weekly order must both spoil and run short.
    ingredients = [{"id": "greens", "name": "Greens", "unit": "kg", "unit_cost": 3.0,
                    "pack_size": 0, "shelf_life_days": 2, "qty_on_hand": 0}]

    result = forecast_demand({"dishes": dishes, "ingredients": ingredients, "recipes": recipes},
                             {"seed": 11}, 200)
    habit, recommended = result["plans"]["habit"], result["plans"]["recommended"]
    comparison = result["plan_comparison"]

    assert recommended["waste_cost"]["p50"] < habit["waste_cost"]["p50"]
    assert comparison["service_level_recommended"] > comparison["service_level_habit"]
    assert comparison["waste_cost_saving"] > 0
    # The gain comes from splitting the week, not from buying more food.
    assert recommended["order_cost"] <= habit["order_cost"]
    greens = next(row for row in recommended["ingredients"] if row["ingredient_id"] == "greens")
    assert len(greens["delivery_days"]) > 1
