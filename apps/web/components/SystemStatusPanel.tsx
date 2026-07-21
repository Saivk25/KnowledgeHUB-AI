"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type State = "checking" | "up" | "down";

function Chip({ label, state, detail }: { label: string; state: State; detail?: string }) {
  const styles: Record<State, string> = {
    checking: "bg-slate-100 text-slate-500 border-slate-200",
    up: "bg-emerald/10 text-emerald-700 border-emerald/30",
    down: "bg-rose/10 text-rose-700 border-rose/30",
  };
  const labelText: Record<State, string> = { checking: "Checking…", up: "Up", down: "Down" };
  return (
    <div className={`flex items-center justify-between rounded-lg border px-4 py-3 ${styles[state]}`}>
      <div>
        <p className="text-sm font-medium">{label}</p>
        {detail && <p className="text-xs opacity-80">{detail}</p>}
      </div>
      <span className="flex items-center gap-1.5 text-xs font-semibold">
        <span className="h-1.5 w-1.5 rounded-full bg-current" />
        {labelText[state]}
      </span>
    </div>
  );
}

export default function SystemStatusPanel() {
  const [api_, setApiState] = useState<State>("checking");
  const [db, setDb] = useState<State>("checking");
  const [vectorDb, setVectorDb] = useState<State>("checking");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .liveness()
      .then(() => setApiState("up"))
      .catch(() => setApiState("down"));

    api
      .readiness()
      .then((r) => {
        setDb(r.components.database.status === "up" ? "up" : "down");
        setVectorDb(r.components.vector_db.status === "up" ? "up" : "down");
      })
      .catch(() => {
        setDb("down");
        setVectorDb("down");
        setError("Could not reach the API. Is the backend running?");
      });
  }, []);

  return (
    <div className="rounded-2xl border border-edge bg-surface p-6 shadow-sm text-left">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Milestone 1 -- Live system status</p>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <Chip label="API" state={api_} />
        <Chip label="Database (PostgreSQL)" state={db} />
        <Chip label="Vector DB (Qdrant)" state={vectorDb} />
      </div>
      {error && <p className="mt-3 text-xs text-rose-600">{error}</p>}
      <p className="mt-4 text-xs text-slate-400">
        This panel calls <code className="rounded bg-canvas px-1 py-0.5">GET /health</code> and{" "}
        <code className="rounded bg-canvas px-1 py-0.5">GET /health/ready</code> on the API directly from your
        browser -- it is the foundation this project is built on, wired end to end.
      </p>
    </div>
  );
}
