// Milestone 6: mirrors StatusBadge.tsx's exact pattern (static style/label
// lookup tables, unstyled fallback for anything unrecognized).
const STYLES: Record<string, string> = {
  LECTURE: "bg-indigo/10 text-indigo-700 border-indigo/30",
  ASSIGNMENT: "bg-amber/10 text-amber-700 border-amber/30",
  QUESTION_PAPER: "bg-rose/10 text-rose-700 border-rose/30",
  LAB_MANUAL: "bg-emerald/10 text-emerald-700 border-emerald/30",
  RESEARCH_PAPER: "bg-violet-100 text-violet-700 border-violet-300",
  PERSONAL_NOTE: "bg-slate-100 text-slate-600 border-slate-300",
  OTHER: "bg-slate-100 text-slate-500 border-slate-200",
};

const LABELS: Record<string, string> = {
  LECTURE: "Lecture",
  ASSIGNMENT: "Assignment",
  QUESTION_PAPER: "Question Paper",
  LAB_MANUAL: "Lab Manual",
  RESEARCH_PAPER: "Research Paper",
  PERSONAL_NOTE: "Personal Note",
  OTHER: "Other",
};

export default function CategoryBadge({ category }: { category: string | null }) {
  if (!category) return null;
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${
        STYLES[category] || "bg-slate-100 text-slate-600 border-slate-200"
      }`}
    >
      {LABELS[category] || category}
    </span>
  );
}
