"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { api, ApiError, ConceptOut, DocumentOut, StudyPlanResultOut } from "@/lib/api";

// Milestone 10 (Study Workflows): Study planner -- pick 2+ targets
// (documents and/or concepts, mirroring Compare's multi-select pattern
// in concepts/page.tsx), an optional horizon, and get back a
// deterministically-scheduled, LLM-narrated day-by-day plan (see
// docs/adr/0017-study-workflows.md decision 4 -- the schedule itself is
// never LLM-decided, only the `note` phrasing is).
type TargetKind = "resource" | "concept";
interface SelectableTarget {
  kind: TargetKind;
  id: string;
  label: string;
}

const DEFAULT_HORIZON_DAYS = 7;

export default function StudyPlanPage() {
  const [documents, setDocuments] = useState<DocumentOut[]>([]);
  const [concepts, setConcepts] = useState<ConceptOut[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<SelectableTarget[]>([]);
  const [horizonDays, setHorizonDays] = useState(DEFAULT_HORIZON_DAYS);
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const [plan, setPlan] = useState<StudyPlanResultOut | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [docsRes, conceptsRes] = await Promise.all([api.listDocuments(), api.listConcepts()]);
        setDocuments(docsRes.items.filter((d) => d.status === "READY"));
        setConcepts(conceptsRes.items);
      } catch (err) {
        setLoadError(err instanceof ApiError ? err.message : "Couldn't load documents and concepts.");
      }
    })();
  }, []);

  const toggle = (target: SelectableTarget) => {
    setSelected((prev) => {
      const exists = prev.some((t) => t.kind === target.kind && t.id === target.id);
      if (exists) return prev.filter((t) => !(t.kind === target.kind && t.id === target.id));
      return [...prev, target];
    });
  };

  const isSelected = (kind: TargetKind, id: string) =>
    selected.some((t) => t.kind === kind && t.id === id);

  const onGenerate = async () => {
    if (selected.length < 2) return;
    setGenerating(true);
    setGenError(null);
    setPlan(null);
    try {
      const targets = selected.map((t) => ({
        label: t.label,
        ...(t.kind === "resource" ? { resourceId: t.id } : { conceptId: t.id }),
      }));
      const conv = await api.createConversation();
      const res = await api.sendIntent(conv.id, { intent: "STUDY_PLAN", targets, horizonDays });
      if (res.status !== "OK") {
        setGenError("Couldn't build a study plan from these targets.");
        return;
      }
      setPlan(res.result as StudyPlanResultOut);
    } catch (err) {
      setGenError(err instanceof ApiError ? err.message : "Couldn't build a study plan.");
    } finally {
      setGenerating(false);
    }
  };

  return (
    <AppShell>
      <div className="mx-auto max-w-2xl px-8 py-10">
        <h1 className="text-2xl font-semibold text-ink">Study planner</h1>
        <p className="mt-1 text-sm text-slate-500">
          Pick at least two documents or concepts to spread across a study schedule.
        </p>

        {loadError && (
          <div className="mt-4 rounded-lg border border-rose/30 bg-rose/10 px-4 py-3 text-sm text-rose-700">
            {loadError}
          </div>
        )}

        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-edge bg-surface p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Documents</p>
            <div className="mt-2 max-h-64 space-y-1 overflow-y-auto">
              {documents.length === 0 && <p className="text-sm text-slate-500">No ready documents yet.</p>}
              {documents.map((d) => (
                <label key={d.id} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-canvas">
                  <input
                    type="checkbox"
                    checked={isSelected("resource", d.id)}
                    onChange={() => toggle({ kind: "resource", id: d.id, label: d.filename })}
                  />
                  {d.filename}
                </label>
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-edge bg-surface p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Concepts</p>
            <div className="mt-2 max-h-64 space-y-1 overflow-y-auto">
              {concepts.length === 0 && <p className="text-sm text-slate-500">No concepts yet.</p>}
              {concepts.map((c) => (
                <label key={c.id} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-canvas">
                  <input
                    type="checkbox"
                    checked={isSelected("concept", c.id)}
                    onChange={() => toggle({ kind: "concept", id: c.id, label: c.name })}
                  />
                  {c.name}
                </label>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-slate-600">
            Horizon (days)
            <input
              type="number"
              min={1}
              max={60}
              value={horizonDays}
              onChange={(e) => setHorizonDays(Number(e.target.value) || DEFAULT_HORIZON_DAYS)}
              className="w-20 rounded-lg border border-edge px-2 py-1.5 text-sm"
            />
          </label>
          <button
            onClick={onGenerate}
            disabled={selected.length < 2 || generating}
            className="rounded-lg bg-indigo px-4 py-2 text-sm font-medium text-white hover:bg-indigo/90 disabled:opacity-50"
          >
            {generating ? "Building…" : `Build plan (${selected.length} selected)`}
          </button>
        </div>

        {genError && <p className="mt-3 text-sm text-rose-700">{genError}</p>}

        {plan && (
          <ol className="mt-6 space-y-3">
            {plan.days.map((day) => (
              <li key={day.day} className="rounded-xl border border-edge bg-surface p-4">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-ink">
                    Day {day.day}
                    {day.date && <span className="ml-2 text-xs text-slate-400">{day.date}</span>}
                  </p>
                </div>
                <p className="mt-1 text-sm text-slate-600">{day.targets.join(", ")}</p>
                <p className="mt-2 text-xs text-slate-500">{day.note}</p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </AppShell>
  );
}
