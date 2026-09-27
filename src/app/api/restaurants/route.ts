import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { getUserBySessionToken, SESSION_COOKIE } from "@/lib/session";

async function requireUser(request: NextRequest) {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  return getUserBySessionToken(token);
}

export async function GET(request: NextRequest) {
  const user = await requireUser(request);
  if (!user) return NextResponse.json({ error: "Not signed in." }, { status: 401 });

  const result = await getDb().query(
    `SELECT id, name, business_type, location, created_at
     FROM restaurants
     WHERE owner_user_id = $1
     ORDER BY created_at`,
    [user.id],
  );
  return NextResponse.json({ restaurants: result.rows });
}

export async function POST(request: NextRequest) {
  const user = await requireUser(request);
  if (!user) return NextResponse.json({ error: "Not signed in." }, { status: 401 });

  const body = await request.json().catch(() => null);
  const name = body?.name?.trim();
  const businessType = body?.type?.trim() || null;
  const location = body?.location?.trim() || null;
  if (!name) {
    return NextResponse.json({ error: "Business name is required." }, { status: 400 });
  }

  try {
    const result = await getDb().query(
      `INSERT INTO restaurants (owner_user_id, name, business_type, location)
       VALUES ($1, $2, $3, $4)
       RETURNING id, name, business_type, location, created_at`,
      [user.id, name, businessType, location],
    );
    return NextResponse.json({ restaurant: result.rows[0] });
  } catch (error: unknown) {
    if (error && typeof error === "object" && "code" in error && error.code === "23505") {
      return NextResponse.json({ error: "You already have a business with that name." }, { status: 409 });
    }
    throw error;
  }
}
