"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import { api, ApiError, CompareResultOut, ConceptOut } from "@/lib/api";

// Milestone 7 (Concept Graph): the "browse by concept" page the roadmap's
// M7 line item asks for. Deliberately minimal -- a list with an evidence
// count, linking to the concept detail page. No filtering/search, no
// graph visualization: those are out of this milestone's approved scope.
export default function ConceptsPage() {
  const [concepts, setConcepts] = useState<ConceptOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  // Milestone 9 (Intent Workflows): Compare -- select 2-4 concepts, then
  // ask for a citation-grounded comparison across them. Per the approved
  // design, gaps in one side's evidence are labeled, never silently
  // filled (docs/milestones/MILESTONE_9.md Section 4 decisions 1-2).
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [comparing, setComparing] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [compareResult, setCompareResult] = useState<CompareResultOut | null>(null);
  const MAX_COMPARE_TARGETS = 4;

  const toggleSelected = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else if (next.size < MAX_COMPARE_TARGETS) {
        next.add(id);
      }
      return next;
    });
  };

  const onCompare = async () => {
    if (!concepts || selectedIds.size < 2) return;
    setComparing(true);
    setCompareError(null);
    setCompareResult(null);
    try {
      const targets = concepts
        .filter((c) => selectedIds.has(c.id))
        .map((c) => ({ label: c.name, conceptId: c.id }));
      const conv = await api.createConversation();
      const res = await api.sendIntent(conv.id, { intent: "COMPARE", targets });
      setCompareResult(res.result as CompareResultOut);
    } catch (err) {
      setCompareError(err instanceof ApiError ? err.message : "Couldn't compare these concepts.");
    } finally {
      setComparing(false);
    }
  };

  const load = async () => {
    setError(null);
    try {
      const res = await api.listConcepts();
      setConcepts(res.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't load concepts.");
    }
  };

  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(() => {
    if (!concepts) return null;
    if (!query.trim()) return concepts;
    return concepts.filter((c) => c.name.toLowerCase().includes(query.toLowerCase()));
  }, [concepts, query]);

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl px-8 py-10">
        <div>
          <h1 className="text-2xl font-semibold text-ink">Concepts</h1>
          <p className="mt-1 text-sm text-slate-500">
            {concepts ? `${concepts.length} concept${concepts.length === 1 ? "" : "s"}` : "Loading…"}
          </p>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by name…"
            className="w-full max-w-sm rounded-lg border border-edge px-3 py-2 text-sm focus:border-indigo focus:outline-none focus:ring-1 focus:ring-indigo"
          />
          {selectedIds.size > 0 && (
            <button
              onClick={onCompare}
              disabled={selectedIds.size < 2 || comparing}
              className="rounded-lg bg-indigo px-3 py-2 text-sm font-medium text-white hover:bg-indigo/90 disabled:opacity-50"
            >
              {comparing ? "Comparing…" : `Compare selected (${selectedIds.size})`}
            </button>
          )}
        </div>

        {compareError && (
          <div className="mt-4 rounded-lg border border-rose/30 bg-rose/10 px-4 py-3 text-sm text-rose-700">{compareError}</div>
        )}

        {compareResult && (
          <div className="mt-4 rounded-xl border border-edge bg-surface p-6">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Comparison</p>
            <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">{compareResult.content}</p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {compareResult.targets.map((t) => (
                <div key={t.label} className="rounded-lg border border-edge px-3 py-2">
                  <p className="text-sm font-medium text-ink">{t.label}</p>
                  <p className="text-xs text-slate-400">
                    {t.hasEvidence ? `${t.citations.length} citation${t.citations.length === 1 ? "" : "s"}` : "No local evidence found"}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

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
              <p className="text-sm text-slate-500">
                {concepts && concepts.length > 0
                  ? "No concepts match your search."
                  : "No concepts yet -- upload a document to start building your knowledge graph."}
              </p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b border-edge bg-canvas text-left text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="w-10 px-4 py-3"></th>
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3">Evidence</th>
                  <th className="px-4 py-3">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-edge">
                {filtered.map((concept) => (
                  <tr key={concept.id} className="hover:bg-canvas">
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(concept.id)}
                        onChange={() => toggleSelected(concept.id)}
                        disabled={!selectedIds.has(concept.id) && selectedIds.size >= MAX_COMPARE_TARGETS}
                        aria-label={`Select ${concept.name} to compare`}
                      />
                    </td>
                    <td className="px-4 py-3">
                      <Link href={`/concepts/${concept.id}`} className="font-medium text-ink hover:text-indigo">
                        {concept.name}
                      </Link>
                      {concept.possibleDuplicateOfConceptId && (
                        <span className="ml-2 rounded-full border border-amber/30 bg-amber/10 px-2 py-0.5 text-xs font-medium text-amber-700">
                          possible duplicate
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-slate-500">{concept.evidenceCount}</td>
                    <td className="px-4 py-3 text-slate-500">{new Date(concept.createdAt).toLocaleDateString()}</td>
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
