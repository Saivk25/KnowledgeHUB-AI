"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import AppShell from "@/components/AppShell";
import CategoryBadge from "@/components/CategoryBadge";
import CitationPill from "@/components/CitationPill";
import SourceViewerModal from "@/components/SourceViewerModal";
import { FlashcardsPanel, QuizPanel, VivaPanel } from "@/components/StudyPanels";
import {
  api,
  ApiError,
  CitationOut,
  ConceptLinkOut,
  ContentCategory,
  CorrectionOut,
  DocumentOut,
  IngestionJobOut,
  LOW_CONFIDENCE_THRESHOLD,
  SummarizeResultOut,
} from "@/lib/api";

const STEPS = [
  { key: "UPLOADED", label: "Uploaded" },
  { key: "EXTRACTING", label: "Extracting text" },
  { key: "CLASSIFYING", label: "Classifying content" },
  { key: "INDEXING", label: "Creating knowledge index" },
  { key: "CONCEPT_LINKING", label: "Linking concepts" },
  { key: "DONE", label: "Ready" },
];

const CATEGORY_OPTIONS: ContentCategory[] = [
  "LECTURE",
  "ASSIGNMENT",
  "QUESTION_PAPER",
  "LAB_MANUAL",
  "RESEARCH_PAPER",
  "PERSONAL_NOTE",
  "OTHER",
];

function stepIndex(step: string | undefined) {
  const idx = STEPS.findIndex((s) => s.key === step);
  return idx === -1 ? 0 : idx;
}

