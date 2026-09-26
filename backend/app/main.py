from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app import db
from sim import backtest, generator, ingest, waste


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    yield
    await db.disconnect()


app = FastAPI(title="SwarmStock API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/demo")
async def get_demo():
    return generator.generate_demo_dataset()


@app.post("/api/upload")
async def post_upload(file_type: str, file: UploadFile):
    rows = []  # TODO: parse file into rows
    return ingest.validate_upload(file_type, rows)


@app.get("/api/waste")
async def get_waste(restaurant_id: str):
    return waste.compute_waste(restaurant_id)


@app.post("/api/simulate")
async def post_simulate(restaurant_id: str, scenario: dict):
    raise NotImplementedError


@app.get("/api/backtest")
async def get_backtest(restaurant_id: str):
    return backtest.run_backtest(restaurant_id)
