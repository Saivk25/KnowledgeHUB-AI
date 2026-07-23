"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import AppShell from "@/components/AppShell";
import { FlashcardsPanel, QuizPanel, VivaPanel } from "@/components/StudyPanels";
import { api, ApiError, ConceptDetailOut, SummarizeResultOut } from "@/lib/api";

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
  // Milestone 9 (Intent Workflows): Summarize this concept -- an
  // on-demand intent request, distinct from Vision v2's Phase 2
  // "concept auto-synthesis" (a persisted, continuously-updated rolling
  // summary), which is explicitly out of this milestone's scope.
  const [summarizing, setSummarizing] = useState(false);
  const [summary, setSummary] = useState<string | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);

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

  const onSummarize = async () => {
    if (!detail) return;
    setSummarizing(true);
    setSummaryError(null);
    try {
      const conv = await api.createConversation();
      const res = await api.sendIntent(conv.id, { intent: "SUMMARIZE", conceptId: detail.concept.id });
      if (res.status !== "OK") {
        setSummaryError("Couldn't find enough evidence to summarize this concept.");
        return;
      }
      setSummary((res.result as SummarizeResultOut).content);
    } catch (err) {
      setSummaryError(err instanceof ApiError ? err.message : "Couldn't summarize this concept.");
    } finally {
      setSummarizing(false);
    }
  };

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

              {/* Milestone 9: Summarize this concept -- on-demand, not
                  the persisted rolling auto-synthesis Vision v2 Phase 2
                  describes (out of scope here). */}
              <div className="mt-4">
                <button
                  onClick={onSummarize}
                  disabled={summarizing}
                  className="rounded-lg border border-indigo px-3 py-1.5 text-xs font-medium text-indigo hover:bg-indigo/5 disabled:opacity-50"
                >
                  {summarizing ? "Summarizing…" : "Summarize what I know about this"}
                </button>
                {summaryError && <p className="mt-2 text-xs text-rose-700">{summaryError}</p>}
                {summary && <p className="mt-3 whitespace-pre-wrap text-sm text-slate-700">{summary}</p>}
              </div>

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

            {/* Milestone 10 (Study Workflows): Quiz me, Flashcards, Viva
                mode -- same three panels as the Document detail page,
                targeting this concept instead of a resource. */}
            <div className="space-y-4">
              <QuizPanel target={{ conceptId: detail.concept.id }} />
              <FlashcardsPanel target={{ conceptId: detail.concept.id }} />
              <VivaPanel target={{ conceptId: detail.concept.id }} />
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
