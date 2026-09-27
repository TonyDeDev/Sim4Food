"use client";

import { useEffect, useState } from "react";
import styles from "./page.module.css";

type HealthState =
  | { status: "loading" }
  | { status: "ok"; data: unknown }
  | { status: "error"; message: string };

function useJson(url: string): HealthState {
  const [state, setState] = useState<HealthState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    fetch(url)
      .then((res) => res.json())
      .then((data) => {
        if (!cancelled) setState({ status: "ok", data });
      })
      .catch((err) => {
        if (!cancelled) setState({ status: "error", message: String(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [url]);

  return state;
}

export default function HealthCheck() {
  const health = useJson("/api/health");
  const dbHealth = useJson("/api/db-health");

  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <h1>sim4food - connectivity check</h1>
        <p>Diagnostic page for Postgres/Next.js wiring. Not part of the product UI.</p>
        <pre>{`/api/health -> ${JSON.stringify(health, null, 2)}`}</pre>
        <pre>{`/api/db-health -> ${JSON.stringify(dbHealth, null, 2)}`}</pre>
      </main>
    </div>
  );
}
