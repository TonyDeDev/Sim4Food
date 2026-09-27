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
from datetime import date, datetime, time, timezone

import asyncpg


async def _id_map(conn: asyncpg.Connection, table: str, restaurant_id: str) -> dict[str, str]:
    # Ingredients keep old versions as extra rows; only the current row is addressable.
    current_only = " AND current_id IS NULL" if table == "ingredients" else ""
    rows = await conn.fetch(
        f"SELECT external_id, id FROM {table} WHERE restaurant_id = $1{current_only}", restaurant_id
    )
    return {r["external_id"]: r["id"] for r in rows}


# The first version of a row starts here, so it covers all earlier history.
ALWAYS = datetime(1900, 1, 1, tzinfo=timezone.utc)


def _effective_at(row: dict) -> datetime:
    """The row's optional effective_date as UTC midnight, or the moment of upload."""
    value = row.get("effective_date")
    if value is None or str(value).strip() == "":
        return datetime.now(timezone.utc)
    return datetime.combine(date.fromisoformat(str(value).strip()), time.min, tzinfo=timezone.utc)


def _same(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, str) or isinstance(b, str):
        return a == b
    return abs(float(a) - float(b)) < 1e-9


_VERSIONED_INGREDIENT_FIELDS = ("unit", "unit_cost", "pack_size", "shelf_life_days")


