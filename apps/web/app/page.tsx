import Link from "next/link";
import SystemStatusPanel from "@/components/SystemStatusPanel";

// Milestone 2 (Authentication): the landing page now offers Login/Register
// CTAs since /login and /register are live routes with a real backend
// behind them (previously they would have 404'd, so no CTA existed).
export default function LandingPage() {
  return (
    <div className="min-h-screen bg-canvas">
      <header className="flex items-center justify-between px-6 py-4 md:px-10">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-indigo text-white text-sm font-bold">K</span>
          <span className="font-semibold tracking-tight text-ink">KnowledgeHub AI</span>
        </div>
        <div className="flex items-center gap-4">
          <a href="https://github.com" target="_blank" rel="noreferrer" className="text-sm text-slate-500 hover:text-ink">
            View on GitHub
          </a>
          <Link href="/login" className="text-sm font-medium text-ink hover:text-indigo">
            Log in
          </Link>
          <Link
            href="/register"
            className="rounded-lg bg-indigo px-3.5 py-1.5 text-sm font-medium text-white hover:bg-indigo/90"
          >
            Sign up
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 pt-16 pb-24 text-center md:px-10">
        <h1 className="text-4xl md:text-5xl font-semibold tracking-tight text-ink">
          Your Organization&apos;s Intelligence, <span className="text-indigo">Instantly Searchable.</span>
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-lg text-slate-600">
          This is Milestone 2: authentication and workspaces. Create an account to get your own private
          workspace. Document ingestion and AI chat arrive in the milestones that follow, per the frozen SRS.
        </p>

        <div className="mt-8 flex items-center justify-center gap-3">
          <Link
            href="/register"
            className="rounded-lg bg-indigo px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo/90"
          >
            Create your workspace
          </Link>
          <Link
            href="/login"
            className="rounded-lg border border-edge bg-surface px-5 py-2.5 text-sm font-medium text-ink hover:bg-canvas"
          >
            Log in
          </Link>
        </div>

        <div className="mt-10">
          <SystemStatusPanel />
        </div>

        <div className="mt-10 rounded-xl border border-edge bg-surface p-5 text-left">
          <h3 className="font-semibold text-ink">What&apos;s next</h3>
          <p className="mt-1.5 text-sm text-slate-600">
            Milestone 3 introduces document upload and the ingestion pipeline. Milestone 4 introduces RAG chat
            with page-level citations. Each ships only after the previous one is reviewed and approved.
          </p>
        </div>
      </main>

      <footer className="border-t border-edge px-6 py-6 text-center text-xs text-slate-400 md:px-10">
        KnowledgeHub AI -- Milestone 2: Authentication &amp; Workspace
      </footer>
    </div>
  );
}
