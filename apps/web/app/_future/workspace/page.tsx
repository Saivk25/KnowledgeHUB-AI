"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import StatusBadge from "@/components/StatusBadge";
import { api, DocumentOut } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

export default function WorkspaceHomePage() {
  const { user, workspace } = useAuth();
  const [documents, setDocuments] = useState<DocumentOut[] | null>(null);
  const [stats, setStats] = useState<{ readyDocuments: number; processingDocuments: number; failedDocuments: number } | null>(null);
  const [error, setError] = useState(false);

  const load = async () => {
    setError(false);
    try {
      const [docsRes, wsRes] = await Promise.all([api.listDocuments(), api.getWorkspace()]);
      setDocuments(docsRes.items);
      setStats(wsRes.stats);
    } catch {
      setError(true);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl px-8 py-10">
        <h1 className="text-2xl font-semibold text-ink">Welcome back{user ? `, ${user.displayName}` : ""}</h1>
        <p className="mt-1 text-slate-500">{workspace?.name}</p>

        {error && (
          <div className="mt-6 flex items-center justify-between rounded-lg border border-rose/30 bg-rose/10 px-4 py-3 text-sm text-rose-700">
            Couldn&apos;t load your workspace summary.
            <button onClick={load} className="font-medium underline">
              Retry
            </button>
          </div>
        )}

        <div className="mt-6 grid gap-4 sm:grid-cols-3">
          {[
            { label: "Ready documents", value: stats?.readyDocuments, color: "text-emerald" },
            { label: "Processing", value: stats?.processingDocuments, color: "text-amber" },
            { label: "Failed", value: stats?.failedDocuments, color: "text-rose" },
          ].map((card) => (
            <div key={card.label} className="rounded-xl border border-edge bg-surface p-4">
              {stats === null && !error ? (
                <div className="h-8 w-12 animate-pulse rounded bg-slate-100" />
              ) : (
                <p className={`text-2xl font-semibold ${card.color}`}>{card.value ?? 0}</p>
              )}
              <p className="mt-1 text-sm text-slate-500">{card.label}</p>
            </div>
          ))}
        </div>

        <div className="mt-6 rounded-xl border border-edge bg-surface p-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-semibold text-ink">Upload your first document</h2>
              <p className="mt-1 text-sm text-slate-500">Add a PDF and KnowledgeHub AI will make it instantly searchable.</p>
            </div>
            <Link href="/documents/upload" className="rounded-lg bg-indigo px-4 py-2 text-sm font-medium text-white hover:bg-indigo/90">
              Upload PDF
            </Link>
          </div>
        </div>

        <div className="mt-6">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-ink">Recent documents</h2>
            <Link href="/documents" className="text-sm font-medium text-indigo hover:underline">
              View Library
            </Link>
          </div>

          <div className="mt-3 rounded-xl border border-edge bg-surface">
            {documents === null ? (
              <div className="divide-y divide-edge">
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="h-14 animate-pulse bg-slate-50" />
                ))}
              </div>
            ) : documents.length === 0 ? (
              <div className="p-8 text-center">
                <p className="text-sm text-slate-500">Your workspace is empty. Upload a PDF to begin.</p>
                <Link href="/documents/upload" className="mt-3 inline-block rounded-lg bg-indigo px-4 py-2 text-sm font-medium text-white">
                  Upload PDF
                </Link>
              </div>
            ) : (
              <div className="divide-y divide-edge">
                {documents.slice(0, 5).map((doc) => (
                  <Link
                    key={doc.id}
                    href={`/documents/${doc.id}`}
                    className="flex items-center justify-between px-4 py-3 hover:bg-canvas"
                  >
                    <span className="truncate text-sm text-ink">{doc.filename}</span>
                    <StatusBadge status={doc.status} />
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>

        {documents && documents.some((d) => d.status === "READY") && (
          <div className="mt-6 flex items-center justify-between rounded-xl border border-indigo/20 bg-indigo/5 p-4">
            <p className="text-sm text-ink">Your knowledge base is ready. Ask it something.</p>
            <Link href="/chat" className="rounded-lg bg-indigo px-4 py-2 text-sm font-medium text-white hover:bg-indigo/90">
              Open AI Chat
            </Link>
          </div>
        )}
      </div>
    </AppShell>
  );
}
