"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { useRouter } from "next/navigation";
import { api, UserOut, WorkspaceOut } from "./api";

interface AuthState {
  user: UserOut | null;
  workspace: WorkspaceOut | null;
  loading: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [workspace, setWorkspace] = useState<WorkspaceOut | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  const refresh = async () => {
    try {
      const res = await api.me();
      setUser(res.user);
      setWorkspace(res.workspace);
    } catch {
      setUser(null);
      setWorkspace(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const logout = async () => {
    await api.logout();
    setUser(null);
    setWorkspace(null);
    router.push("/");
  };

  return <AuthContext.Provider value={{ user, workspace, loading, refresh, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
