"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import StatusBadge from "@/components/StatusBadge";
import { api, ApiError, DocumentOut } from "@/lib/api";

export default function DocumentLibraryPage() {
  const [documents, setDocuments] = useState<DocumentOut[] | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const load = async () => {
    setError(null);
    try {
      const res = await api.listDocuments();
      setDocuments(res.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't load your documents.");
    }
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 4000); // light polling so status chips reflect background processing
    return () => clearInterval(interval);
  }, []);

  const filtered = useMemo(() => {
    if (!documents) return null;
    if (!query.trim()) return documents;
    return documents.filter((d) => d.filename.toLowerCase().includes(query.toLowerCase()));
  }, [documents, query]);

  const onDelete = async (id: string) => {
    if (!confirm("Delete this document? It will no longer be searchable.")) return;
    setDeletingId(id);
    try {
      await api.deleteDocument(id);
      setDocuments((prev) => (prev ? prev.filter((d) => d.id !== id) : prev));
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Couldn't delete this document.");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl px-8 py-10">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Documents</h1>
            <p className="mt-1 text-sm text-slate-500">{documents ? `${documents.length} document${documents.length === 1 ? "" : "s"}` : "Loading…"}</p>
          </div>
          <Link href="/documents/upload" className="rounded-lg bg-indigo px-4 py-2 text-sm font-medium text-white hover:bg-indigo/90">
            Upload PDF
          </Link>
        </div>

        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by filename…"
          className="mt-5 w-full max-w-sm rounded-lg border border-edge px-3 py-2 text-sm focus:border-indigo focus:outline-none focus:ring-1 focus:ring-indigo"
        />

        {error && (
          <div className="mt-4 flex items-center justify-between rounded-lg border border-rose/30 bg-rose/10 px-4 py-3 text-sm text-rose-700">
            {error}
            <button onClick={load} className="font-medium underline">Retry</button>
          </div>
        )}

        <div className="mt-4 overflow-hidden rounded-xl border border-edge bg-surface">
          {filtered === null ? (
            <div className="divide-y divide-edge">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="h-14 animate-pulse bg-slate-50" />
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <div className="p-10 text-center">
              <p className="text-sm text-slate-500">{documents && documents.length > 0 ? "No documents match your search." : "No documents yet."}</p>
              {documents && documents.length === 0 && (
                <Link href="/documents/upload" className="mt-3 inline-block rounded-lg bg-indigo px-4 py-2 text-sm font-medium text-white">
                  Upload your first PDF
                </Link>
              )}
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b border-edge bg-canvas text-left text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-4 py-3">Title</th>
                  <th className="px-4 py-3">Pages</th>
                  <th className="px-4 py-3">Uploaded</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-edge">
                {filtered.map((doc) => (
                  <tr key={doc.id} className="hover:bg-canvas">
                    <td className="px-4 py-3">
                      <Link href={`/documents/${doc.id}`} className="font-medium text-ink hover:text-indigo">
                        {doc.filename}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-slate-500">{doc.pageCount || "—"}</td>
                    <td className="px-4 py-3 text-slate-500">{new Date(doc.createdAt).toLocaleDateString()}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={doc.status} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      {/* Milestone 3 (Document Ingestion): "Ask About This" intentionally does not
                          link to /chat -- that route isn't mounted until Milestone 4 (RAG Chat).
                          A ready, indexed document is the Milestone 3 deliverable; asking questions
                          about it is the next milestone's, not this page's, job. */}
                      {doc.status === "READY" && (
                        <span className="mr-3 text-xs font-medium text-slate-400" title="AI Chat arrives in Milestone 4">
                          Indexed
                        </span>
                      )}
                      <button
                        onClick={() => onDelete(doc.id)}
                        disabled={deletingId === doc.id}
                        className="text-xs font-medium text-rose hover:underline disabled:opacity-50"
                      >
                        {deletingId === doc.id ? "Deleting…" : "Delete"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </AppShell>
  );
}