async def upsert_ingredients(conn: asyncpg.Connection, restaurant_id: str, rows: list[dict]) -> list[str]:
    """Upserts ingredients, keeping the old values as a history row when a spec changes.

    The current row (current_id NULL) keeps its id, so purchases, counts and
    recipes keep pointing at it. When unit, unit_cost, pack_size or
    shelf_life_days differ, a copy of the old values is inserted with valid_to
    set to the change time (current_id pointing at the current row) and the
    current row is updated with valid_from = the change time. Identical
    re-uploads write nothing. Returns row errors.
    """
    existing = {
        r["external_id"]: r
        for r in await conn.fetch(
            "SELECT id, external_id, name, unit, unit_cost::float8 AS unit_cost, pack_size::float8 AS pack_size, "
            "shelf_life_days, valid_from FROM ingredients WHERE restaurant_id = $1 AND current_id IS NULL",
            restaurant_id,
        )
    }
    errors: list[str] = []
    new_records, archives, updates = [], [], []
    for row in rows:
        shelf_life = row.get("shelf_life_days")
        incoming = {
            "unit": row["unit"],
            "unit_cost": float(row["unit_cost"]),
            "pack_size": float(row["pack_size"]),
            "shelf_life_days": int(float(shelf_life)) if shelf_life not in (None, "") else None,
        }
        external_id = str(row["ingredient_id"])
        current = existing.get(external_id)
        if current is None:
            new_records.append((
                restaurant_id, external_id, row["name"], incoming["unit"], incoming["unit_cost"],
                incoming["pack_size"], incoming["shelf_life_days"], ALWAYS,
            ))
            continue

        spec_changed = any(not _same(current[f], incoming[f]) for f in _VERSIONED_INGREDIENT_FIELDS)
        if not spec_changed:
            if current["name"] != row["name"]:
                updates.append((row["name"], incoming["unit"], incoming["unit_cost"], incoming["pack_size"],
                                incoming["shelf_life_days"], current["valid_from"], current["id"]))
            continue

        effective_at = _effective_at(row)
        if effective_at < current["valid_from"]:
            errors.append(
                f"{external_id}: effective_date is earlier than its last change "
                f"({current['valid_from'].date().isoformat()})"
            )
            continue
        archives.append((current["id"], effective_at))
        updates.append((row["name"], incoming["unit"], incoming["unit_cost"], incoming["pack_size"],
                        incoming["shelf_life_days"], effective_at, current["id"]))

    if new_records:
        await conn.executemany(
            """
            INSERT INTO ingredients
                (restaurant_id, external_id, name, unit, unit_cost, pack_size, shelf_life_days, valid_from)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            new_records,
        )
    if archives:
        await conn.executemany(
            """
            INSERT INTO ingredients
                (restaurant_id, external_id, name, unit, unit_cost, pack_size, shelf_life_days,
                 created_at, valid_from, valid_to, current_id)
            SELECT restaurant_id, external_id, name, unit, unit_cost, pack_size, shelf_life_days,
                   created_at, valid_from, $2, id
            FROM ingredients WHERE id = $1
            """,
            archives,
        )
    if updates:
        await conn.executemany(
            """
            UPDATE ingredients SET
                name = $1, unit = $2, unit_cost = $3, pack_size = $4, shelf_life_days = $5,
                valid_from = $6, updated_at = now()
            WHERE id = $7
            """,
            updates,
        )
    return errors


async def upsert_menu_items(conn: asyncpg.Connection, restaurant_id: str, rows: list[dict]) -> None:
    records = [
        (restaurant_id, str(row["item_id"]), row["name"], float(row["price"]), row.get("category"))
        for row in rows
    ]
    if not records:
        return
    # Menu price history is not kept separately: sales.avg_price already
    # snapshots the price at the time of each sale.
    await conn.executemany(
        """
        INSERT INTO menu_items (restaurant_id, external_id, name, price, category)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (restaurant_id, external_id) DO UPDATE SET
            name = EXCLUDED.name, price = EXCLUDED.price, category = EXCLUDED.category,
            updated_at = now()
        """,
        records,
    )


async def insert_recipes(conn: asyncpg.Connection, restaurant_id: str, rows: list[dict]) -> list[str]:
    """Replaces the recipe of every dish named in the file, keeping the old lines as history.

    A dish in the file is treated as fully specified: ingredients it used to
    have that are missing from the file are ended. Dishes not in the file are
    left alone. A changed quantity ends the current line (valid_to) and adds a
    new one (valid_from); unchanged lines write nothing.
    """
    ingredient_map = await _id_map(conn, "ingredients", restaurant_id)
    menu_item_map = await _id_map(conn, "menu_items", restaurant_id)
    errors: list[str] = []
    wanted: dict[tuple, tuple[float, datetime]] = {}
    dishes: set = set()
    for row in rows:
        menu_item_id = menu_item_map.get(str(row["item_id"]))
        ingredient_id = ingredient_map.get(str(row["ingredient_id"]))
        if menu_item_id is None:
            errors.append(f"unknown item_id (upload menu first): {row['item_id']}")
            continue
        if ingredient_id is None:
            errors.append(f"unknown ingredient_id (upload ingredients first): {row['ingredient_id']}")
            continue
        wanted[(menu_item_id, ingredient_id)] = (float(row["qty_per_serving"]), _effective_at(row))
        dishes.add(menu_item_id)

    if not dishes:
        return errors

    stored = await conn.fetch(
        "SELECT id, menu_item_id, ingredient_id, qty_per_serving::float8 AS qty_per_serving, valid_from, valid_to "
        "FROM recipes WHERE menu_item_id = ANY($1::uuid[])",
        list(dishes),
    )
    current = {(r["menu_item_id"], r["ingredient_id"]): r for r in stored if r["valid_to"] is None}
    dishes_with_history = {r["menu_item_id"] for r in stored}
    # A removal takes effect when the file says the dish's other lines do.
    dish_effective = {dish: eff for (dish, _), (_qty, eff) in wanted.items()}

    ends, inserts = [], []  # ends: (row id, valid_to), inserts: (dish, ingredient, qty, valid_from)
    for key, (qty, effective_at) in wanted.items():
        old = current.get(key)
        if old is not None and _same(old["qty_per_serving"], qty):
            continue
        if old is not None:
            if effective_at < old["valid_from"]:
                errors.append(
                    f"recipe {key[0]}/{key[1]}: effective_date is earlier than its last change "
                    f"({old['valid_from'].date().isoformat()})"
                )
                continue
            ends.append((old["id"], effective_at))
            start = effective_at
        else:
            # A dish with no recipe yet starts at the beginning of time; a line added
            # to an existing dish starts when it was added.
            start = effective_at if key[0] in dishes_with_history else ALWAYS
        inserts.append((key[0], key[1], qty, start))
    for key, old in current.items():
        if key[0] in dishes and key not in wanted:
            effective_at = dish_effective[key[0]]
            if effective_at < old["valid_from"]:
                errors.append(f"recipe {key[0]}/{key[1]}: effective_date is earlier than its last change")
                continue
            ends.append((old["id"], effective_at))

    if ends:
        await conn.executemany("UPDATE recipes SET valid_to = $2 WHERE id = $1", ends)
    if inserts:
        await conn.executemany(
            "INSERT INTO recipes (menu_item_id, ingredient_id, qty_per_serving, valid_from) VALUES ($1, $2, $3, $4)",
            inserts,
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
