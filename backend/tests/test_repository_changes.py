import asyncio
from datetime import datetime, timezone

from app import repository

ALWAYS = repository.ALWAYS


class FakeConn:
    """Just enough of asyncpg.Connection to record what the upload handlers write."""

    def __init__(self, ingredients=(), recipes=()):
        self.ingredients = list(ingredients)
        self.recipes = list(recipes)
        self.executed: list[tuple[str, list]] = []

    async def fetch(self, sql, *args):
        if "SELECT external_id, id FROM ingredients" in sql:
            return [{"external_id": "beef", "id": "i-beef"}, {"external_id": "bun", "id": "i-bun"}]
        if "SELECT external_id, id FROM menu_items" in sql:
            return [{"external_id": "burger", "id": "m-burger"}, {"external_id": "wrap", "id": "m-wrap"}]
        if "FROM ingredients" in sql:
            assert "current_id IS NULL" in sql, "history rows must never be treated as current"
            return self.ingredients
        if "FROM recipes" in sql:
            return self.recipes
        raise AssertionError(f"unexpected query: {sql}")

    async def executemany(self, sql, records):
        self.executed.append((" ".join(sql.split()), list(records)))

    def writes(self, prefix: str) -> list:
        return [r for sql, rows in self.executed if sql.startswith(prefix) for r in rows]


def run(coro):
    return asyncio.run(coro)


def utc(y, m, d):
    return datetime(y, m, d, tzinfo=timezone.utc)


BEEF = {
    "id": "i-beef", "external_id": "beef", "name": "Beef", "unit": "kg", "unit_cost": 10.0, "pack_size": 5.0,
    "shelf_life_days": 3, "valid_from": ALWAYS,
}


def ingredient_row(**kw):
    return {"ingredient_id": "beef", "name": "Beef", "unit": "kg", "unit_cost": "10", "pack_size": "5", "shelf_life_days": "3", **kw}


def test_identical_ingredient_reupload_writes_nothing():
    conn = FakeConn(ingredients=[BEEF])
    assert run(repository.upsert_ingredients(conn, "r1", [ingredient_row()])) == []
    assert conn.executed == []


def test_price_change_archives_the_old_values_then_updates_the_current_row():
    conn = FakeConn(ingredients=[BEEF])
    run(repository.upsert_ingredients(conn, "r1", [ingredient_row(unit_cost="12.5", effective_date="2026-03-01")]))
    assert conn.writes("INSERT INTO ingredients") == [("i-beef", utc(2026, 3, 1))]
    (update,) = conn.writes("UPDATE ingredients")
    assert update[2] == 12.5 and update[5] == utc(2026, 3, 1) and update[6] == "i-beef"
    # the copy is taken from the row before the update
    order = [sql.split()[0] for sql, _ in conn.executed]
    assert order == ["INSERT", "UPDATE"]


def test_price_change_without_effective_date_is_effective_now():
    conn = FakeConn(ingredients=[BEEF])
    before = datetime.now(timezone.utc)
    run(repository.upsert_ingredients(conn, "r1", [ingredient_row(unit_cost="12")]))
    (_, effective_at), = conn.writes("INSERT INTO ingredients")
    assert before <= effective_at <= datetime.now(timezone.utc)


def test_backdating_before_the_last_change_is_rejected():
    latest = {**BEEF, "valid_from": utc(2026, 5, 1)}
    conn = FakeConn(ingredients=[latest])
    errors = run(repository.upsert_ingredients(conn, "r1", [ingredient_row(unit_cost="12", effective_date="2026-04-01")]))
    assert len(errors) == 1 and "earlier than its last change" in errors[0]
    assert conn.executed == []


def test_name_only_change_does_not_create_history():
    conn = FakeConn(ingredients=[BEEF])
    run(repository.upsert_ingredients(conn, "r1", [ingredient_row(name="Ground beef")]))
    assert conn.writes("INSERT INTO ingredients") == []
    assert len(conn.writes("UPDATE ingredients")) == 1


