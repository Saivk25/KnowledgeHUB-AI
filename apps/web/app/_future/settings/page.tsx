"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

export default function SettingsPage() {
  const { user, workspace, refresh, logout } = useAuth();
  const [displayName, setDisplayName] = useState("");
  const [workspaceName, setWorkspaceName] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user) setDisplayName(user.displayName);
    if (workspace) setWorkspaceName(workspace.name);
  }, [user, workspace]);

  const onSave = async () => {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await api.updateProfile(displayName);
      await api.updateWorkspace(workspaceName);
      await refresh();
      setMessage("Changes saved.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save your changes.");
    } finally {
      setSaving(false);
    }
  };

  if (!user) {
    return (
      <AppShell>
        <div className="mx-auto max-w-lg px-8 py-10 space-y-3">
          <div className="h-6 w-1/3 animate-pulse rounded bg-slate-100" />
          <div className="h-40 animate-pulse rounded-xl bg-slate-100" />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-lg px-8 py-10">
        <h1 className="text-2xl font-semibold text-ink">Settings</h1>

        <div className="mt-6 rounded-xl border border-edge bg-surface p-6">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Profile</h2>
          <div className="mt-3 space-y-3">
            <div>
              <label className="block text-sm font-medium text-ink">Email</label>
              <input disabled value={user.email} className="mt-1 w-full rounded-lg border border-edge bg-canvas px-3 py-2 text-sm text-slate-500" />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink">Display name</label>
              <input
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                className="mt-1 w-full rounded-lg border border-edge px-3 py-2 text-sm focus:border-indigo focus:outline-none focus:ring-1 focus:ring-indigo"
              />
            </div>
          </div>

          <h2 className="mt-6 text-sm font-semibold uppercase tracking-wide text-slate-400">Workspace</h2>
          <div className="mt-3">
            <label className="block text-sm font-medium text-ink">Workspace name</label>
            <input
              value={workspaceName}
              onChange={(e) => setWorkspaceName(e.target.value)}
              className="mt-1 w-full rounded-lg border border-edge px-3 py-2 text-sm focus:border-indigo focus:outline-none focus:ring-1 focus:ring-indigo"
            />
          </div>

          {message && <p className="mt-4 text-sm text-emerald-700">{message}</p>}
          {error && <p className="mt-4 text-sm text-rose-700">{error}</p>}

          <button
            onClick={onSave}
            disabled={saving}
            className="mt-5 rounded-lg bg-indigo px-4 py-2 text-sm font-medium text-white hover:bg-indigo/90 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save Changes"}
          </button>
        </div>

        <div className="mt-6 rounded-xl border border-edge bg-surface p-6">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Session</h2>
          <button onClick={logout} className="mt-3 rounded-lg border border-edge px-4 py-2 text-sm font-medium text-ink hover:bg-canvas">
            Log Out
          </button>
        </div>

        <p className="mt-6 text-center text-xs text-slate-400">
          KnowledgeHub AI · v0.1.0 ·{" "}
          <a href="https://github.com" className="underline">
            GitHub
          </a>
        </p>
      </div>
    </AppShell>
  );
}
