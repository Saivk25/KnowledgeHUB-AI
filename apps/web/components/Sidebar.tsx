"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

// Milestone 3 (Document Ingestion) scope: Documents and Upload Document
// are live routes. Milestone 7 (Concept Graph) adds Concepts. Milestone 8
// (Local-First Retrieval & Provenance) adds AI Chat -- previously
// prototyped under app/_future/, now a live route backed by the mounted
// /api/v1/conversations router.
const NAV_ITEMS = [
  { href: "/workspace", label: "Workspace Home", icon: "home" },
  { href: "/chat", label: "AI Chat", icon: "chat" },
  { href: "/documents", label: "Documents", icon: "docs" },
  { href: "/documents/upload", label: "Upload Document", icon: "upload" },
  { href: "/concepts", label: "Concepts", icon: "concept" },
  { href: "/settings", label: "Settings", icon: "settings" },
];

function Icon({ name }: { name: string }) {
  const common = "w-4.5 h-4.5";
  switch (name) {
    case "home":
      return <svg className={common} viewBox="0 0 20 20" fill="none"><path d="M3 9.5 10 4l7 5.5V16a1 1 0 0 1-1 1h-4v-5H8v5H4a1 1 0 0 1-1-1V9.5Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round"/></svg>;
    case "chat":
      return <svg className={common} viewBox="0 0 20 20" fill="none"><path d="M3 4h14v9H8l-4 3v-3H3V4Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round"/></svg>;
    case "docs":
      return <svg className={common} viewBox="0 0 20 20" fill="none"><path d="M6 2h6l3 3v12a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round"/><path d="M12 2v3h3" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round"/></svg>;
    case "upload":
      return <svg className={common} viewBox="0 0 20 20" fill="none"><path d="M10 13V4m0 0 3.5 3.5M10 4 6.5 7.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/><path d="M4 13v2a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>;
    case "concept":
      return <svg className={common} viewBox="0 0 20 20" fill="none"><circle cx="6" cy="6" r="2.2" stroke="currentColor" strokeWidth="1.4"/><circle cx="15" cy="6" r="2.2" stroke="currentColor" strokeWidth="1.4"/><circle cx="10.5" cy="15" r="2.2" stroke="currentColor" strokeWidth="1.4"/><path d="M7.7 7.3 9 13m4.3-5.7L11 13" stroke="currentColor" strokeWidth="1.4"/></svg>;
    default:
      return <svg className={common} viewBox="0 0 20 20" fill="none"><circle cx="10" cy="10" r="2.5" stroke="currentColor" strokeWidth="1.4"/><path d="M10 3v2m0 10v2m7-7h-2M5 10H3m11.5-5.5-1.4 1.4M6.9 13.1l-1.4 1.4m9-1.4 1.4 1.4M6.9 6.9 5.5 5.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>;
  }
}

export default function Sidebar() {
  const pathname = usePathname();
  const { workspace, logout } = useAuth();

  return (
    <aside className="w-60 shrink-0 bg-ink text-slate-200 flex flex-col h-screen sticky top-0">
      <div className="px-5 py-5 border-b border-white/10">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-indigo text-white text-sm font-bold">K</span>
          <span className="text-white font-semibold tracking-tight">KnowledgeHub AI</span>
        </div>
        <p className="mt-1 text-xs text-slate-400 truncate">{workspace?.name || "Workspace"}</p>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href || (item.href !== "/workspace" && pathname.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                active ? "bg-indigo text-white" : "text-slate-300 hover:bg-white/5 hover:text-white"
              }`}
            >
              <Icon name={item.icon} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="px-3 py-4 border-t border-white/10">
        <button
          onClick={logout}
          className="w-full rounded-lg px-3 py-2 text-left text-sm text-slate-300 hover:bg-white/5 hover:text-white transition-colors"
        >
          Log out
        </button>
      </div>
    </aside>
  );
}
