"""Persists validated upload rows into Postgres.

CSV ids (`ingredient_id`, `item_id`) are business-level slugs, distinct from
each table's human-readable `name` and from the UUID primary key Postgres
generates - they're stored in each table's `external_id` column so later
uploads (recipes, sales, purchases, inventory_counts) can resolve them back
to the right row.

`restaurant_id` throughout this module is always a real restaurants.id -
the restaurant is created up front (owned by the signed-in user) via the
Next.js /api/restaurants route, and app.auth.verify_restaurant_owner checks
ownership before any of this runs. Nothing here bootstraps a restaurant row.

Each handler resolves and validates every row first, then writes the whole
file in one `executemany`. Sales files run to hundreds of rows, and a
per-row round trip to a hosted database made a single upload take tens of
seconds.
"""
from datetime import date

import asyncpg


async def _id_map(conn: asyncpg.Connection, table: str, restaurant_id: str) -> dict[str, str]:
    rows = await conn.fetch(f"SELECT external_id, id FROM {table} WHERE restaurant_id = $1", restaurant_id)
    return {r["external_id"]: r["id"] for r in rows}


async def upsert_ingredients(conn: asyncpg.Connection, restaurant_id: str, rows: list[dict]) -> None:
    records = []
    for row in rows:
        shelf_life = row.get("shelf_life_days")
        records.append((
            restaurant_id, str(row["ingredient_id"]), row["name"], row["unit"],
            float(row["unit_cost"]), float(row["pack_size"]),
            int(float(shelf_life)) if shelf_life not in (None, "") else None,
        ))
    if not records:
        return
    await conn.executemany(
        """
        INSERT INTO ingredients (restaurant_id, external_id, name, unit, unit_cost, pack_size, shelf_life_days)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (restaurant_id, external_id) DO UPDATE SET
            name = EXCLUDED.name, unit = EXCLUDED.unit, unit_cost = EXCLUDED.unit_cost,
            pack_size = EXCLUDED.pack_size, shelf_life_days = EXCLUDED.shelf_life_days
        """,
        records,
    )


async def upsert_menu_items(conn: asyncpg.Connection, restaurant_id: str, rows: list[dict]) -> None:
    records = [
        (restaurant_id, str(row["item_id"]), row["name"], float(row["price"]), row.get("category"))
        for row in rows
    ]
    if not records:
        return
    await conn.executemany(
        """
        INSERT INTO menu_items (restaurant_id, external_id, name, price, category)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (restaurant_id, external_id) DO UPDATE SET
            name = EXCLUDED.name, price = EXCLUDED.price, category = EXCLUDED.category
        """,
        records,
    )


async def insert_recipes(conn: asyncpg.Connection, restaurant_id: str, rows: list[dict]) -> list[str]:
    ingredient_map = await _id_map(conn, "ingredients", restaurant_id)
    menu_item_map = await _id_map(conn, "menu_items", restaurant_id)
    errors = []
    records = []
    for row in rows:
        menu_item_id = menu_item_map.get(str(row["item_id"]))
        ingredient_id = ingredient_map.get(str(row["ingredient_id"]))
        if menu_item_id is None:
            errors.append(f"unknown item_id (upload menu first): {row['item_id']}")
            continue
        if ingredient_id is None:
            errors.append(f"unknown ingredient_id (upload ingredients first): {row['ingredient_id']}")
            continue
        records.append((menu_item_id, ingredient_id, float(row["qty_per_serving"])))

    if records:
        await conn.executemany(
            """
            INSERT INTO recipes (menu_item_id, ingredient_id, qty_per_serving)
            VALUES ($1, $2, $3)
            ON CONFLICT (menu_item_id, ingredient_id) DO UPDATE SET qty_per_serving = EXCLUDED.qty_per_serving
            """,
            records,
        )
    return errors


