const STYLES: Record<string, string> = {
  QUEUED: "bg-amber/10 text-amber-700 border-amber/30",
  PROCESSING: "bg-amber/10 text-amber-700 border-amber/30",
  READY: "bg-emerald/10 text-emerald-700 border-emerald/30",
  FAILED: "bg-rose/10 text-rose-700 border-rose/30",
};

const LABELS: Record<string, string> = {
  QUEUED: "Queued",
  PROCESSING: "Processing",
  READY: "Ready",
  FAILED: "Failed",
};

export default function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${STYLES[status] || "bg-slate-100 text-slate-600 border-slate-200"}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {LABELS[status] || status}
    </span>
  );
}
