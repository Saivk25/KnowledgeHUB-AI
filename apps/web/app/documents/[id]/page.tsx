"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import AppShell from "@/components/AppShell";
import CategoryBadge from "@/components/CategoryBadge";
import { api, ApiError, ContentCategory, DocumentOut, IngestionJobOut } from "@/lib/api";

const STEPS = [
  { key: "UPLOADED", label: "Uploaded" },
  { key: "EXTRACTING", label: "Extracting text" },
  { key: "CLASSIFYING", label: "Classifying content" },
  { key: "INDEXING", label: "Creating knowledge index" },
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
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [editingClassification, setEditingClassification] = useState(false);
  const [categoryDraft, setCategoryDraft] = useState<string>("");
  const [subjectDraft, setSubjectDraft] = useState<string>("");
  const [savingClassification, setSavingClassification] = useState(false);
  const [classificationError, setClassificationError] = useState<string | null>(null);

  const load = async () => {
    try {
      const res = await api.getDocumentDetail(params.id);
      setDocument(res.document);
      setJob(res.processingJob);
      setError(null);
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
                  {/* Milestone 3 (Document Ingestion): no link to /chat here -- that route
                      isn't mounted until Milestone 4 (RAG Chat). Being indexed and queryable
                      are two different milestones' deliverables. */}
                  <div className="mt-3 text-xs text-emerald-600/80">
                    Asking questions about this document arrives in Milestone 4.
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
                        <span className="text-sm text-slate-600">— {document.subject}</span>
                      )}
                      {document.extractionConfidence !== null && document.extractionConfidence < 1 && (
                        <span className="text-xs text-amber-700">
                          extraction confidence {Math.round(document.extractionConfidence * 100)}%
                        </span>
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
    </AppShell>
  );
}
