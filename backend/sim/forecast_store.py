"""Persists forecast runs so the model only trains when explicitly triggered
(the Simulate button), not on every page view.

GET /api/forecast reads the latest stored row here - cheap, no training.
POST /api/forecast (main.py) runs build_forecast_payload and calls save_run.
"""
import json

import asyncpg


async def get_latest_run(pool: asyncpg.Pool, restaurant_id: str) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT results, created_at FROM simulation_runs WHERE restaurant_id = $1 ORDER BY created_at DESC LIMIT 1",
            restaurant_id,
        )
    if row is None:
        return None
    results = row["results"]
    if isinstance(results, str):
        results = json.loads(results)
    return {"forecast": results, "run_at": row["created_at"].isoformat()}


async def save_run(pool: asyncpg.Pool, restaurant_id: str, payload: dict) -> str:
    async with pool.acquire() as conn:
        created_at = await conn.fetchval(
            """
            INSERT INTO simulation_runs (restaurant_id, scenario_params, results)
            VALUES ($1, '{}'::jsonb, $2::jsonb)
            RETURNING created_at
            """,
            restaurant_id, json.dumps(payload),
        )
    return created_at.isoformat()
