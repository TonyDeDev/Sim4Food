"""Persists validated upload rows into Postgres.

CSV ids (`ingredient_id`, `item_id`) are business-level slugs, distinct from
each table's human-readable `name` and from the UUID primary key Postgres
generates - they're stored in each table's `external_id` column so later
uploads (recipes, sales, purchases, inventory_counts) can resolve them back
to the right row.
"""
from datetime import date, datetime

import asyncpg


async def ensure_restaurant(conn: asyncpg.Connection, restaurant_id: str) -> str:
    """Looks up (or bootstraps) the restaurant row for this restaurant_id, returning its UUID.

    Multi-tenant accounts are out of scope for the MVP, so `restaurant_id` as
    passed by the API is treated as a stable slug/name rather than a real UUID.
    """
    return await conn.fetchval(
        """
        INSERT INTO restaurants (name) VALUES ($1)
        ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
        RETURNING id
        """,
        restaurant_id,
    )


async def _id_map(conn: asyncpg.Connection, table: str, restaurant_id: str) -> dict[str, str]:
    rows = await conn.fetch(f"SELECT external_id, id FROM {table} WHERE restaurant_id = $1", restaurant_id)
    return {r["external_id"]: r["id"] for r in rows}


async def upsert_ingredients(conn: asyncpg.Connection, restaurant_id: str, rows: list[dict]) -> None:
    for row in rows:
        shelf_life = row.get("shelf_life_days")
        await conn.execute(
            """
            INSERT INTO ingredients (restaurant_id, external_id, name, unit, unit_cost, pack_size, shelf_life_days)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (restaurant_id, external_id) DO UPDATE SET
                name = EXCLUDED.name, unit = EXCLUDED.unit, unit_cost = EXCLUDED.unit_cost,
                pack_size = EXCLUDED.pack_size, shelf_life_days = EXCLUDED.shelf_life_days
            """,
            restaurant_id, str(row["ingredient_id"]), row["name"], row["unit"],
            float(row["unit_cost"]), float(row["pack_size"]),
            int(float(shelf_life)) if shelf_life not in (None, "") else None,
        )


async def upsert_menu_items(conn: asyncpg.Connection, restaurant_id: str, rows: list[dict]) -> None:
    for row in rows:
        await conn.execute(
            """
            INSERT INTO menu_items (restaurant_id, external_id, name, price, category)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (restaurant_id, external_id) DO UPDATE SET
                name = EXCLUDED.name, price = EXCLUDED.price, category = EXCLUDED.category
            """,
            restaurant_id, str(row["item_id"]), row["name"], float(row["price"]), row.get("category"),
        )


async def insert_recipes(conn: asyncpg.Connection, restaurant_id: str, rows: list[dict]) -> list[str]:
    ingredient_map = await _id_map(conn, "ingredients", restaurant_id)
    menu_item_map = await _id_map(conn, "menu_items", restaurant_id)
    errors = []
    for row in rows:
        menu_item_id = menu_item_map.get(str(row["item_id"]))
        ingredient_id = ingredient_map.get(str(row["ingredient_id"]))
        if menu_item_id is None:
            errors.append(f"unknown item_id (upload menu first): {row['item_id']}")
            continue
        if ingredient_id is None:
            errors.append(f"unknown ingredient_id (upload ingredients first): {row['ingredient_id']}")
            continue
        await conn.execute(
            """
            INSERT INTO recipes (menu_item_id, ingredient_id, qty_per_serving)
            VALUES ($1, $2, $3)
            ON CONFLICT (menu_item_id, ingredient_id) DO UPDATE SET qty_per_serving = EXCLUDED.qty_per_serving
            """,
            menu_item_id, ingredient_id, float(row["qty_per_serving"]),
        )
    return errors


async def insert_sales(conn: asyncpg.Connection, restaurant_id: str, rows: list[dict]) -> list[str]:
    menu_item_map = await _id_map(conn, "menu_items", restaurant_id)
    errors = []
    for row in rows:
        menu_item_id = menu_item_map.get(str(row["item_id"]))
        if menu_item_id is None:
            errors.append(f"unknown item_id (upload menu first): {row['item_id']}")
            continue
        await conn.execute(
            """
            INSERT INTO sales (restaurant_id, menu_item_id, date, qty_sold, avg_price)
            VALUES ($1, $2, $3, $4, $5)
            """,
            restaurant_id, menu_item_id, date.fromisoformat(str(row["date"])),
            float(row["qty_sold"]), float(row["avg_price"]),
        )
    return errors


