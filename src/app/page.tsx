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

export default function Home() {
  const health = useJson("/api/health");
  const dbHealth = useJson("/api/db-health");

  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <h1>sim4food - Vercel setup placeholder</h1>
        <p>This page is a temporary connectivity check. Real frontend design comes later.</p>
        <pre>{`/api/health -> ${JSON.stringify(health, null, 2)}`}</pre>
        <pre>{`/api/db-health -> ${JSON.stringify(dbHealth, null, 2)}`}</pre>
      </main>
    </div>
  );
}
