import type { Metadata } from "next";
import "./globals.css";

// Milestone 1 (Project Foundation): no AuthProvider yet -- there is no
// backend auth router to check a session against. It is restored here in
// Milestone 2 once /api/v1/auth exists (see app/_future/README.md).

export const metadata: Metadata = {
  title: "KnowledgeHub AI",
  description: "Your Organization's Intelligence, Instantly Searchable.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
