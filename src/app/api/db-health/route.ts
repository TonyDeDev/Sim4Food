import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";

export async function GET() {
  try {
    const db = getDb();
    const result = await db.query("SELECT NOW()");
    return NextResponse.json({ connected: true, time: result.rows[0].now });
  } catch (error) {
    return NextResponse.json(
      { connected: false, error: error instanceof Error ? error.message : String(error) },
      { status: 200 },
    );
  }
}
