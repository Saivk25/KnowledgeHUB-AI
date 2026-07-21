import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";

// Milestone 2 (Authentication): AuthProvider wraps every page so that
// useAuth()/useRequireAuth() (used by AppShell and the protected pages --
// workspace, settings) have a session to read. Milestone 1 had no
// AuthProvider because there was no backend auth router to check a
// session against.

export const metadata: Metadata = {
  title: "KnowledgeHub AI",
  description: "Your Organization's Intelligence, Instantly Searchable.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
