import asyncio
from datetime import date
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, UploadFile
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app import db, insights, repository
from app.auth import get_current_user_id, verify_restaurant_owner
from app.config import settings
from sim import backtest, forecast, forecast_store, generator, home_summary, ingest, inventory, waste
from sim.dataset import load_frames
from sim.forecast_payload import build_forecast_payload


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    yield
    await db.disconnect()


app = FastAPI(title="SwarmStock API", lifespan=lifespan)

# No longer load-bearing for the deployed app once the browser reaches this
# backend only through Next.js's /py/* proxy (server-to-server calls aren't
# subject to browser CORS at all). Kept for local-dev convenience (hitting
# this backend directly with a browser tool) and any future direct
# cross-origin browser client.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(insights.router)


@app.get("/api/demo")
async def get_demo():
    return generator.generate_demo_dataset()


@app.post("/api/upload")
async def post_upload(
    restaurant_id: str, file_type: str, file: UploadFile, user_id: str = Depends(get_current_user_id)
):
    await verify_restaurant_owner(restaurant_id, user_id)

    raw = await file.read()
    rows = ingest.parse_csv_rows(raw)

    validation = ingest.validate_upload(file_type, rows)
    if validation["status"] != "ok":
        return validation

    persisted = await repository.persist_upload(db.get_pool(), restaurant_id, file_type, file.filename, rows)
    return {**validation, **persisted}


@app.get("/api/uploads")
async def get_uploads(restaurant_id: str, user_id: str = Depends(get_current_user_id)):
    await verify_restaurant_owner(restaurant_id, user_id)
    return await repository.get_upload_status(db.get_pool(), restaurant_id)


@app.get("/api/waste")
async def get_waste(restaurant_id: str, user_id: str = Depends(get_current_user_id)):
    await verify_restaurant_owner(restaurant_id, user_id)
    return await waste.compute_waste(restaurant_id)


@app.get("/api/inventory")
async def get_inventory(restaurant_id: str, user_id: str = Depends(get_current_user_id)):
    await verify_restaurant_owner(restaurant_id, user_id)
    return await inventory.compute_inventory(restaurant_id)


@app.get("/api/menu")
async def get_menu(restaurant_id: str, user_id: str = Depends(get_current_user_id)):
    await verify_restaurant_owner(restaurant_id, user_id)
    async with db.get_pool().acquire() as conn:
        rows = await conn.fetch(
            "SELECT id::text AS id, name, price::float8 AS price FROM menu_items "
            "WHERE restaurant_id = $1 ORDER BY name", restaurant_id,
        )
        ingredient_rows = await conn.fetch(
            "SELECT i.id::text AS id, i.name, i.unit, COALESCE(ic.qty_on_hand, 0)::float8 AS qty_on_hand "
            "FROM ingredients i LEFT JOIN inventory_current ic "
            "ON ic.ingredient_id = i.id AND ic.restaurant_id = i.restaurant_id "
            "WHERE i.restaurant_id = $1 AND i.current_id IS NULL ORDER BY i.name", restaurant_id,
        )
    return {"menu": [dict(row) for row in rows], "ingredients": [dict(row) for row in ingredient_rows]}


@app.get("/api/home-summary")
async def get_home_summary(restaurant_id: str, user_id: str = Depends(get_current_user_id)):
    await verify_restaurant_owner(restaurant_id, user_id)
    return await home_summary.compute_home_summary(restaurant_id)


