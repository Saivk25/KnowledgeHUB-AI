"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import CategoryBadge from "@/components/CategoryBadge";
import StatusBadge from "@/components/StatusBadge";
import { api, ApiError, DocumentOut, LOW_CONFIDENCE_THRESHOLD } from "@/lib/api";

// Milestone 11 (4.4): a document "needs review" when either its
// extraction or its (unconfirmed) classification confidence is below the
// shared threshold -- built entirely on fields DocumentOut already
// returns (extractionConfidence, contentCategoryConfidence,
// contentCategoryConfirmed), no new query parameter or route.
function needsReview(doc: DocumentOut): boolean {
  const lowExtraction = doc.extractionConfidence !== null && doc.extractionConfidence < LOW_CONFIDENCE_THRESHOLD;
  const lowClassification =
    !doc.contentCategoryConfirmed &&
    doc.contentCategoryConfidence !== null &&
    doc.contentCategoryConfidence < LOW_CONFIDENCE_THRESHOLD;
  return lowExtraction || lowClassification;
}

// The lower of the two confidences this row has an opinion on, used for
// the "lowest confidence first" sort and the per-row indicator below.
// null (unknown) sorts as the lowest possible confidence.
function lowestConfidence(doc: DocumentOut): number | null {
  const values = [doc.extractionConfidence, doc.contentCategoryConfirmed ? null : doc.contentCategoryConfidence].filter(
    (v): v is number => v !== null
  );
  return values.length > 0 ? Math.min(...values) : null;
}

export default function DocumentLibraryPage() {
  const [documents, setDocuments] = useState<DocumentOut[] | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [needsReviewOnly, setNeedsReviewOnly] = useState(false);
  const [sortByConfidence, setSortByConfidence] = useState(false);

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
    let items = documents;
    if (query.trim()) {
      items = items.filter((d) => d.filename.toLowerCase().includes(query.toLowerCase()));
    }
    if (needsReviewOnly) {
      items = items.filter(needsReview);
    }
    if (sortByConfidence) {
      items = [...items].sort((a, b) => {
        const ca = lowestConfidence(a);
        const cb = lowestConfidence(b);
        if (ca === null && cb === null) return 0;
        if (ca === null) return -1; // unknown confidence surfaces first, alongside genuinely low ones
        if (cb === null) return 1;
        return ca - cb;
      });
    }
    return items;
  }, [documents, query, needsReviewOnly, sortByConfidence]);

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

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by filename…"
            className="w-full max-w-sm rounded-lg border border-edge px-3 py-2 text-sm focus:border-indigo focus:outline-none focus:ring-1 focus:ring-indigo"
          />
          {/* Milestone 11 (4.4): triage view -- client-side only, built on
              extractionConfidence/contentCategoryConfidence/
              contentCategoryConfirmed, all already fetched by listDocuments(). */}
          <label className="flex items-center gap-1.5 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={needsReviewOnly}
              onChange={(e) => setNeedsReviewOnly(e.target.checked)}
            />
            Needs review only
          </label>
          <label className="flex items-center gap-1.5 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={sortByConfidence}
              onChange={(e) => setSortByConfidence(e.target.checked)}
            />
            Sort by lowest confidence
          </label>
        </div>

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
                  <th className="px-4 py-3">Category</th>
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
                      {needsReview(doc) && (
                        <span className="ml-2 rounded-full bg-amber/20 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-700">
                          Needs review
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <CategoryBadge category={doc.contentCategory} />
                    </td>
                    <td className="px-4 py-3 text-slate-500">{doc.pageCount || "—"}</td>
                    <td className="px-4 py-3 text-slate-500">{new Date(doc.createdAt).toLocaleDateString()}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={doc.status} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      {/* Milestone 8 (Local-First Retrieval & Provenance): /chat is
                          now a live route -- a ready, indexed document can be asked
                          about directly. */}
                      {doc.status === "READY" && (
                        <Link href="/chat" className="mr-3 text-xs font-medium text-indigo hover:underline">
                          Ask About This
                        </Link>
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
