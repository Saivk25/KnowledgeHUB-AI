"use client";

import AppShell from "@/components/AppShell";
import { useAuth } from "@/lib/auth-context";

// Milestone 2 (Authentication): a minimal workspace shell that proves
// login -> protected route -> your own workspace end to end. It
// deliberately does not call api.listDocuments() or render document
// stats -- that endpoint isn't mounted until Milestone 3, and calling it
// here would 404. See apps/web/app/_future/README.md.
export default function WorkspaceHomePage() {
  const { user, workspace } = useAuth();

  return (
    <AppShell>
      <div className="mx-auto max-w-3xl px-8 py-10">
        <h1 className="text-2xl font-semibold text-ink">Welcome back{user ? `, ${user.displayName}` : ""}</h1>
        <p className="mt-1 text-slate-500">{workspace?.name}</p>

        <div className="mt-6 rounded-xl border border-edge bg-surface p-6">
          <h2 className="font-semibold text-ink">Your workspace is ready</h2>
          <p className="mt-1.5 text-sm text-slate-600">
            You are signed in and this is your private workspace -- isolated from every other account. Document
            upload, search, and AI chat are introduced in the milestones that follow.
          </p>
        </div>

        <div className="mt-6 rounded-xl border border-dashed border-edge bg-canvas p-6 text-center">
          <p className="text-sm text-slate-500">Document upload arrives in Milestone 3.</p>
        </div>
      </div>
    </AppShell>
  );
}
