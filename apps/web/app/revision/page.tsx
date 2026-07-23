"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import { api, ApiError, RevisionItemOut, RevisionResultOut } from "@/lib/api";

// Milestone 10 (Study Workflows): Revision mode -- "what needs my
// attention" across the whole workspace, ranked by
// app/services/study_signals.py's assess_review_need() (never-reviewed,
// low quiz score, or thin evidence). Deliberately read-only and
// stateless from this page's point of view: it's a fresh REVISION intent
// request on every load, not a persisted/cached recommendation list.
const PRIORITY_LABEL: Record<number, { label: string; className: string }> = {
  1: { label: "Most urgent", className: "border-rose/30 bg-rose/5 text-rose-700" },
  2: { label: "Needs attention", className: "border-amber/30 bg-amber/5 text-amber-700" },
  3: { label: "Worth a look", className: "border-sky/30 bg-sky/5 text-sky-700" },
  4: { label: "On track", className: "border-emerald/30 bg-emerald/5 text-emerald-700" },
};

export default function RevisionPage() {
  const [items, setItems] = useState<RevisionItemOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const conv = await api.createConversation();
      const res = await api.sendIntent(conv.id, { intent: "REVISION" });
      setItems((res.result as RevisionResultOut).items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't load your revision list.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <AppShell>
      <div className="mx-auto max-w-2xl px-8 py-10">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Revision</h1>
            <p className="mt-1 text-sm text-slate-500">What needs your attention, ranked by urgency.</p>
          </div>
          <button
            onClick={load}
            disabled={loading}
            className="rounded-lg border border-edge px-3 py-1.5 text-xs font-medium text-ink hover:bg-canvas disabled:opacity-50"
          >
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>

        {error && (
          <div className="mt-6 flex items-center justify-between rounded-lg border border-rose/30 bg-rose/10 px-4 py-3 text-sm text-rose-700">
            {error}
            <button onClick={load} className="font-medium underline">Retry</button>
          </div>
        )}

        {!items && !error && (
          <div className="mt-6 space-y-3">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-16 animate-pulse rounded-xl bg-slate-100" />
            ))}
          </div>
        )}

        {items && items.length === 0 && (
          <div className="mt-6 rounded-xl border border-edge bg-surface p-10 text-center">
            <p className="text-sm text-slate-500">
              Nothing to revise yet -- upload documents and link concepts to start building a revision list.
            </p>
          </div>
        )}

        {items && items.length > 0 && (
          <ul className="mt-6 space-y-3">
            {items.map((item, idx) => {
              const priority = PRIORITY_LABEL[item.priority] || PRIORITY_LABEL[4];
              const href = item.resourceId
                ? `/documents/${item.resourceId}`
                : item.conceptId
                ? `/concepts/${item.conceptId}`
                : null;
              return (
                <li key={idx} className={`rounded-xl border px-4 py-3 ${priority.className}`}>
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      {href ? (
                        <Link href={href} className="font-medium text-ink hover:text-indigo">
                          {item.label}
                        </Link>
                      ) : (
                        <p className="font-medium text-ink">{item.label}</p>
                      )}
                      <p className="mt-1 text-xs">{item.reason}</p>
                    </div>
                    <span className="shrink-0 rounded-full border border-current px-2 py-0.5 text-xs font-medium">
                      {priority.label}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </AppShell>
  );
}
