import { Pool } from "pg";

let pool: Pool | undefined;

export function getDb(): Pool {
  if (!process.env.POSTGRES_URL) {
    throw new Error("POSTGRES_URL is not set");
  }
  if (!pool) {
    pool = new Pool({ connectionString: process.env.POSTGRES_URL });
  }
  return pool;
}
