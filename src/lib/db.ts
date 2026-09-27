import { Pool } from "pg";

let pool: Pool | undefined;

function compatibleConnectionString(connectionString: string): string {
  const url = new URL(connectionString);
  if (url.searchParams.get("sslmode") === "require" && !url.searchParams.has("uselibpqcompat")) {
    url.searchParams.set("uselibpqcompat", "true");
  }
  return url.toString();
}

export function getDb(): Pool {
  if (!process.env.POSTGRES_URL) {
    throw new Error("POSTGRES_URL is not set");
  }
  if (!pool) {
    pool = new Pool({ connectionString: compatibleConnectionString(process.env.POSTGRES_URL) });
  }
  return pool;
}
