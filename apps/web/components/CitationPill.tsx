import { CitationOut } from "@/lib/api";

export default function CitationPill({ citation, onOpen }: { citation: CitationOut; onOpen: (c: CitationOut) => void }) {
  return (
    <button
      onClick={() => onOpen(citation)}
      className="inline-flex items-center gap-1 rounded-full border border-sky/30 bg-sky/10 px-2 py-0.5 text-xs font-medium text-sky-700 hover:bg-sky/20 transition-colors"
      title={`${citation.documentFilename} · page ${citation.pageNumber}`}
    >
      [{citation.order}] {citation.documentFilename} · p.{citation.pageNumber}
    </button>
  );
}
