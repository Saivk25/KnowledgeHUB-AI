"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import { api, DocumentOut } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

// Milestone 3 (Document Ingestion): now that /api/v1/documents is mounted,
// this screen shows a real (if minimal) document count instead of the
// Milestone 2 placeholder ("Document upload arrives in Milestone 3").
// Errors are swallowed deliberately -- this is a summary tile, not the
// Documents page itself (/documents already has its own error handling),
// so a transient failure here should just show nothing rather than an
// alarming error banner on the workspace home screen.
export default function WorkspaceHomePage() {
  const { user, workspace } = useAuth();
  const [documents, setDocuments] = useState<DocumentOut[] | null>(null);

  useEffect(() => {
    api
      .listDocuments()
      .then((res) => setDocuments(res.items))
      .catch(() => setDocuments(null));
  }, []);

  const readyCount = documents?.filter((d) => d.status === "READY").length ?? null;

  return (
    <AppShell>
      <div className="mx-auto max-w-3xl px-8 py-10">
        <h1 className="text-2xl font-semibold text-ink">Welcome back{user ? `, ${user.displayName}` : ""}</h1>
        <p className="mt-1 text-slate-500">{workspace?.name}</p>

        <div className="mt-6 rounded-xl border border-edge bg-surface p-6">
          <h2 className="font-semibold text-ink">Your workspace is ready</h2>
          <p className="mt-1.5 text-sm text-slate-600">
            You are signed in and this is your private workspace -- isolated from every other account. AI chat
            over your documents is introduced in the milestone that follows.
          </p>
        </div>

        <div className="mt-6 flex items-center justify-between rounded-xl border border-edge bg-surface p-6">
          <div>
            <h2 className="font-semibold text-ink">Documents</h2>
            <p className="mt-1.5 text-sm text-slate-600">
              {documents === null
                ? "Loading…"
                : documents.length === 0
                ? "No documents yet."
                : `${documents.length} document${documents.length === 1 ? "" : "s"}, ${readyCount} ready.`}
            </p>
          </div>
          <Link href="/documents" className="rounded-lg bg-indigo px-4 py-2 text-sm font-medium text-white hover:bg-indigo/90">
            {documents && documents.length > 0 ? "View Documents" : "Upload a PDF"}
          </Link>
        </div>
      </div>
    </AppShell>
  );
}
