"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import CitationPill from "@/components/CitationPill";
import SourceViewerModal from "@/components/SourceViewerModal";
import { api, ApiError, CitationOut } from "@/lib/api";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  status?: "OK" | "NO_EVIDENCE" | "ERROR";
  citations?: CitationOut[];
}

const SUGGESTIONS = [
  "Summarize the key points of this document.",
  "What are the main risks or obligations mentioned?",
  "What is the approval process described here?",
];

export default function ChatPage() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [readyCount, setReadyCount] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [phase, setPhase] = useState<"idle" | "searching" | "generating">("idle");
  const [error, setError] = useState<string | null>(null);
  const [activeCitation, setActiveCitation] = useState<CitationOut | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    (async () => {
      try {
        const ws = await api.getWorkspace();
        setReadyCount(ws.stats.readyDocuments);
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

  const send = async (content: string) => {
    if (!conversationId || !content.trim()) return;
    setError(null);
    setInput("");
    setMessages((prev) => [...prev, { id: `local-${Date.now()}`, role: "user", content }]);
    setPhase("searching");
    setTimeout(() => setPhase((p) => (p === "searching" ? "generating" : p)), 500);

    try {
      const res = await api.sendMessage(conversationId, content);
      setMessages((prev) => [
        ...prev,
        {
          id: res.answer.id,
          role: "assistant",
          content: res.answer.content,
          status: res.answer.status,
          citations: res.answer.citations,
        },
      ]);
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
                    <p className="whitespace-pre-wrap">{m.content}</p>
                    {m.citations && m.citations.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1.5 border-t border-edge pt-3">
                        {m.citations.map((c) => (
                          <CitationPill key={c.order} citation={c} onOpen={setActiveCitation} />
                        ))}
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
            <div className="mx-auto flex max-w-2xl items-center gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask a question about your documents…"
                maxLength={2000}
                className="flex-1 rounded-lg border border-edge px-3 py-2.5 text-sm focus:border-indigo focus:outline-none focus:ring-1 focus:ring-indigo"
              />
              <button
                type="submit"
                disabled={phase !== "idle" || !input.trim()}
                className="rounded-lg bg-indigo px-4 py-2.5 text-sm font-medium text-white hover:bg-indigo/90 disabled:opacity-50"
              >
                Send
              </button>
            </div>
          </form>
        )}
      </div>

      {activeCitation && <SourceViewerModal citation={activeCitation} onClose={() => setActiveCitation(null)} />}
    </AppShell>
  );
}
