"""Extra data the agent-based simulation needs beyond sim.dataset.load_frames.

load_frames (the XGBoost pipeline's loader) has no reason to carry menu
prices or live stock - it never uses them. The agent simulation needs both:
prices for the dish-choice price term and for revenue/profit, and
inventory_current specifically (not a historical inventory_counts snapshot)
because a what-if run means "starting from what's actually on the shelf
right now."
"""
import pandas as pd

from app.db import get_pool
from sim.dataset import load_frames


async def load_simulation_frames(restaurant_id: str) -> dict:
    frames = await load_frames(restaurant_id)

    pool = get_pool()
    async with pool.acquire() as conn:
        menu_rows = await conn.fetch(
            "SELECT id::text AS menu_item_id, external_id, name, price::float8 AS price, category "
            "FROM menu_items WHERE restaurant_id = $1",
            restaurant_id,
        )
        stock_rows = await conn.fetch(
            "SELECT ingredient_id::text AS ingredient_id, qty_on_hand::float8 AS qty_on_hand "
            "FROM inventory_current WHERE restaurant_id = $1",
            restaurant_id,
        )

    frames["menu_items"] = pd.DataFrame(
        [dict(r) for r in menu_rows], columns=["menu_item_id", "external_id", "name", "price", "category"]
    )
    frames["current_stock"] = pd.DataFrame([dict(r) for r in stock_rows], columns=["ingredient_id", "qty_on_hand"])
    return frames