async def insert_sales(conn: asyncpg.Connection, restaurant_id: str, rows: list[dict]) -> list[str]:
    menu_item_map = await _id_map(conn, "menu_items", restaurant_id)
    errors = []
    records = []
    for row in rows:
        menu_item_id = menu_item_map.get(str(row["item_id"]))
        if menu_item_id is None:
            errors.append(f"unknown item_id (upload menu first): {row['item_id']}")
            continue
        records.append((
            restaurant_id, menu_item_id, date.fromisoformat(str(row["date"])),
            float(row["qty_sold"]), float(row["avg_price"]),
        ))

    if records:
        await conn.executemany(
            """
            INSERT INTO sales (restaurant_id, menu_item_id, date, qty_sold, avg_price)
            VALUES ($1, $2, $3, $4, $5)
            """,
            records,
        )
    return errors


async def insert_purchases(conn: asyncpg.Connection, restaurant_id: str, rows: list[dict]) -> list[str]:
    ingredient_map = await _id_map(conn, "ingredients", restaurant_id)
    errors = []
    records = []
    for row in rows:
        ingredient_id = ingredient_map.get(str(row["ingredient_id"]))
        if ingredient_id is None:
            errors.append(f"unknown ingredient_id (upload ingredients first): {row['ingredient_id']}")
            continue
        records.append((
            restaurant_id, ingredient_id, date.fromisoformat(str(row["date"])),
            float(row["qty"]), float(row["unit_cost"]), float(row["total"]),
        ))

    if records:
        await conn.executemany(
            """
            INSERT INTO purchases (restaurant_id, ingredient_id, date, qty, unit_cost, total)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            records,
        )
    return errors


async def insert_inventory_counts(conn: asyncpg.Connection, restaurant_id: str, rows: list[dict]) -> list[str]:
    ingredient_map = await _id_map(conn, "ingredients", restaurant_id)
    errors = []
    records = []
    for row in rows:
        ingredient_id = ingredient_map.get(str(row["ingredient_id"]))
        if ingredient_id is None:
            errors.append(f"unknown ingredient_id (upload ingredients first): {row['ingredient_id']}")
            continue
        records.append((
            restaurant_id, ingredient_id, date.fromisoformat(str(row["date"])),
            float(row["qty_on_hand"]),
        ))

    if not records:
        return errors

    await conn.executemany(
        """
        INSERT INTO inventory_counts (restaurant_id, ingredient_id, date, qty_on_hand, source)
        VALUES ($1, $2, $3, $4, 'computed')
        """,
        records,
    )

    # inventory_current holds the newest count per ingredient. Derived from the
    # stored counts in one statement rather than per-row RETURNING, which
    # executemany cannot give us. DISTINCT ON picks each ingredient's latest
    # count across every upload, so the result does not depend on the order
    # rows arrived in, and the guard keeps an existing newer value intact.
    await conn.execute(
        """
        INSERT INTO inventory_current (restaurant_id, ingredient_id, qty_on_hand, last_reconciled_count_id, last_updated)
        SELECT DISTINCT ON (c.ingredient_id)
            c.restaurant_id, c.ingredient_id, c.qty_on_hand, c.id,
            c.date::timestamp AT TIME ZONE 'UTC'
        FROM inventory_counts c
        WHERE c.restaurant_id = $1
        ORDER BY c.ingredient_id, c.date DESC, c.created_at DESC
        ON CONFLICT (restaurant_id, ingredient_id) DO UPDATE SET
            qty_on_hand = EXCLUDED.qty_on_hand,
            last_reconciled_count_id = EXCLUDED.last_reconciled_count_id,
            last_updated = EXCLUDED.last_updated
        WHERE inventory_current.last_updated <= EXCLUDED.last_updated
        """,
        restaurant_id,
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
            batch_id = await conn.fetchval(
                """
                INSERT INTO upload_batches (restaurant_id, file_type, file_name, row_count, status)
                VALUES ($1, $2, $3, $4, 'pending')
                RETURNING id
                """,
                restaurant_id, file_type, file_name, len(rows),
            )
            errors = await handler(conn, restaurant_id, rows) or []
            status = "processed" if not errors else "failed"
            error_message = "; ".join(errors[:5]) if errors else None
            await conn.execute(
                "UPDATE upload_batches SET status = $1, error_message = $2 WHERE id = $3",
                status, error_message, batch_id,
            )
            return {"batch_id": str(batch_id), "errors": errors}
