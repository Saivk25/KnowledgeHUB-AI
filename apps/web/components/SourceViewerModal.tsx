"use client";

import { useState } from "react";
import { api, CitationOut } from "@/lib/api";

export default function SourceViewerModal({ citation, onClose }: { citation: CitationOut; onClose: () => void }) {
  const [loaded, setLoaded] = useState(false);
  const fileUrl = `${api.fileUrl(citation.documentId)}#page=${citation.pageNumber}`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-6" onClick={onClose}>
      <div
        className="flex w-full max-w-4xl h-[85vh] overflow-hidden rounded-xl bg-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex flex-1 flex-col">
          <div className="flex items-center justify-between border-b border-edge px-4 py-3">
            <div>
              <p className="text-sm font-semibold text-ink">{citation.documentFilename}</p>
              <p className="text-xs text-slate-500">Page {citation.pageNumber} · used in this answer</p>
            </div>
            <div className="flex items-center gap-2">
              <a
                href={api.fileUrl(citation.documentId)}
                target="_blank"
                rel="noreferrer"
                className="rounded-md border border-edge px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-canvas"
              >
                Open full PDF
              </a>
              <button onClick={onClose} className="rounded-md border border-edge px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-canvas">
                Close
              </button>
            </div>
          </div>

          <div className="relative flex-1 bg-slate-100">
            {!loaded && (
              <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-400">Loading source document…</div>
            )}
            <iframe src={fileUrl} className="h-full w-full" onLoad={() => setLoaded(true)} title="Source PDF" />
          </div>
        </div>

        <div className="w-72 shrink-0 border-l border-edge p-4 overflow-y-auto">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Evidence excerpt</p>
          <p className="mt-2 text-sm leading-relaxed text-slate-700">{citation.excerpt}</p>
        </div>
      </div>
    </div>
  );
}
