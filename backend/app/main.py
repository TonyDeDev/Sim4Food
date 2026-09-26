import csv
import io
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app import db, repository
from app.config import settings
from sim import backtest, generator, ingest, waste


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    yield
    await db.disconnect()


app = FastAPI(title="SwarmStock API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/demo")
async def get_demo():
    return generator.generate_demo_dataset()


@app.post("/api/upload")
async def post_upload(restaurant_id: str, file_type: str, file: UploadFile):
    raw = await file.read()
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))

    validation = ingest.validate_upload(file_type, rows)
    if validation["status"] != "ok":
        return validation

    persisted = await repository.persist_upload(db.get_pool(), restaurant_id, file_type, file.filename, rows)
    return {**validation, **persisted}


@app.get("/api/waste")
async def get_waste(restaurant_id: str):
    return waste.compute_waste(restaurant_id)


@app.post("/api/simulate")
async def post_simulate(restaurant_id: str, scenario: dict):
    raise NotImplementedError


@app.get("/api/backtest")
async def get_backtest(restaurant_id: str):
    return backtest.run_backtest(restaurant_id)
