import asyncio
import csv
import io
from datetime import date
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app import db, insights, repository
from app.auth import get_current_user_id, verify_restaurant_owner
from app.config import settings
from sim import backtest, forecast_store, generator, home_summary, ingest, inventory, waste
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
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))

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


@app.get("/api/home-summary")
async def get_home_summary(restaurant_id: str, user_id: str = Depends(get_current_user_id)):
    await verify_restaurant_owner(restaurant_id, user_id)
    return await home_summary.compute_home_summary(restaurant_id)


@app.post("/api/simulate")
async def post_simulate(restaurant_id: str, scenario: dict, user_id: str = Depends(get_current_user_id)):
    await verify_restaurant_owner(restaurant_id, user_id)
    raise NotImplementedError


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
