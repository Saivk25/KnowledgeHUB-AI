"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import CitationPill from "@/components/CitationPill";
import SourceViewerModal from "@/components/SourceViewerModal";
import { api, ApiError, CitationOut, Provenance, SearchResultOut, SUFFICIENCY_REASON_LABELS } from "@/lib/api";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  status?: "OK" | "INSUFFICIENT" | "ERROR";
  provenance?: Provenance | null;
  retrievalConfidence?: number;
  canOfferExternalFallback?: boolean;
  citations?: CitationOut[];
  // The question this assistant message answered -- kept so the external
  // fallback confirmation button below can resend it with consent.
  sourceQuestion?: string;
  // Milestone 11 (Confidence & Correction UX): sufficiencyScore was
  // already returned by both AnswerOut and IntentResponse since
  // Milestone 8, but this component never copied it into ChatMessage
  // state -- a pure "expose an already-returned field" fix, not a
  // backend change. sufficiencyReason is a genuinely new schema field
  // this milestone adds, powering the "Why?" affordance below.
  sufficiencyScore?: number;
  sufficiencyReason?: string | null;
}

const SUGGESTIONS = [
  "Summarize the key points of this document.",
  "What are the main risks or obligations mentioned?",
  "What is the approval process described here?",
];

// Milestone 8 (Local-First Retrieval & Provenance): the one new visual
// addition alongside every assistant answer, per the approved design ("Only
// add: provenance badge, retrieval confidence, external fallback
// confirmation. Do not redesign the interface.").
function ProvenanceBadge({ provenance, confidence }: { provenance: Provenance | null | undefined; confidence?: number }) {
  if (!provenance) return null;
  const styles: Record<Provenance, string> = {
    LOCAL: "bg-emerald/10 text-emerald-700 border-emerald/30",
    HYBRID: "bg-amber-100 text-amber-800 border-amber-300",
    EXTERNAL: "bg-slate-100 text-slate-600 border-slate-300",
  };
  const labels: Record<Provenance, string> = {
    LOCAL: "From your documents",
    HYBRID: "Documents + general knowledge",
    EXTERNAL: "General knowledge (not your documents)",
  };
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium ${styles[provenance]}`}
    >
      {labels[provenance]}
      {typeof confidence === "number" && provenance !== "EXTERNAL" && (
        <span className="opacity-70">· {Math.round(confidence * 100)}% confidence</span>
      )}
    </span>
  );
}

export default function ChatPage() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [readyCount, setReadyCount] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  // Milestone 9 (Intent Workflows): the one new UI affordance this
  // milestone adds to the chat compose bar, per the approved design's
  // "Explain (default) / Search" toggle (docs/milestones/MILESTONE_9.md
  // Section 3.7) -- Compare/Summarize get their own entry points
  // elsewhere (concepts list, resource/concept detail pages) rather than
  // living in this same freeform-question box.
  const [mode, setMode] = useState<"EXPLAIN" | "SEARCH">("EXPLAIN");
  const [phase, setPhase] = useState<"idle" | "searching" | "generating">("idle");
  const [error, setError] = useState<string | null>(null);
  const [activeCitation, setActiveCitation] = useState<CitationOut | null>(null);
  // Milestone 11: which assistant message currently has its "Why?"
  // sufficiency-reason explanation expanded (at most one at a time).
  const [whyOpenId, setWhyOpenId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    (async () => {
      try {
        const ws = await api.getWorkspace();
        setReadyCount(ws.stats?.readyDocuments ?? 0);
        const conv = await api.createConversation();
        setConversationId(conv.id);
      } catch {
        setReadyCount(0);
      }
    })();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, phase]);

  const send = async (content: string, useExternalFallback = false) => {
    if (!conversationId || !content.trim()) return;
    setError(null);
    setInput("");
    if (!useExternalFallback) {
      setMessages((prev) => [...prev, { id: `local-${Date.now()}`, role: "user", content }]);
    }
    setPhase("searching");
    setTimeout(() => setPhase((p) => (p === "searching" ? "generating" : p)), 500);

    try {
      if (mode === "SEARCH" && !useExternalFallback) {
        const res = await api.sendIntent(conversationId, { intent: "SEARCH", question: content });
        const searchResult = res.result as SearchResultOut;
        setMessages((prev) => [
          ...prev,
          {
            id: `search-${Date.now()}`,
            role: "assistant",
            content:
              searchResult.assistedSynthesis ??
              (searchResult.hits.length > 0
                ? `Found ${searchResult.hits.length} matching result${searchResult.hits.length === 1 ? "" : "s"}.`
                : "No matches found in your workspace."),
            status: res.status,
            provenance: res.provenance,
            retrievalConfidence: res.retrievalConfidence,
            canOfferExternalFallback: false,
            citations: searchResult.hits,
            sourceQuestion: content,
            sufficiencyScore: res.sufficiencyScore,
            sufficiencyReason: res.sufficiencyReason,
          },
        ]);
      } else {
        const res = await api.sendMessage(conversationId, content, useExternalFallback);
        setMessages((prev) => [
          ...prev,
          {
            id: res.answer.id,
            role: "assistant",
            content: res.answer.content,
            status: res.answer.status,
            provenance: res.answer.provenance,
            retrievalConfidence: res.answer.retrievalConfidence,
            canOfferExternalFallback: res.answer.canOfferExternalFallback,
            citations: res.answer.citations,
            sourceQuestion: content,
            sufficiencyScore: res.answer.sufficiencyScore,
            sufficiencyReason: res.answer.sufficiencyReason,
          },
        ]);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong while generating the answer.");
    } finally {
      setPhase("idle");
    }
  };

  return (
    <AppShell>
      <div className="flex h-screen flex-col">
        <div className="border-b border-edge bg-surface px-8 py-4">
          <h1 className="font-semibold text-ink">AI Chat</h1>
          <p className="text-sm text-slate-500">
            {readyCount === null ? "Loading your knowledge base…" : `${readyCount} ready document${readyCount === 1 ? "" : "s"} in this workspace`}
          </p>
        </div>

        <div className="flex-1 overflow-y-auto px-8 py-6">
          {readyCount === 0 ? (
            <div className="mx-auto max-w-md rounded-xl border border-edge bg-surface p-8 text-center">
              <p className="text-sm text-slate-600">
                You need at least one <strong>Ready</strong> document before you can ask a question.
              </p>
              <Link href="/documents/upload" className="mt-4 inline-block rounded-lg bg-indigo px-4 py-2 text-sm font-medium text-white">
                Upload a PDF
              </Link>
            </div>
          ) : messages.length === 0 ? (
            <div className="mx-auto max-w-md text-center">
              <p className="text-sm text-slate-500">Ask a question about your uploaded documents.</p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="rounded-full border border-edge bg-surface px-3 py-1.5 text-xs text-slate-600 hover:border-indigo hover:text-indigo"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-2xl space-y-5">
              {messages.map((m) => (
                <div key={m.id} className={m.role === "user" ? "text-right" : ""}>
                  <div
                    className={`inline-block max-w-[85%] rounded-xl px-4 py-2.5 text-left text-sm ${
                      m.role === "user" ? "bg-indigo text-white" : "border border-edge bg-surface text-ink"
                    }`}
                  >
                    {m.role === "assistant" && m.provenance && (
                      <div className="mb-2 flex flex-wrap items-center gap-2">
                        <ProvenanceBadge provenance={m.provenance} confidence={m.retrievalConfidence} />
                        {/* Milestone 11 (4.3): sufficiencyScore was already
                            returned by the API but dropped here -- now
                            rendered, plus a "Why?" affordance mapping the
                            newly-exposed sufficiencyReason to a sentence. */}
                        {typeof m.sufficiencyScore === "number" && (
                          <span className="text-[11px] text-slate-400">
                            sufficiency {Math.round(m.sufficiencyScore * 100)}%
                          </span>
                        )}
                        {m.sufficiencyReason && (
                          <button
                            onClick={() => setWhyOpenId(whyOpenId === m.id ? null : m.id)}
                            className="text-[11px] font-medium text-indigo hover:underline"
                          >
                            Why?
                          </button>
                        )}
                      </div>
                    )}
                    {whyOpenId === m.id && m.sufficiencyReason && (
                      <p className="mb-2 rounded-md bg-canvas px-2.5 py-1.5 text-xs text-slate-500">
                        {SUFFICIENCY_REASON_LABELS[m.sufficiencyReason] ?? m.sufficiencyReason}
                      </p>
                    )}
                    <p className="whitespace-pre-wrap">{m.content}</p>
                    {m.citations && m.citations.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1.5 border-t border-edge pt-3">
                        {m.citations.map((c) => (
                          <CitationPill key={c.order} citation={c} onOpen={setActiveCitation} />
                        ))}
                      </div>
                    )}
                    {/* Milestone 8: external fallback confirmation -- only ever
                        offered, never assumed, when local evidence is
                        insufficient (approved design: fail closed). */}
                    {m.role === "assistant" && m.status === "INSUFFICIENT" && m.canOfferExternalFallback && (
                      <div className="mt-3 border-t border-edge pt-3">
                        <button
                          onClick={() => m.sourceQuestion && send(m.sourceQuestion, true)}
                          className="rounded-lg border border-indigo px-3 py-1.5 text-xs font-medium text-indigo hover:bg-indigo/5"
                        >
                          Answer using general knowledge instead
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {phase !== "idle" && (
                <div>
                  <div className="inline-block rounded-xl border border-edge bg-surface px-4 py-2.5 text-sm text-slate-500">
                    {phase === "searching" ? "Searching your workspace…" : "Generating answer…"}
                  </div>
                </div>
              )}

              {error && (
                <div className="rounded-lg border border-rose/30 bg-rose/10 px-4 py-3 text-sm text-rose-700">{error}</div>
              )}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {readyCount !== 0 && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            className="border-t border-edge bg-surface px-8 py-4"
          >
            <div className="mx-auto max-w-2xl">
              <div className="mb-2 flex gap-1">
                {(["EXPLAIN", "SEARCH"] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setMode(m)}
                    className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                      mode === m ? "border-indigo bg-indigo/10 text-indigo" : "border-edge text-slate-500 hover:text-ink"
                    }`}
                  >
                    {m === "EXPLAIN" ? "Explain" : "Search"}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-2">
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={mode === "EXPLAIN" ? "Ask a question about your documents…" : "Search your documents…"}
                  maxLength={2000}
                  className="flex-1 rounded-lg border border-edge px-3 py-2.5 text-sm focus:border-indigo focus:outline-none focus:ring-1 focus:ring-indigo"
                />
                <button
                  type="submit"
                  disabled={phase !== "idle" || !input.trim()}
                  className="rounded-lg bg-indigo px-4 py-2.5 text-sm font-medium text-white hover:bg-indigo/90 disabled:opacity-50"
                >
                  {mode === "EXPLAIN" ? "Send" : "Search"}
                </button>
              </div>
            </div>
          </form>
        )}
      </div>

      {activeCitation && <SourceViewerModal citation={activeCitation} onClose={() => setActiveCitation(null)} />}
    </AppShell>
  );
}
