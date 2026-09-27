import { randomBytes } from "crypto";
import { getDb } from "./db";

export const SESSION_COOKIE = "session";
const SESSION_DURATION_MS = 30 * 24 * 60 * 60 * 1000; // 30 days

export type SessionUser = {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
};

export async function createSession(userId: string): Promise<{ token: string; expiresAt: Date }> {
  const token = randomBytes(32).toString("hex");
  const expiresAt = new Date(Date.now() + SESSION_DURATION_MS);
  await getDb().query(
    "INSERT INTO sessions (token, user_id, expires_at) VALUES ($1, $2, $3)",
    [token, userId, expiresAt],
  );
  return { token, expiresAt };
}

export async function getUserBySessionToken(token: string | undefined): Promise<SessionUser | null> {
  if (!token) return null;
  const result = await getDb().query(
    `SELECT u.id, u.email, u.first_name, u.last_name
     FROM sessions s
     JOIN users u ON u.id = s.user_id
     WHERE s.token = $1 AND s.expires_at > now()`,
    [token],
  );
  return result.rows[0] ?? null;
}

export async function destroySession(token: string | undefined): Promise<void> {
  if (!token) return;
  await getDb().query("DELETE FROM sessions WHERE token = $1", [token]);
}
