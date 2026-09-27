"""Loads historical ingredient consumption (qty_sold x recipe qty) for one restaurant.

Each sale uses the recipe line that was in force on the sale date, so editing a
recipe later does not change what was consumed in the past.
"""
from sim import history


async def load_consumption(conn, restaurant_id: str, ingredients: list[dict]) -> list[dict]:
    """[{ingredient_id, date, qty}], ingredient_id being the ingredients.id in `ingredients`."""
    sales = await conn.fetch(
        "SELECT menu_item_id::text AS menu_item_id, date, qty_sold::float8 AS qty_sold "
        "FROM sales WHERE restaurant_id = $1 ORDER BY date, menu_item_id",
        restaurant_id,
    )
    recipe_rows = await conn.fetch(
        "SELECT r.menu_item_id::text AS menu_item_id, r.ingredient_id::text AS ingredient_id, "
        "r.qty_per_serving::float8 AS qty_per_serving, r.valid_from, r.valid_to "
        "FROM recipes r JOIN menu_items m ON m.id = r.menu_item_id "
        "WHERE m.restaurant_id = $1 ORDER BY 1, 2, r.valid_from",
        restaurant_id,
    )
    return history.consumption_rows(ingredients, [dict(r) for r in sales], [dict(r) for r in recipe_rows])
