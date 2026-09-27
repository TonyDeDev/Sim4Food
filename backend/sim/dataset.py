"""Loads one restaurant's POS, recipe, purchase, inventory and event data from Postgres.

Returns pandas frames keyed by string ids, ready for sim.features.build_feature_matrix.
"""
import pandas as pd

from app.db import get_pool


async def load_frames(restaurant_name: str) -> dict:
    pool = get_pool()
    async with pool.acquire() as conn:
        restaurant_id = await conn.fetchval("SELECT id FROM restaurants WHERE name = $1", restaurant_name)
        if restaurant_id is None:
            raise ValueError(f"Unknown restaurant: {restaurant_name}")

        sales = await conn.fetch(
            "SELECT date, menu_item_id::text AS menu_item_id, qty_sold::float8 AS qty_sold, avg_price::float8 AS avg_price "
            "FROM sales WHERE restaurant_id = $1 ORDER BY date, menu_item_id",
            restaurant_id,
        )
        recipes = await conn.fetch(
            "SELECT r.menu_item_id::text AS menu_item_id, r.ingredient_id::text AS ingredient_id, "
            "r.qty_per_serving::float8 AS qty_per_serving "
            "FROM recipes r JOIN menu_items m ON m.id = r.menu_item_id "
            "WHERE m.restaurant_id = $1 ORDER BY 1, 2",
            restaurant_id,
        )
        ingredients = await conn.fetch(
            "SELECT id::text AS ingredient_id, name, unit, unit_cost::float8 AS unit_cost, "
            "pack_size::float8 AS pack_size, shelf_life_days::float8 AS shelf_life_days "
            "FROM ingredients WHERE restaurant_id = $1 ORDER BY external_id",
            restaurant_id,
        )
        purchases = await conn.fetch(
            "SELECT date, ingredient_id::text AS ingredient_id, qty::float8 AS qty "
            "FROM purchases WHERE restaurant_id = $1 ORDER BY date, ingredient_id",
            restaurant_id,
        )
        counts = await conn.fetch(
            "SELECT date, ingredient_id::text AS ingredient_id, qty_on_hand::float8 AS qty_on_hand "
            "FROM inventory_counts WHERE restaurant_id = $1 ORDER BY date, ingredient_id, created_at",
            restaurant_id,
        )
        events = await conn.fetch(
            "SELECT type::text AS type, start_date, end_date, items::text[] AS items, "
            "discount_pct::float8 AS discount_pct, expected_lift::float8 AS expected_lift "
            "FROM events WHERE restaurant_id = $1 ORDER BY start_date",
            restaurant_id,
        )

    def frame(rows, columns):
        return pd.DataFrame([dict(r) for r in rows], columns=columns)

    return {
        "restaurant_id": str(restaurant_id),
        "sales": frame(sales, ["date", "menu_item_id", "qty_sold", "avg_price"]),
        "recipes": frame(recipes, ["menu_item_id", "ingredient_id", "qty_per_serving"]),
        "ingredients": frame(ingredients, ["ingredient_id", "name", "unit", "unit_cost", "pack_size", "shelf_life_days"]),
        "purchases": frame(purchases, ["date", "ingredient_id", "qty"]),
        "counts": frame(counts, ["date", "ingredient_id", "qty_on_hand"]),
        "events": frame(events, ["type", "start_date", "end_date", "items", "discount_pct", "expected_lift"]),
    }