export default function DocumentDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [document, setDocument] = useState<DocumentOut | null>(null);
  const [job, setJob] = useState<IngestionJobOut | null>(null);
  const [concepts, setConcepts] = useState<ConceptLinkOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [editingClassification, setEditingClassification] = useState(false);
  const [categoryDraft, setCategoryDraft] = useState<string>("");
  const [subjectDraft, setSubjectDraft] = useState<string>("");
  const [savingClassification, setSavingClassification] = useState(false);
  const [classificationError, setClassificationError] = useState<string | null>(null);
  // Milestone 9 (Intent Workflows): the Summarize entry point this page
  // adds, per the approved design (docs/milestones/MILESTONE_9.md Section
  // 3.7) -- a self-contained panel, not a redesign of this page.
  const [summarizing, setSummarizing] = useState(false);
  const [summary, setSummary] = useState<{ content: string; citations: CitationOut[] } | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [activeCitation, setActiveCitation] = useState<CitationOut | null>(null);
  // Milestone 11 (Confidence & Correction UX): correction history log,
  // the re-extraction affordance, and the reclassification-suggestion
  // banner's client-only dismissal state -- see docs/milestones/MILESTONE_11.md.
  const [corrections, setCorrections] = useState<CorrectionOut[]>([]);
  const [reextracting, setReextracting] = useState(false);
  const [suggestionDismissed, setSuggestionDismissed] = useState(false);

  const load = async () => {
    try {
      const res = await api.getDocumentDetail(params.id);
      setDocument(res.document);
      setJob(res.processingJob);
      setConcepts(res.concepts || []);
      setError(null);
      if (res.document.status === "READY") {
        const correctionsRes = await api.getCorrections(params.id);
        setCorrections(correctionsRes.items);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't load this document.");
    }
  };

  useEffect(() => {
    load();
    const interval = setInterval(() => {
      if (document?.status === "READY" || document?.status === "FAILED") return;
      load();
    }, 1500);
    return () => clearInterval(interval);
  }, [params.id, document?.status]);

  const onRetry = async () => {
    setRetrying(true);
    try {
      await api.retryDocument(params.id);
      await load();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Couldn't retry this document.");
    } finally {
      setRetrying(false);
    }
  };

  const startEditingClassification = () => {
    setCategoryDraft(document?.contentCategory || "OTHER");
    setSubjectDraft(document?.subject || "");
    setClassificationError(null);
    setEditingClassification(true);
  };

  // Milestone 11: re-run extraction on an already-READY document with a
  // low extraction confidence, without going through the FAILED-only
  // /retry route (a wholly separate, additive endpoint -- see
  // docs/milestones/MILESTONE_11.md Section 4.6).
  const onReextract = async () => {
    setReextracting(true);
    try {
      await api.reextractDocument(params.id);
      await load();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Couldn't re-run extraction on this document.");
    } finally {
      setReextracting(false);
    }
  };

  // Milestone 11: accept the automatic classifier's latest suggestion for
  // a field, using the existing updateClassification client method
  // unchanged -- "Use this" is just a PATCH with the auto_* value.
  const onAcceptSuggestion = async (field: "contentCategory" | "subject", value: string) => {
    setSavingClassification(true);
    try {
      const updated = await api.updateClassification(params.id, { [field]: value });
      setDocument(updated);
      const correctionsRes = await api.getCorrections(params.id);
      setCorrections(correctionsRes.items);
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Couldn't apply this suggestion.");
    } finally {
      setSavingClassification(false);
    }
  };

  const onSummarize = async () => {
    setSummarizing(true);
    setSummaryError(null);
    try {
      const conv = await api.createConversation();
      const res = await api.sendIntent(conv.id, { intent: "SUMMARIZE", resourceId: params.id });
      if (res.status !== "OK") {
        setSummaryError("Couldn't find enough evidence to summarize this document.");
        return;
      }
      const result = res.result as SummarizeResultOut;
      setSummary({ content: result.content, citations: res.citations });
    } catch (err) {
      setSummaryError(err instanceof ApiError ? err.message : "Couldn't summarize this document.");
    } finally {
      setSummarizing(false);
    }
  };

  const onSaveClassification = async () => {
    setSavingClassification(true);
    setClassificationError(null);
    try {
      const updated = await api.updateClassification(params.id, {
        contentCategory: categoryDraft,
        subject: subjectDraft,
      });
      setDocument(updated);
      setEditingClassification(false);
    } catch (err) {
      setClassificationError(err instanceof ApiError ? err.message : "Couldn't save this correction.");
    } finally {
      setSavingClassification(false);
    }
  };

  return (
    <AppShell>
      <div className="mx-auto max-w-2xl px-8 py-10">
        <Link href="/documents" className="text-sm text-slate-400 hover:text-slate-600">
          ← Back to Library
        </Link>

        {error && (
          <div className="mt-6 rounded-lg border border-rose/30 bg-rose/10 px-4 py-3 text-sm text-rose-700">{error}</div>
        )}

        {!document && !error && (
          <div className="mt-6 space-y-3">
            <div className="h-6 w-2/3 animate-pulse rounded bg-slate-100" />
            <div className="h-32 animate-pulse rounded-xl bg-slate-100" />
          </div>
        )}

        {document && (
          <div className="mt-6 rounded-xl border border-edge bg-surface p-6">
            <h1 className="text-lg font-semibold text-ink">{document.filename}</h1>

            {document.status === "FAILED" ? (
              <div className="mt-6">
                <div className="rounded-lg border border-rose/30 bg-rose/10 px-4 py-3 text-sm text-rose-700">
                  We could not process this PDF. {document.errorMessage}
                </div>
                <button
                  onClick={onRetry}
                  disabled={retrying}
                  className="mt-4 rounded-lg bg-indigo px-4 py-2 text-sm font-medium text-white hover:bg-indigo/90 disabled:opacity-50"
                >
                  {retrying ? "Retrying…" : "Retry Processing"}
                </button>
              </div>
            ) : document.status === "READY" ? (
              <div className="mt-6 space-y-4">
                <div className="rounded-lg border border-emerald/30 bg-emerald/10 px-4 py-3 text-sm text-emerald-700">
                  This document is ready — {document.pageCount} pages indexed.
                  {/* Milestone 8 (Local-First Retrieval & Provenance): /chat is a
                      live route now that indexing and retrieval are both shipped. */}
                  <div className="mt-3 text-xs text-emerald-600/80">
                    <Link href="/chat" className="font-medium text-emerald-700 hover:underline">
                      Ask a question about this document
                    </Link>
                  </div>
                </div>

                {/* Milestone 6: classification + confidence. Stored/computed
                    since ingestion; this is the first milestone that surfaces
                    it in the UI, with a manual-correction affordance. */}
                <div className="rounded-lg border border-edge bg-surface px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Classification</p>

                  {!editingClassification ? (
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <CategoryBadge category={document.contentCategory} />
                      {document.contentCategoryConfidence !== null && !document.contentCategoryConfirmed && (
                        <span className="text-xs text-slate-400">
                          {Math.round(document.contentCategoryConfidence * 100)}% confidence
                        </span>
                      )}
                      {document.contentCategoryConfirmed && (
                        <span className="text-xs text-slate-400">confirmed by you</span>
                      )}
                      {document.subject && (
                        <span className="text-sm text-slate-600">
                          — {document.subject}
                          {/* Milestone 11 (4.5): subjectConfidence was already
                              returned by the API but never rendered -- a pure
                              display fix, exactly mirroring how
                              contentCategoryConfidence is shown above. */}
                          {document.subjectConfidence !== null && !document.subjectConfirmed && (
                            <span className="ml-1 text-xs text-slate-400">
                              ({Math.round(document.subjectConfidence * 100)}% confidence)
                            </span>
                          )}
                          {document.subjectConfirmed && (
                            <span className="ml-1 text-xs text-slate-400">(confirmed by you)</span>
                          )}
                        </span>
                      )}
                      {document.extractionConfidence !== null && document.extractionConfidence < 1 && (
                        <span className="text-xs text-amber-700">
                          extraction confidence {Math.round(document.extractionConfidence * 100)}%
                        </span>
                      )}
                      {/* Milestone 11 (4.6): re-run extraction for a
                          low-confidence READY resource -- a new, additive
                          route, never touching /retry. */}
                      {document.extractionConfidence !== null &&
                        document.extractionConfidence < LOW_CONFIDENCE_THRESHOLD && (
                          <button
                            onClick={onReextract}
                            disabled={reextracting}
                            className="text-xs font-medium text-amber-700 hover:underline disabled:opacity-50"
                          >
                            {reextracting ? "Re-running…" : "Re-run extraction"}
                          </button>
                        )}
                      <button
                        onClick={startEditingClassification}
                        className="text-xs font-medium text-indigo hover:underline"
                      >
                        Edit
                      </button>
                    </div>
                  ) : (
                    <div className="mt-2 space-y-2">
                      <select
                        value={categoryDraft}
                        onChange={(e) => setCategoryDraft(e.target.value)}
                        className="w-full rounded-lg border border-edge bg-surface px-3 py-2 text-sm text-ink"
                      >
                        {CATEGORY_OPTIONS.map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </select>
                      <input
                        value={subjectDraft}
                        onChange={(e) => setSubjectDraft(e.target.value)}
                        placeholder="Subject (optional)"
                        className="w-full rounded-lg border border-edge bg-surface px-3 py-2 text-sm text-ink"
                      />
                      {classificationError && <p className="text-xs text-rose-700">{classificationError}</p>}
                      <div className="flex gap-2">
                        <button
                          onClick={onSaveClassification}
                          disabled={savingClassification}
                          className="rounded-lg bg-indigo px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo/90 disabled:opacity-50"
                        >
                          {savingClassification ? "Saving…" : "Save"}
                        </button>
                        <button
                          onClick={() => setEditingClassification(false)}
                          className="rounded-lg border border-edge px-3 py-1.5 text-xs font-medium text-ink hover:bg-canvas"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                {/* Milestone 11 (4.2): reclassification-suggestion banner --
                    shown only when the latest automatic run disagrees with
                    the (possibly already-corrected) authoritative field.
                    "Use this" reuses updateClassification unchanged; "Keep
                    mine" is a client-only dismissal (no persistence, per
                    Design Decision 3). */}
                {!suggestionDismissed &&
                  ((document.autoContentCategory && document.autoContentCategory !== document.contentCategory) ||
                    (document.autoSubject && document.autoSubject !== document.subject)) && (
                    <div className="rounded-lg border border-amber/40 bg-amber/10 px-4 py-3">
                      <p className="text-xs font-semibold uppercase tracking-wide text-amber-700">
                        Updated classification available
                      </p>
                      <div className="mt-2 space-y-1.5 text-sm text-amber-900">
                        {document.autoContentCategory && document.autoContentCategory !== document.contentCategory && (
                          <div className="flex items-center gap-2">
                            <span>Category: {document.autoContentCategory}</span>
                            <button
                              onClick={() => onAcceptSuggestion("contentCategory", document.autoContentCategory!)}
                              className="text-xs font-medium text-indigo hover:underline"
                            >
                              Use this
                            </button>
                          </div>
                        )}
                        {document.autoSubject && document.autoSubject !== document.subject && (
                          <div className="flex items-center gap-2">
                            <span>Subject: {document.autoSubject}</span>
                            <button
                              onClick={() => onAcceptSuggestion("subject", document.autoSubject!)}
                              className="text-xs font-medium text-indigo hover:underline"
                            >
                              Use this
                            </button>
                          </div>
                        )}
                      </div>
                      <button
                        onClick={() => setSuggestionDismissed(true)}
                        className="mt-2 text-xs font-medium text-amber-700 hover:underline"
                      >
                        Keep mine
                      </button>
                    </div>
                  )}

                {/* Milestone 11 (4.1): correction history -- every
                    classification correction ever applied to this
                    document, newest first, read-only. */}
                {corrections.length > 0 && (
                  <div className="rounded-lg border border-edge bg-surface px-4 py-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                      Correction history
                    </p>
                    <ul className="mt-2 space-y-1.5 text-xs text-slate-500">
                      {corrections.map((c) => (
                        <li key={c.id}>
                          <span className="font-medium text-slate-600">
                            {c.field === "CONTENT_CATEGORY" ? "Category" : "Subject"}
                          </span>{" "}
                          changed from{" "}
                          <span className="text-slate-600">{c.previousValue ?? "(none)"}</span> to{" "}
                          <span className="text-slate-600">{c.newValue}</span> on{" "}
                          {new Date(c.correctedAt).toLocaleString()}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Milestone 7: this document's evidence links into the
                    concept graph. Deliberately minimal -- no redesign,
                    no filtering, just the concepts this document
                    evidences, linking to each concept's own page. */}
                <div className="rounded-lg border border-edge bg-surface px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Concepts</p>
                  {concepts.length === 0 ? (
                    <p className="mt-2 text-sm text-slate-500">No concepts linked yet.</p>
                  ) : (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {concepts.map((c) => (
                        <Link
                          key={c.conceptId}
                          href={`/concepts/${c.conceptId}`}
                          className="inline-flex items-center gap-1.5 rounded-full border border-indigo/30 bg-indigo/10 px-2.5 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo/20"
                        >
                          {c.name}
                          <span className="text-indigo-500">· {c.contributionType.toLowerCase()}</span>
                        </Link>
                      ))}
                    </div>
                  )}
                </div>

                {/* Milestone 9: Summarize this document -- an on-demand
                    intent request, not an auto-generated/persisted
                    synthesis (that's Vision v2's Phase 2 concept-
                    synthesis feature, explicitly out of this milestone's
                    scope). */}
                <div className="rounded-lg border border-edge bg-surface px-4 py-3">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Summary</p>
                    <button
                      onClick={onSummarize}
                      disabled={summarizing}
                      className="rounded-lg border border-indigo px-3 py-1.5 text-xs font-medium text-indigo hover:bg-indigo/5 disabled:opacity-50"
                    >
                      {summarizing ? "Summarizing…" : "Summarize this document"}
                    </button>
                  </div>
                  {summaryError && <p className="mt-2 text-xs text-rose-700">{summaryError}</p>}
                  {summary && (
                    <div className="mt-3">
                      <p className="whitespace-pre-wrap text-sm text-slate-700">{summary.content}</p>
                      {summary.citations.length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-1.5 border-t border-edge pt-3">
                          {summary.citations.map((c) => (
                            <CitationPill key={c.order} citation={c} onOpen={setActiveCitation} />
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Milestone 10 (Study Workflows): Quiz me, Flashcards,
                    Viva mode -- three self-contained panels, same
                    "on-demand intent request" shape as Summarize above,
                    reused from concepts/[id]/page.tsx via StudyPanels.tsx. */}
                <QuizPanel target={{ resourceId: params.id }} />
                <FlashcardsPanel target={{ resourceId: params.id }} />
                <VivaPanel target={{ resourceId: params.id }} />
              </div>
            ) : (
              <div className="mt-6">
                <ol className="space-y-3">
                  {STEPS.map((step, idx) => {
                    const current = stepIndex(job?.step);
                    const done = idx < current;
                    const active = idx === current;
                    return (
                      <li key={step.key} className="flex items-center gap-3">
                        <span
                          className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium ${
                            done
                              ? "bg-emerald text-white"
                              : active
                              ? "bg-amber text-white animate-pulse"
                              : "bg-slate-100 text-slate-400"
                          }`}
                        >
                          {done ? "✓" : idx + 1}
                        </span>
                        <span className={`text-sm ${active ? "font-medium text-ink" : "text-slate-500"}`}>{step.label}</span>
                      </li>
                    );
                  })}
                </ol>
                <p className="mt-5 text-xs text-slate-400">You can leave this page — processing continues in the background.</p>
              </div>
            )}
          </div>
        )}
      </div>
      {activeCitation && <SourceViewerModal citation={activeCitation} onClose={() => setActiveCitation(null)} />}
    </AppShell>
  );
}
