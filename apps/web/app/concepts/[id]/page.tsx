"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import AppShell from "@/components/AppShell";
import { api, ApiError, ConceptDetailOut } from "@/lib/api";

// Milestone 7 (Concept Graph): the concept detail page -- evidence
// (which resources support this concept, and how), one-hop related
// concepts, and a bare merge affordance when this concept was flagged as
// a possible duplicate. Deliberately minimal, per the approved design: no
// graph visualization, no auto-generated synthesis/summary.
export default function ConceptDetailPage() {
  const params = useParams<{ id: string }>();
  const [detail, setDetail] = useState<ConceptDetailOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [merging, setMerging] = useState(false);
  const [mergeError, setMergeError] = useState<string | null>(null);

  const load = async () => {
    try {
      const res = await api.getConceptDetail(params.id);
      setDetail(res);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't load this concept.");
    }
  };

  useEffect(() => {
    load();
  }, [params.id]);

  const onMerge = async () => {
    if (!detail?.concept.possibleDuplicateOfConceptId) return;
    setMerging(true);
    setMergeError(null);
    try {
      await api.mergeConcept(detail.concept.id, detail.concept.possibleDuplicateOfConceptId);
      await load();
    } catch (err) {
      setMergeError(err instanceof ApiError ? err.message : "Couldn't merge this concept.");
    } finally {
      setMerging(false);
    }
  };

  return (
    <AppShell>
      <div className="mx-auto max-w-2xl px-8 py-10">
        <Link href="/concepts" className="text-sm text-slate-400 hover:text-slate-600">
          ← Back to Concepts
        </Link>

        {error && (
          <div className="mt-6 rounded-lg border border-rose/30 bg-rose/10 px-4 py-3 text-sm text-rose-700">{error}</div>
        )}

        {!detail && !error && (
          <div className="mt-6 space-y-3">
            <div className="h-6 w-2/3 animate-pulse rounded bg-slate-100" />
            <div className="h-32 animate-pulse rounded-xl bg-slate-100" />
          </div>
        )}

        {detail && (
          <div className="mt-6 space-y-4">
            <div className="rounded-xl border border-edge bg-surface p-6">
              <h1 className="text-lg font-semibold text-ink">{detail.concept.name}</h1>
              {detail.concept.description && (
                <p className="mt-2 text-sm text-slate-600">{detail.concept.description}</p>
              )}
              <p className="mt-2 text-xs text-slate-400">
                {detail.concept.evidenceCount} evidence link{detail.concept.evidenceCount === 1 ? "" : "s"}
              </p>

              {detail.concept.possibleDuplicateOfConceptId && (
                <div className="mt-4 rounded-lg border border-amber/30 bg-amber/10 px-4 py-3 text-sm text-amber-700">
                  This might be the same concept as{" "}
                  <Link href={`/concepts/${detail.concept.possibleDuplicateOfConceptId}`} className="font-medium underline">
                    another one
                  </Link>
                  .
                  {mergeError && <p className="mt-1 text-xs text-rose-700">{mergeError}</p>}
                  <div className="mt-2">
                    <button
                      onClick={onMerge}
                      disabled={merging}
                      className="rounded-lg bg-indigo px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo/90 disabled:opacity-50"
                    >
                      {merging ? "Merging…" : "Merge into it"}
                    </button>
                  </div>
                </div>
              )}
            </div>

            <div className="rounded-xl border border-edge bg-surface p-6">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Evidence</p>
              {detail.evidence.length === 0 ? (
                <p className="mt-2 text-sm text-slate-500">No evidence yet.</p>
              ) : (
                <ul className="mt-3 space-y-3">
                  {detail.evidence.map((ev, idx) => (
                    <li key={idx} className="rounded-lg border border-edge px-4 py-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <Link href={`/documents/${ev.resourceId}`} className="font-medium text-ink hover:text-indigo">
                          {ev.filename}
                        </Link>
                        <span className="rounded-full border border-indigo/30 bg-indigo/10 px-2 py-0.5 text-xs font-medium text-indigo-700">
                          {ev.contributionType}
                        </span>
                        <span className="text-xs text-slate-400">{Math.round(ev.confidence * 100)}% confidence</span>
                      </div>
                      {ev.excerpt && <p className="mt-2 text-sm text-slate-600 line-clamp-2">{ev.excerpt}</p>}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="rounded-xl border border-edge bg-surface p-6">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Related concepts</p>
              {detail.related.length === 0 ? (
                <p className="mt-2 text-sm text-slate-500">
                  No related concepts yet -- typed relationships require an OpenAI-backed concept linker.
                </p>
              ) : (
                <ul className="mt-3 space-y-2">
                  {detail.related.map((rel) => (
                    <li key={rel.conceptId} className="flex items-center gap-2">
                      <Link href={`/concepts/${rel.conceptId}`} className="font-medium text-ink hover:text-indigo">
                        {rel.name}
                      </Link>
                      <span className="rounded-full border border-edge bg-canvas px-2 py-0.5 text-xs text-slate-500">
                        {rel.relationshipType}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