async def insert_purchases(conn: asyncpg.Connection, restaurant_id: str, rows: list[dict]) -> list[str]:
    ingredient_map = await _id_map(conn, "ingredients", restaurant_id)
    errors = []
    for row in rows:
        ingredient_id = ingredient_map.get(str(row["ingredient_id"]))
        if ingredient_id is None:
            errors.append(f"unknown ingredient_id (upload ingredients first): {row['ingredient_id']}")
            continue
        await conn.execute(
            """
            INSERT INTO purchases (restaurant_id, ingredient_id, date, qty, unit_cost, total)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            restaurant_id, ingredient_id, date.fromisoformat(str(row["date"])),
            float(row["qty"]), float(row["unit_cost"]), float(row["total"]),
        )
    return errors


async def insert_inventory_counts(conn: asyncpg.Connection, restaurant_id: str, rows: list[dict]) -> list[str]:
    ingredient_map = await _id_map(conn, "ingredients", restaurant_id)
    errors = []
    for row in rows:
        ingredient_id = ingredient_map.get(str(row["ingredient_id"]))
        if ingredient_id is None:
            errors.append(f"unknown ingredient_id (upload ingredients first): {row['ingredient_id']}")
            continue
        d = date.fromisoformat(str(row["date"]))
        qty = float(row["qty_on_hand"])
        count_id = await conn.fetchval(
            """
            INSERT INTO inventory_counts (restaurant_id, ingredient_id, date, qty_on_hand, source)
            VALUES ($1, $2, $3, $4, 'computed')
            RETURNING id
            """,
            restaurant_id, ingredient_id, d, qty,
        )
        updated_at = datetime.combine(d, datetime.min.time())
        await conn.execute(
            """
            INSERT INTO inventory_current (restaurant_id, ingredient_id, qty_on_hand, last_reconciled_count_id, last_updated)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (restaurant_id, ingredient_id) DO UPDATE SET
                qty_on_hand = EXCLUDED.qty_on_hand,
                last_reconciled_count_id = EXCLUDED.last_reconciled_count_id,
                last_updated = EXCLUDED.last_updated
            WHERE inventory_current.last_updated <= EXCLUDED.last_updated
            """,
            restaurant_id, ingredient_id, qty, count_id, updated_at,
        )
    return errors


_HANDLERS = {
    "ingredients": upsert_ingredients,
    "menu": upsert_menu_items,
    "recipes": insert_recipes,
    "sales": insert_sales,
    "purchases": insert_purchases,
    "inventory_counts": insert_inventory_counts,
}


async def persist_upload(
    pool: asyncpg.Pool, restaurant_id: str, file_type: str, file_name: str, rows: list[dict]
) -> dict:
    """Writes validated rows for one file into Postgres, tracked as an upload_batches row.

    Returns {"batch_id", "errors"} - row-level errors are references to ids
    from a file that hasn't been uploaded yet (e.g. a recipe naming an
    ingredient not yet in `ingredients`); an empty list means every row
    persisted.
    """
    handler = _HANDLERS[file_type]
    async with pool.acquire() as conn:
        async with conn.transaction():
            restaurant_uuid = await ensure_restaurant(conn, restaurant_id)
            batch_id = await conn.fetchval(
                """
                INSERT INTO upload_batches (restaurant_id, file_type, file_name, row_count, status)
                VALUES ($1, $2, $3, $4, 'pending')
                RETURNING id
                """,
                restaurant_uuid, file_type, file_name, len(rows),
            )
            errors = await handler(conn, restaurant_uuid, rows) or []
            status = "processed" if not errors else "failed"
            error_message = "; ".join(errors[:5]) if errors else None
            await conn.execute(
                "UPDATE upload_batches SET status = $1, error_message = $2 WHERE id = $3",
                status, error_message, batch_id,
            )
            return {"batch_id": str(batch_id), "errors": errors}
