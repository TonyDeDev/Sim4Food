"""Monte Carlo what-if evaluation with inventory-constrained fulfilment."""
from __future__ import annotations

import math

import numpy as np

from sim import replay


def _number(value, default: float = 0.0) -> float:
    """Parse client/dataframe values without letting null or NaN crash a run."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _quantiles(values):
    return {f"p{p}": round(float(np.percentile(values, p)), 2) for p in (10, 50, 90)}


def _recipe_map(dishes: list[dict], recipes: list[dict]) -> dict[str, dict[str, float]]:
    """Return each dish's positive ingredient requirements."""
    result = {dish["id"]: {} for dish in dishes}
    for recipe in recipes:
        quantity = _number(recipe.get("qty_per_serving"))
        if quantity > 0:
            result.setdefault(recipe["dish_id"], {})[recipe["ingredient_id"]] = quantity
    return result


def _integer_requests(demand: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Convert expected dish totals to individual customer requests without bias."""
    whole = np.floor(np.maximum(demand, 0)).astype(int)
    fractions = np.maximum(demand, 0) - whole
    return whole + (rng.random(len(demand)) < fractions).astype(int)


def _fulfil_week(
    demand: np.ndarray,
    dishes: list[dict],
    recipe_map: dict[str, dict[str, float]],
    on_hand: dict[str, float],
    base_mix: np.ndarray,
    rng: np.random.Generator,
    *,
    substitution_rate: float,
    deliveries: dict[str, list[dict]] | None = None,
    shelf_life: dict[str, float | None] | None = None,
    record: dict | None = None,
) -> dict:
    """Serve individual orders, substituting only after a stockout.

    ``demand`` remains the unconstrained first choice. A random order queue
    prevents menu ordering from deciding which dishes consume shared stock.
    ``deliveries`` maps an ingredient to the lots arriving during the week, so
    a perishable can be replenished mid-week instead of only on day zero.
    ``record``, when given, collects the per-order log the animation replays;
    it observes the run and never changes it.
    """
    request_counts = _integer_requests(demand, rng)
    queue = np.repeat(np.arange(len(dishes)), request_counts)
    rng.shuffle(queue)
    shelf_life = shelf_life or {}
    tracked = set(on_hand) | set(deliveries or {})
    # An ingredient a recipe calls for but stock has never heard of reads as
    # zero available, rather than breaking the run.
    for requirements in recipe_map.values():
        tracked.update(requirements)
    # Model stock as dated lots. Opening stock is treated as fresh because
    # upload data has quantities but no lot ages; incoming stock expires
    # shelf_life days after its arrival. ``remaining`` mirrors the lot totals so
    # the per-order availability check is a lookup rather than a re-sum - this
    # loop runs once per customer and dominates the whole simulation.
    lots = {ingredient_id: [] for ingredient_id in tracked}
    remaining = {ingredient_id: 0.0 for ingredient_id in tracked}
    for ingredient_id, quantity in on_hand.items():
        if quantity > 0:
            lots[ingredient_id].append({"qty": quantity, "expires": shelf_life.get(ingredient_id)})
            remaining[ingredient_id] = quantity
    arrivals: dict[int, list[tuple[str, float]]] = {}
    for ingredient_id, scheduled in (deliveries or {}).items():
        for lot in scheduled:
            quantity = _number(lot.get("qty"))
            if quantity > 0:
                arrivals.setdefault(int(lot["day"]), []).append((ingredient_id, quantity))
    used = {ingredient_id: 0.0 for ingredient_id in tracked}
    expired = {ingredient_id: 0.0 for ingredient_id in tracked}
    stockout = {ingredient_id: 0 for ingredient_id in tracked}
    fulfilled = [0] * len(dishes)
    abandoned_by_dish = [0] * len(dishes)
    substitutions = 0
    substitution_attempts = 0
    abandoned = 0
    # Index-addressed recipes and a plain list queue keep numpy scalar lookups
    # out of the inner loop.
    dish_recipes = [tuple(recipe_map[dish["id"]].items()) for dish in dishes]
    order_queue = queue.tolist()
    # How acceptable each substitute is depends only on the dish pair, so build
    # the whole table once rather than on every stockout.
    sub_weights = []
    for requested in dishes:
        row = []
        for idx, candidate in enumerate(dishes):
            same_category = candidate.get("category") and candidate.get("category") == requested.get("category")
            price_distance = abs(float(candidate["price"]) - float(requested["price"])) / max(float(requested["price"]), 1.0)
            row.append(float(base_mix[idx]) * (2.0 if same_category else 1.0) * math.exp(-price_distance))
        sub_weights.append(row)

    def can_make(index: int) -> bool:
        for ingredient_id, quantity in dish_recipes[index]:
            if remaining[ingredient_id] + 1e-9 < quantity:
                return False
        return True

    def consume(index: int) -> None:
        for ingredient_id, quantity in dish_recipes[index]:
            need = quantity
            for lot in lots[ingredient_id]:
                take = lot["qty"] if lot["qty"] < need else need
                lot["qty"] -= take
                need -= take
                if need <= 1e-9:
                    break
            remaining[ingredient_id] -= quantity
            used[ingredient_id] += quantity

    # Orders are spread across the week so stock can expire, and a delayed
    # delivery can land, partway through it. Each day owns the queue slice
    # ``day_starts[day]:day_starts[day + 1]``.
    day_starts = [-(-day * len(order_queue) // 7) for day in range(8)]
    for day in range(7):
        # Lots only age between days, so one sweep per day is enough.
        for ingredient_id, ingredient_lots in lots.items():
            still_fresh = []
            for lot in ingredient_lots:
                if lot["expires"] is not None and day >= lot["expires"]:
                    expired[ingredient_id] += lot["qty"]
                    remaining[ingredient_id] -= lot["qty"]
                    if record is not None and lot["qty"] > 0:
                        record["expiries"].append({
                            "day": day, "ingredient_id": ingredient_id, "qty": round(lot["qty"], 4),
                        })
                else:
                    still_fresh.append(lot)
            lots[ingredient_id] = still_fresh
        # Lots are available from the start of the day they arrive, so a
        # delayed drop leaves the days before it short.
        for ingredient_id, quantity in arrivals.get(day, ()):
            life = shelf_life.get(ingredient_id)
            lots[ingredient_id].append({
                "qty": quantity, "expires": None if life is None else day + life,
            })
            remaining[ingredient_id] += quantity
            if record is not None:
                record["arrivals"].append({
                    "day": day, "ingredient_id": ingredient_id, "qty": round(quantity, 4),
                })

        for position in range(day_starts[day], day_starts[day + 1]):
            served_index = order_queue[position]
            if not can_make(served_index):
                substitution_attempts += 1
                requested_index = served_index
                for ingredient_id, quantity in dish_recipes[requested_index]:
                    if remaining[ingredient_id] + 1e-9 < quantity:
                        stockout[ingredient_id] = 1

                alternatives = [idx for idx in range(len(dishes)) if idx != requested_index and can_make(idx)]
                if alternatives and rng.random() < substitution_rate:
                    # Historical mix is the available preference signal. Same
                    # category and similar price make a dish more acceptable.
                    row = sub_weights[requested_index]
                    weights = [row[idx] for idx in alternatives]
                    total_weight = math.fsum(weights)
                    if total_weight <= 0:
                        # A newly added dish can have no historical sales yet. It
                        # is still a valid substitute, so fall back to an even
                        # choice.
                        served_index = alternatives[int(rng.integers(len(alternatives)))]
                    else:
                        # Inlined weighted draw. np.random.Generator.choice with
                        # p= is orders of magnitude slower per call, and this runs
                        # once per stockout.
                        threshold = rng.random() * total_weight
                        cumulative = 0.0
                        served_index = alternatives[-1]
                        for candidate_index, weight in zip(alternatives, weights):
                            cumulative += weight
                            if cumulative > threshold:
                                served_index = candidate_index
                                break
                    substitutions += 1
                else:
                    abandoned += 1
                    abandoned_by_dish[requested_index] += 1
                    if record is not None:
                        record["orders"].append([day, requested_index, replay.WALKED_OUT])
                    continue

            consume(served_index)
            fulfilled[served_index] += 1
            if record is not None:
                record["orders"].append([day, order_queue[position], served_index])

    unconstrained_usage = {ingredient_id: 0.0 for ingredient_id in tracked}
    for idx, requested in enumerate(request_counts.tolist()):
        for ingredient_id, quantity in dish_recipes[idx]:
            unconstrained_usage[ingredient_id] += requested * quantity
    for ingredient_id, ingredient_lots in lots.items():
        for lot in ingredient_lots:
            if lot["expires"] is not None and lot["expires"] <= 7:
                expired[ingredient_id] += lot["qty"]
                if record is not None and lot["qty"] > 0:
                    record["expiries"].append({
                        "day": 7, "ingredient_id": ingredient_id, "qty": round(lot["qty"], 4),
                    })
                lot["qty"] = 0.0
    leftover = {ingredient_id: sum(lot["qty"] for lot in ingredient_lots)
                for ingredient_id, ingredient_lots in lots.items()}
    return {
        "dish_demand": request_counts.tolist(),
        "dish_fulfilled": fulfilled,
        "ingredient_demand": unconstrained_usage,
        "ingredient_usage": used,
        "ingredient_stockout": stockout,
        "abandoned_by_dish": abandoned_by_dish,
        "substitution_attempts": substitution_attempts,
        "substitutions": substitutions,
        "lost_dish_sales": abandoned,
        "waste_qty": expired,
        "leftover_usable": leftover,
    }


def _round_up_to_pack(quantity: float, pack: float) -> float:
    """Suppliers sell whole packs, so an order has to land on one."""
    return math.ceil(quantity / pack) * pack if pack > 0 else quantity


def _delivery_schedule(target: float, opening_stock: float, shelf_life_days, pack: float) -> list[dict]:
    """Split a week's requirement into lots that arrive before they are needed.

    An ingredient that keeps for fewer than seven days cannot be covered by one
    weekly drop: whatever is bought for the back half of the week expires before
    it is cooked, which is why a single order shows both spoilage and shortages.
    Buying the same weekly volume in shelf-life sized lots removes the
    guaranteed spoilage without lowering coverage.
    """
    window = 7 if shelf_life_days is None else int(np.clip(shelf_life_days, 1, 7))
    daily = max(target, 0.0) / 7
    schedule = []
    for start in range(0, 7, window):
        need = daily * min(window, 7 - start)
        # Only the first lot can draw on what is already on the shelf.
        cover = opening_stock if start == 0 else 0.0
        quantity = _round_up_to_pack(max(0.0, need - cover), pack)
        if quantity > 0:
            schedule.append({"day": start, "qty": round(quantity, 3)})
    return schedule


def _financials(
    fulfilment: dict,
    dishes: list[dict],
    recipe_map: dict[str, dict[str, float]],
    by_ingredient: dict[str, dict],
    ingredients: list[dict],
    *,
    discount_pct: float,
    deal_item: str,
    apply_discount: bool,
) -> dict:
    """Attach one simulated week's money outcomes to its fulfilment record."""
    revenue = 0.0
    food_cost = 0.0
    lost_sales_cost = 0.0
    for idx, dish in enumerate(dishes):
        sold = fulfilment["dish_fulfilled"][idx]
        discounted = apply_discount and dish["id"] == deal_item
        revenue += sold * dish["price"] * (1 - discount_pct / 100 if discounted else 1)
        cost_per_dish = sum(quantity * _number(by_ingredient[ingredient_id].get("unit_cost"))
                            for ingredient_id, quantity in recipe_map[dish["id"]].items())
        food_cost += sold * cost_per_dish
        # A walkout forfeits the margin that dish would have earned.
        lost_sales_cost += fulfilment["abandoned_by_dish"][idx] * max(0.0, dish["price"] - cost_per_dish)
    waste_cost = sum(fulfilment["waste_qty"].get(ingredient["id"], 0) * _number(ingredient.get("unit_cost"))
                     for ingredient in ingredients)
    fulfilment.update({
        "revenue": revenue,
        "food_cost": food_cost,
        "waste_cost": waste_cost,
        "lost_sales_cost": lost_sales_cost,
        "profit": revenue - food_cost - waste_cost - lost_sales_cost,
        "fulfilled_sales": int(sum(fulfilment["dish_fulfilled"])),
        "unconstrained_demand": int(sum(fulfilment["dish_demand"])),
    })
    return fulfilment


_WEEK_METRICS = ("revenue", "food_cost", "profit", "waste_cost", "lost_sales_cost",
                 "unconstrained_demand", "fulfilled_sales", "lost_dish_sales", "substitutions")


def _summarize(runs: list[dict]) -> dict:
    return {metric: _quantiles([run[metric] for run in runs]) for metric in _WEEK_METRICS}


def forecast_demand(calibration_params: dict, scenario: dict, n_runs: int = 300) -> dict:
    """Compare current operations with a demand and inventory scenario.

    Unconstrained demand is retained after a stockout, so unavailable dishes
    are never interpreted as a lack of customer interest.
    """
    dishes = calibration_params["dishes"]
    ingredients = calibration_params["ingredients"]
    recipes = calibration_params["recipes"]
    if not dishes:
        raise ValueError("This restaurant has no menu items to simulate")
    n_runs = int(np.clip(n_runs, 200, 500))
    seed = int(scenario.get("seed", 42))
    rng = np.random.default_rng(seed)
    base_week = {dish["id"]: _number(dish.get("baseline_weekly_demand")) for dish in dishes}
    total_base = sum(base_week.values())
    if total_base <= 0:
        raise ValueError("A non-zero XGBoost or historical dish baseline is required")
    base_mix = np.asarray([base_week[dish["id"]] / total_base for dish in dishes])
    by_ingredient = {ingredient["id"]: ingredient for ingredient in ingredients}
    recipe_map = _recipe_map(dishes, recipes)

    deal_item = str(scenario.get("item_id") or "")
    discount_pct = float(np.clip(_number(scenario.get("discount_pct")), 0, 80))
    holiday = bool(scenario.get("holiday", False))
    social_influence = bool(scenario.get("social_influence", False))
    holiday_lift = float(np.clip(_number(scenario.get("holiday_lift_pct", 20 if holiday else 0)), 0, 150)) / 100
    social_lift = float(np.clip(_number(scenario.get("social_lift_pct", 10 if social_influence else 0)), 0, 100)) / 100
    elasticity = float(np.clip(_number(scenario.get("price_elasticity", 1.25)), 0, 3))
    substitution_rate = float(np.clip(_number(scenario.get("substitution_rate", 0.7)), 0, 1))
    # The owner's current habit: buy a fixed cushion over expected usage and
    # ignore what is already on the shelf. This is the plan to beat.
    habit_multiplier = float(np.clip(_number(scenario.get("habit_multiplier", 1.25)), 1, 3))
    shelf_life = {ingredient["id"]: _number(ingredient.get("shelf_life_days"), default=-1)
                  for ingredient in ingredients}
    shelf_life = {ingredient_id: None if days < 0 else int(days)
                  for ingredient_id, days in shelf_life.items()}

    raw_overrides = scenario.get("stock_overrides") or {}
    stock_overrides = {
        str(ingredient_id): float(np.clip(_number(quantity), 0, 1_000_000))
        for ingredient_id, quantity in raw_overrides.items()
        if str(ingredient_id) in by_ingredient
    }
    scenario_deliveries: dict[str, list[dict]] = {}
    delivery_ingredient_id = str(scenario.get("delivery_ingredient_id") or "")
    delivery_qty = float(np.clip(_number(scenario.get("delivery_qty")), 0, 1_000_000))
    if delivery_ingredient_id in by_ingredient and delivery_qty > 0:
        scenario_deliveries[delivery_ingredient_id] = [{
            "day": int(np.clip(_number(scenario.get("delivery_delay_days")), 0, 6)),
            "qty": delivery_qty,
        }]

    results = {"baseline": [], "scenario": []}
    base_vector = np.asarray([base_week[dish["id"]] for dish in dishes])
    for _ in range(n_runs):
        baseline = rng.poisson(np.maximum(base_vector, 0)).astype(float)
        alternate = baseline.copy()
        if discount_pct and deal_item in base_week:
            target_idx = next(i for i, dish in enumerate(dishes) if dish["id"] == deal_item)
            incremental = rng.poisson(max(0, base_week[deal_item] * elasticity * discount_pct / 100))
            shifted = min(float(incremental) * 0.65, float(alternate.sum() - alternate[target_idx]))
            others = np.delete(alternate, target_idx)
            if others.sum() > 0:
                alternate[np.arange(len(alternate)) != target_idx] -= shifted * others / others.sum()
            alternate[target_idx] += incremental
        if holiday:
            alternate = rng.poisson(np.maximum(alternate * (1 + holiday_lift), 0)).astype(float)
        if social_influence:
            alternate = rng.poisson(np.maximum(alternate * (1 + social_lift), 0)).astype(float)
        results["baseline"].append(baseline)
        results["scenario"].append(alternate)

    metric_runs = {key: [] for key in results}
    current_stock = {ingredient["id"]: _number(ingredient.get("qty_on_hand")) for ingredient in ingredients}
    for key, runs in results.items():
        for demand in runs:
            stock = dict(current_stock)
            if key == "scenario":
                stock.update(stock_overrides)
            fulfilment = _fulfil_week(
                demand, dishes, recipe_map, stock, base_mix, rng,
                substitution_rate=substitution_rate,
                deliveries=scenario_deliveries if key == "scenario" else None,
                shelf_life=shelf_life,
            )
            metric_runs[key].append(_financials(
                fulfilment, dishes, recipe_map, by_ingredient, ingredients,
                discount_pct=discount_pct, deal_item=deal_item, apply_discount=key == "scenario",
            ))

    summary = {}
    for key, runs in metric_runs.items():
        summary[key] = {**_summarize(runs), "ingredients": []}
        for ingredient in ingredients:
            ingredient_id = ingredient["id"]
            unconstrained = [run["ingredient_demand"].get(ingredient_id, 0) for run in runs]
            fulfilled = [run["ingredient_usage"].get(ingredient_id, 0) for run in runs]
            wastes = [run["waste_qty"].get(ingredient_id, 0) for run in runs]
            leftovers = [run["leftover_usable"].get(ingredient_id, 0) for run in runs]
            risk = float(np.mean([run["ingredient_stockout"].get(ingredient_id, 0) for run in runs]))
            uses = [recipe for recipe in recipes if recipe["ingredient_id"] == ingredient_id]
            average_recipe_price = sum(dish["price"] for dish in dishes) / len(dishes)
            usage_per_dish = sum(_number(recipe.get("qty_per_serving")) for recipe in uses) / max(len(uses), 1)
            unit_cost = _number(ingredient.get("unit_cost"))
            underage_cost = max(0, average_recipe_price / max(usage_per_dish, 1e-9) - unit_cost)
            overage_cost = max(0, unit_cost)
            fractile = underage_cost / (underage_cost + overage_cost) if underage_cost + overage_cost else .5
            stock = current_stock[ingredient_id]
            if key == "scenario":
                stock = stock_overrides.get(ingredient_id, stock)
                stock += sum(_number(lot["qty"]) for lot in scenario_deliveries.get(ingredient_id, ()))
            target = float(np.quantile(unconstrained, fractile)) if unconstrained else 0
            pack = _number(ingredient.get("pack_size"))
            life = shelf_life.get(ingredient_id)
            schedule = _delivery_schedule(target, stock, life, pack)
            order = sum(lot["qty"] for lot in schedule)
            if len(schedule) > 1:
                days = ", ".join(f"day {lot['day']}" for lot in schedule)
                action = (f"Order {round(order, 3)} {ingredient['unit']} split across "
                          f"{len(schedule)} drops ({days}) - keeps {life} days")
            elif order > 0:
                action = f"Order {round(order, 3)} {ingredient['unit']}"
            elif risk >= 0.5 and stock > target:
                action = "Reduce opening stock or pause replenishment"
            else:
                action = "No additional order indicated"
            summary[key]["ingredients"].append({
                "ingredient_id": ingredient_id, "name": ingredient["name"], "unit": ingredient["unit"],
                "demand": _quantiles(unconstrained), "fulfilled_usage": _quantiles(fulfilled),
                "demand_mean": round(float(np.mean(unconstrained)), 3) if unconstrained else 0.0,
                "waste": _quantiles(wastes), "waste_cost": round(float(np.median(wastes)) * unit_cost, 2),
                "leftover_usable": _quantiles(leftovers), "shelf_life_days": shelf_life.get(ingredient_id),
                "stockout_probability": round(risk, 4),
                "recommended_order_qty": round(order, 3), "unit_cost": round(unit_cost, 2),
                "target_stock_level": round(target, 3), "opening_stock": round(stock, 3),
                "service_fractile": round(fractile, 4),
                "delivery_schedule": schedule, "delivery_count": len(schedule),
                "recommended_action": action,
            })

    base, alternate = summary["baseline"], summary["scenario"]
    summary["comparison"] = {
        "revenue_delta": round(alternate["revenue"]["p50"] - base["revenue"]["p50"], 2),
        "profit_delta": round(alternate["profit"]["p50"] - base["profit"]["p50"], 2),
        "lost_sales_delta": round(alternate["lost_dish_sales"]["p50"] - base["lost_dish_sales"]["p50"], 2),
        "fulfilled_sales_delta": round(alternate["fulfilled_sales"]["p50"] - base["fulfilled_sales"]["p50"], 2),
        "waste_cost_delta": round(alternate["waste_cost"]["p50"] - base["waste_cost"]["p50"], 2),
        "lost_sales_cost_delta": round(alternate["lost_sales_cost"]["p50"] - base["lost_sales_cost"]["p50"], 2),
        "food_cost_delta": round(alternate["food_cost"]["p50"] - base["food_cost"]["p50"], 2),
        "profit_lift_pct": round((alternate["profit"]["p50"] / base["profit"]["p50"] - 1) * 100, 2) if base["profit"]["p50"] else None,
    }
    baseline_orders = {row["ingredient_id"]: row["recommended_order_qty"] for row in base["ingredients"]}
    for row in alternate["ingredients"]:
        row["baseline_recommended_order_qty"] = baseline_orders.get(row["ingredient_id"], 0)
        row["order_qty_delta"] = round(row["recommended_order_qty"] - row["baseline_recommended_order_qty"], 3)

    # Both ordering plans face the identical what-if demand draws, so the only
    # thing that differs is how much was bought. That is what separates "less
    # waste" from "ran out of food" instead of conflating the two.
    plan_schedules: dict[str, dict[str, list[dict]]] = {"habit": {}, "recommended": {}}
    for row in alternate["ingredients"]:
        ingredient_id = row["ingredient_id"]
        pack = _number(by_ingredient[ingredient_id].get("pack_size"))
        # The habit buys one weekly drop sized off expected usage, ignoring both
        # what is already on the shelf and how long the ingredient keeps.
        habit_qty = _round_up_to_pack(row["demand_mean"] * habit_multiplier, pack)
        if habit_qty > 0:
            plan_schedules["habit"][ingredient_id] = [{"day": 0, "qty": habit_qty}]
        if row["delivery_schedule"]:
            plan_schedules["recommended"][ingredient_id] = row["delivery_schedule"]

    plans = {}
    plan_deliveries: dict[str, dict[str, list[dict]]] = {}
    for plan_name, schedules in plan_schedules.items():
        # A delivery the owner already expects happens under either plan.
        deliveries = {ingredient_id: list(scheduled) for ingredient_id, scheduled in schedules.items()}
        for ingredient_id, scheduled in scenario_deliveries.items():
            deliveries.setdefault(ingredient_id, []).extend(scheduled)
        plan_deliveries[plan_name] = deliveries
        plan_runs = []
        for demand in results["scenario"]:
            stock = dict(current_stock)
            stock.update(stock_overrides)
            plan_runs.append(_financials(
                _fulfil_week(
                    demand, dishes, recipe_map, stock, base_mix, rng,
                    substitution_rate=substitution_rate, deliveries=deliveries, shelf_life=shelf_life,
                ),
                dishes, recipe_map, by_ingredient, ingredients,
                discount_pct=discount_pct, deal_item=deal_item, apply_discount=True,
            ))
        plan_rows = []
        for ingredient in ingredients:
            ingredient_id = ingredient["id"]
            unit_cost = _number(ingredient.get("unit_cost"))
            wastes = [run["waste_qty"].get(ingredient_id, 0) for run in plan_runs]
            schedule = schedules.get(ingredient_id, [])
            ordered = sum(lot["qty"] for lot in schedule)
            plan_rows.append({
                "ingredient_id": ingredient_id, "name": ingredient["name"], "unit": ingredient["unit"],
                "order_qty": round(ordered, 3), "order_cost": round(ordered * unit_cost, 2),
                "delivery_days": [lot["day"] for lot in schedule],
                "waste": _quantiles(wastes), "waste_cost": round(float(np.median(wastes)) * unit_cost, 2),
                "leftover_usable": _quantiles([run["leftover_usable"].get(ingredient_id, 0) for run in plan_runs]),
                "shelf_life_days": shelf_life.get(ingredient_id),
                "stockout_probability": round(float(np.mean(
                    [run["ingredient_stockout"].get(ingredient_id, 0) for run in plan_runs])), 4),
            })
        plans[plan_name] = {
            **_summarize(plan_runs),
            "order_cost": round(sum(row["order_cost"] for row in plan_rows), 2),
            "ingredients": plan_rows,
        }

    habit, recommended = plans["habit"], plans["recommended"]
    demand_p50 = recommended["unconstrained_demand"]["p50"]
    summary["plans"] = plans
    summary["plan_comparison"] = {
        "habit_multiplier": habit_multiplier,
        "waste_cost_saving": round(habit["waste_cost"]["p50"] - recommended["waste_cost"]["p50"], 2),
        "purchase_cost_saving": round(habit["order_cost"] - recommended["order_cost"], 2),
        "lost_sales_cost_change": round(recommended["lost_sales_cost"]["p50"] - habit["lost_sales_cost"]["p50"], 2),
        "profit_gain": round(recommended["profit"]["p50"] - habit["profit"]["p50"], 2),
        # Share of first-choice orders actually served, so a waste cut that
        # quietly starves demand cannot look like a win.
        "service_level_habit": round(habit["fulfilled_sales"]["p50"] / demand_p50, 4) if demand_p50 else None,
        "service_level_recommended": round(recommended["fulfilled_sales"]["p50"] / demand_p50, 4) if demand_p50 else None,
        "served_habit": habit["fulfilled_sales"]["p50"],
        "served_recommended": recommended["fulfilled_sales"]["p50"],
        "demand": demand_p50,
    }
    # One extra week, recorded order by order, is what the animation replays:
    # the scenario draw whose demand sits closest to the median, served under
    # the recommended plan. Recording inside the main loops would slow the hot
    # path and hold hundreds of logs for the one week that gets shown. A fresh
    # generator on the same seed keeps the replay reproducible across runs.
    weekly_totals = np.asarray([float(demand.sum()) for demand in results["scenario"]])
    representative = int(np.argmin(np.abs(weekly_totals - float(np.median(weekly_totals)))))
    replay_stock = dict(current_stock)
    replay_stock.update(stock_overrides)
    record = replay.new_record()
    _fulfil_week(
        results["scenario"][representative], dishes, recipe_map, dict(replay_stock), base_mix,
        np.random.default_rng(seed), substitution_rate=substitution_rate,
        deliveries=plan_deliveries["recommended"], shelf_life=shelf_life, record=record,
    )
    summary["replay"] = replay.build_replay_log(
        record, dishes, ingredients, recipe_map, replay_stock,
        plan="recommended", run_index=representative,
    )
    return {"runs": n_runs, "seed": seed, "scenario": scenario, "calibration": calibration_params.get("calibration", {}), **summary}
