"use client";

import Sidebar from "./Sidebar";
import { useRequireAuth } from "@/lib/useRequireAuth";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading } = useRequireAuth();

  if (loading) {
    return <div className="flex h-screen items-center justify-center text-slate-400 text-sm">Loading your workspace…</div>;
  }
  if (!user) {
    return null; // redirect already in flight
  }

  return (
    <div className="flex min-h-screen bg-canvas">
      <Sidebar />
      <main className="flex-1 min-w-0">{children}</main>
    </div>
  );
}
