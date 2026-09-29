import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { getUserBySessionToken, SESSION_COOKIE } from "@/lib/session";

// Every table that references restaurants(id) does so ON DELETE CASCADE (see
// db/schema.sql), so removing the one row takes its ingredients, menu, recipes,
// sales, purchases, inventory, events, forecasts and backtests with it. There
// is nothing to clean up outside Postgres.
export async function DELETE(request: NextRequest, ctx: RouteContext<"/api/restaurants/[id]">) {
  const user = await getUserBySessionToken(request.cookies.get(SESSION_COOKIE)?.value);
  if (!user) return NextResponse.json({ error: "Not signed in." }, { status: 401 });

  const { id } = await ctx.params;

  try {
    // Ownership is part of the DELETE rather than a separate check, so there is
    // no window between reading the owner and acting on it. A restaurant that
    // belongs to someone else answers the same 404 as one that does not exist,
    // which keeps the endpoint from confirming that an id is real.
    const result = await getDb().query(
      "DELETE FROM restaurants WHERE id = $1 AND owner_user_id = $2 RETURNING id, name",
      [id, user.id],
    );
    if (result.rowCount === 0) {
      return NextResponse.json({ error: "Restaurant not found." }, { status: 404 });
    }
    return NextResponse.json({ deleted: result.rows[0] });
  } catch (error: unknown) {
    // invalid_text_representation: the id in the URL is not a UUID at all, so
    // it cannot name a restaurant. Same answer as one that is simply missing.
    if (error && typeof error === "object" && "code" in error && error.code === "22P02") {
      return NextResponse.json({ error: "Restaurant not found." }, { status: 404 });
    }
    throw error;
  }
}