def test_new_ingredient_starts_at_the_beginning_of_time():
    conn = FakeConn(ingredients=[])
    run(repository.upsert_ingredients(conn, "r1", [ingredient_row()]))
    (record,) = conn.writes("INSERT INTO ingredients")
    assert record[-1] == ALWAYS


def line(item, ing, qty, valid_from=ALWAYS, valid_to=None, row_id=None):
    return {
        "id": row_id or f"{item}-{ing}-{qty}", "menu_item_id": item, "ingredient_id": ing,
        "qty_per_serving": float(qty), "valid_from": valid_from, "valid_to": valid_to,
    }


EXISTING = [
    line("m-burger", "i-beef", 0.2, row_id="r1"),
    line("m-burger", "i-bun", 1, row_id="r2"),
    line("m-wrap", "i-beef", 0.1, row_id="r3"),
]


def recipe_row(item, ing, qty, **kw):
    return {"item_id": item, "ingredient_id": ing, "qty_per_serving": str(qty), **kw}


def test_qty_change_ends_the_current_line_and_adds_a_new_one():
    conn = FakeConn(recipes=EXISTING)
    rows = [recipe_row("burger", "beef", 0.3, effective_date="2026-08-03"), recipe_row("burger", "bun", 1)]
    assert run(repository.insert_recipes(conn, "r1", rows)) == []
    assert conn.writes("UPDATE recipes") == [("r1", utc(2026, 8, 3))]
    assert conn.writes("INSERT INTO recipes") == [("m-burger", "i-beef", 0.3, utc(2026, 8, 3))]
    assert [sql.split()[0] for sql, _ in conn.executed] == ["UPDATE", "INSERT"]  # end before insert


def test_ingredient_missing_from_a_listed_dish_is_ended_not_deleted():
    conn = FakeConn(recipes=EXISTING)
    run(repository.insert_recipes(conn, "r1", [recipe_row("burger", "beef", 0.2, effective_date="2026-08-03")]))
    assert conn.writes("UPDATE recipes") == [("r2", utc(2026, 8, 3))]
    assert conn.writes("INSERT INTO recipes") == []
    assert not any(sql.startswith("DELETE") for sql, _ in conn.executed)
    # the wrap is not in the file, so it is untouched
    assert all(rid != "r3" for rid, _ in conn.writes("UPDATE recipes"))


def test_line_added_to_an_existing_dish_starts_when_added_but_a_new_dish_starts_at_the_beginning():
    conn = FakeConn(recipes=EXISTING)
    rows = [
        recipe_row("burger", "beef", 0.2), recipe_row("burger", "bun", 1),
        recipe_row("wrap", "beef", 0.1), recipe_row("wrap", "bun", 1, effective_date="2026-08-03"),
    ]
    run(repository.insert_recipes(conn, "r1", rows))
    assert conn.writes("INSERT INTO recipes") == [("m-wrap", "i-bun", 1.0, utc(2026, 8, 3))]

    fresh = FakeConn(recipes=[])
    run(repository.insert_recipes(fresh, "r1", [recipe_row("burger", "beef", 0.2)]))
    assert fresh.writes("INSERT INTO recipes") == [("m-burger", "i-beef", 0.2, ALWAYS)]


def test_identical_recipe_reupload_writes_nothing():
    conn = FakeConn(recipes=EXISTING)
    rows = [recipe_row("burger", "beef", 0.2), recipe_row("burger", "bun", 1), recipe_row("wrap", "beef", 0.1)]
    assert run(repository.insert_recipes(conn, "r1", rows)) == []
    assert conn.executed == []


def test_recipe_backdated_before_its_last_change_is_rejected():
    recent = [line("m-burger", "i-beef", 0.2, valid_from=utc(2026, 5, 1), row_id="r1")]
    conn = FakeConn(recipes=recent)
    errors = run(repository.insert_recipes(conn, "r1", [recipe_row("burger", "beef", 0.3, effective_date="2026-04-01")]))
    assert len(errors) == 1 and "earlier than its last change" in errors[0]
    assert conn.executed == []