@app.post("/api/simulate")
async def post_simulate(restaurant_id: str, scenario: dict, user_id: str = Depends(get_current_user_id)):
    await verify_restaurant_owner(restaurant_id, user_id)
    frames = await load_frames(restaurant_id)
    if frames["sales"].empty:
        raise HTTPException(status_code=400, detail="Upload POS sales before running a simulation")
    pool = db.get_pool()
    async with pool.acquire() as conn:
        menu_rows = await conn.fetch(
            "SELECT id::text AS id, name, price::float8 AS price, category FROM menu_items "
            "WHERE restaurant_id = $1 ORDER BY name", restaurant_id,
        )
        stock_rows = await conn.fetch(
            "SELECT ingredient_id::text AS ingredient_id, qty_on_hand::float8 AS qty_on_hand "
            "FROM inventory_current WHERE restaurant_id = $1", restaurant_id,
        )
        profile = await conn.fetchrow(
            "SELECT daily_customers_estimate::float8 AS daily_customers_estimate, segments "
            "FROM customer_profiles WHERE restaurant_id = $1", restaurant_id,
        )
    menus = [dict(r) for r in menu_rows]
    sales = frames["sales"].copy()
    sales["item_id"] = sales["menu_item_id"].astype(str)
    historical_item_totals = sales.groupby("item_id")["qty_sold"].sum()
    item_factor = 7 / max(1, sales["date"].nunique())
    stock = {r["ingredient_id"]: float(r["qty_on_hand"]) for r in stock_rows}
    ingredients = frames["ingredients"].copy()
    ingredients = ingredients.merge(
        __import__("pandas").DataFrame([{"ingredient_id": k, "qty_on_hand": v} for k, v in stock.items()]),
        on="ingredient_id", how="left",
    ) if stock else ingredients.assign(qty_on_hand=0.0)
    dish_specs = []
    for menu in menus:
        hist_weekly = float(historical_item_totals.get(menu["id"], 0)) * item_factor
        dish_specs.append({"id": menu["id"], "name": menu["name"], "price": float(menu["price"]),
                           "category": menu["category"], "baseline_weekly_demand": hist_weekly})
    # Forecast ingredient totals (XGBoost) anchor the overall weekly scale.
    latest = await forecast_store.get_latest_run(pool, restaurant_id)
    payload = ((latest or {}).get("forecast") or {}).get("forecast") or {}
    forecast_by_ingredient = {r["ingredient_id"]: r["forecast"].get("point")
                              for r in payload.get("ingredients", []) if r.get("forecast")}
    forecast_scale = []
    for ingredient_id, value in forecast_by_ingredient.items():
        historical_usage = 0.0
        for recipe in frames["recipes"].to_dict("records"):
            if recipe["ingredient_id"] == ingredient_id:
                historical_usage += historical_item_totals.get(recipe["menu_item_id"], 0) * float(recipe["qty_per_serving"]) * item_factor
        if historical_usage > 0 and value is not None:
            forecast_scale.append(float(value) / historical_usage)
    scale = float(__import__("numpy").median(forecast_scale)) if forecast_scale else 1.0
    for dish in dish_specs:
        dish["baseline_weekly_demand"] *= scale
    # Reconcile dish-level means to the XGBoost ingredient forecast without
    # changing their POS-calibrated mix. A robust common scale preserves the
    # item demand shares while bringing recipe usage onto the forecast scale.
    if forecast_scale:
        for ingredient_id, target_usage in forecast_by_ingredient.items():
            if target_usage is None:
                continue
            predicted_usage = sum(
                dish["baseline_weekly_demand"] * float(recipe["qty_per_serving"])
                for recipe in frames["recipes"].to_dict("records")
                if recipe["ingredient_id"] == ingredient_id
                for dish in dish_specs if dish["id"] == recipe["menu_item_id"]
            )
            if predicted_usage > 0:
                # Ingredient targets differ by mix, so only use them to inform
                # overall level, not independently distort each dish.
                scale_hint = float(target_usage) / predicted_usage
                if 0.5 <= scale_hint <= 2:
                    scale = scale * scale_hint
                    for dish in dish_specs:
                        dish["baseline_weekly_demand"] *= scale_hint
                    break
    ing_specs = []
    for row in ingredients.to_dict("records"):
        ing_specs.append({"id": row["ingredient_id"], "name": row["name"], "unit": row["unit"],
            "unit_cost": float(row["unit_cost"]), "pack_size": float(row.get("pack_size") or 0),
            "shelf_life_days": row.get("shelf_life_days"),
            "qty_on_hand": float(row.get("qty_on_hand") or 0), "unit_price": 0.0})
    recipe_specs = [{"dish_id": r["menu_item_id"], "ingredient_id": r["ingredient_id"],
                     "qty_per_serving": float(r["qty_per_serving"])} for r in frames["recipes"].to_dict("records")]
    profile_value = dict(profile) if profile else {}
    avg_budget = float(profile_value.get("daily_customers_estimate") or 28.0)
    if avg_budget <= 0:
        avg_budget = 28.0
    calibration = {"dish_mix_source": "historical POS sales", "baseline_source": "xgboost" if forecast_scale else "historical POS sales",
                   "forecast_scale": round(scale, 4), "weekly_history_days": int(sales["date"].nunique())}
    params = {"dishes": dish_specs, "ingredients": ing_specs, "recipes": recipe_specs,
              "budget": avg_budget, "calibration": calibration}
    try:
        result = await asyncio.to_thread(forecast.forecast_demand, params, scenario or {}, int((scenario or {}).get("runs", 300)))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result["menu"] = [{"id": d["id"], "name": d["name"], "price": d["price"]} for d in dish_specs]
    # forecast_demand's own return dict has a "scenario" key too (the Monte
    # Carlo outcome under the scenario conditions, dict-merged in last so it
    # wins) - scenario_inputs is the one unambiguous place to find what was
    # actually dialled in (item, discount, holiday, overrides), for callers
    # like the What If overview that need the request rather than the result.
    result["scenario_inputs"] = scenario or {}
    return result


@app.get("/api/backtest")
async def get_backtest(restaurant_id: str, user_id: str = Depends(get_current_user_id)):
    await verify_restaurant_owner(restaurant_id, user_id)
    return backtest.run_backtest(restaurant_id)


@app.get("/api/forecast")
async def get_forecast(restaurant_id: str, user_id: str = Depends(get_current_user_id)):
    """Latest stored forecast run, if any - a cheap read, no training."""
    await verify_restaurant_owner(restaurant_id, user_id)
    latest = await forecast_store.get_latest_run(db.get_pool(), restaurant_id)
    return latest or {"run_at": None, "forecast": None}


@app.post("/api/forecast")
async def post_forecast(
    restaurant_id: str, target_week: date | None = None, user_id: str = Depends(get_current_user_id)
):
    """Runs the forecast now (target week's ingredient usage with P10/P50/P90
    bands, order recommendations, savings, history, backtest and data status)
    and stores it as the latest run. target_week defaults to next week."""
    await verify_restaurant_owner(restaurant_id, user_id)
    frames = await load_frames(restaurant_id)
    # Training is CPU bound, keep it off the event loop.
    payload = await asyncio.to_thread(build_forecast_payload, frames, None, target_week)
    run_at = await forecast_store.save_run(db.get_pool(), restaurant_id, payload)
    return {"run_at": run_at, "forecast": payload}
