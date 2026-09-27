"""Session validation shared with the Next.js app.

Sessions live in one `sessions` table in the same Postgres both sides talk
to - a random opaque token in an httpOnly cookie, looked up here with a
single query. No JWT signing/verification logic to keep in sync across
Python and TypeScript.
"""
from fastapi import Cookie, HTTPException

from app.db import get_pool


async def get_current_user_id(session: str | None = Cookie(default=None)) -> str:
    if session is None:
        raise HTTPException(status_code=401, detail="Not signed in.")

    pool = get_pool()
    async with pool.acquire() as conn:
        user_id = await conn.fetchval(
            "SELECT user_id FROM sessions WHERE token = $1 AND expires_at > now()",
            session,
        )
    if user_id is None:
        raise HTTPException(status_code=401, detail="Session expired.")
    return str(user_id)


async def verify_restaurant_owner(restaurant_id: str, user_id: str) -> None:
    """Raises if restaurant_id doesn't exist or isn't owned by user_id."""
    pool = get_pool()
    async with pool.acquire() as conn:
        owner_id = await conn.fetchval(
            "SELECT owner_user_id FROM restaurants WHERE id = $1",
            restaurant_id,
        )
    if owner_id is None:
        raise HTTPException(status_code=404, detail="Restaurant not found.")
    if str(owner_id) != user_id:
        raise HTTPException(status_code=403, detail="Not your restaurant.")
