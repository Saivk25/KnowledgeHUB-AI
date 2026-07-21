"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import AppShell from "@/components/AppShell";
import { api, ApiError } from "@/lib/api";

const MAX_MB = 25;

// Milestone 5 (Multi-Format Ingestion): mirrors the backend's supported
// extension registry (app/services/extraction.py's SUPPORTED_EXTENSIONS).
// Kept as a flat list here rather than fetched from the API -- same
// "small, frozen surface, no codegen" reasoning as the rest of lib/api.ts.
const SUPPORTED_EXTENSIONS = [
  ".pdf", ".docx", ".pptx", ".txt", ".md",
  ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".c", ".h", ".cpp", ".hpp",
  ".go", ".rs", ".rb", ".php", ".cs", ".kt", ".sql", ".sh",
  ".png", ".jpg", ".jpeg",
];
const ACCEPT_ATTR = SUPPORTED_EXTENSIONS.join(",");

export default function UploadDocumentPage() {
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [youtubeError, setYoutubeError] = useState<string | null>(null);
  const [submittingYoutube, setSubmittingYoutube] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  const validate = (f: File): string | null => {
    const name = f.name.toLowerCase();
    if (!SUPPORTED_EXTENSIONS.some((ext) => name.endsWith(ext))) {
      return `Unsupported file type. Supported: PDF, DOCX, PPTX, TXT, Markdown, source code files, and PNG/JPG images.`;
    }
    if (f.size > MAX_MB * 1024 * 1024) {
      return `This file is larger than the ${MAX_MB}MB limit.`;
    }
    return null;
  };

  const onSelect = (f: File) => {
    const validationError = validate(f);
    if (validationError) {
      setError(validationError);
      setFile(null);
      return;
    }
    setError(null);
    setFile(f);
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) onSelect(f);
  }, []);

  const onUpload = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const doc = await api.uploadDocument(file);
      router.push(`/documents/${doc.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed. Please try again.");
      setUploading(false);
    }
  };

  const onSubmitYoutube = async () => {
    if (!youtubeUrl.trim()) return;
    setSubmittingYoutube(true);
    setYoutubeError(null);
    try {
      const doc = await api.ingestYoutubeVideo(youtubeUrl.trim());
      router.push(`/documents/${doc.id}`);
    } catch (err) {
      setYoutubeError(err instanceof ApiError ? err.message : "Could not ingest this video. Please try again.");
      setSubmittingYoutube(false);
    }
  };

  return (
    <AppShell>
      <div className="mx-auto max-w-2xl px-8 py-10">
        <h1 className="text-2xl font-semibold text-ink">Upload a document</h1>
        <p className="mt-1 text-sm text-slate-500">
          PDF, DOCX, PPTX, TXT/Markdown, source code, or PNG/JPG (up to {MAX_MB}MB). Your document is processed
          privately inside your workspace.
        </p>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          className={`mt-6 flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-12 text-center transition-colors ${
            dragOver ? "border-indigo bg-indigo/5" : "border-edge bg-surface"
          }`}
        >
          <svg className="h-10 w-10 text-slate-300" viewBox="0 0 24 24" fill="none">
            <path d="M12 16V4m0 0 4 4m-4-4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
          <p className="mt-3 text-sm text-slate-600">Drag and drop a file here, or</p>
          <button
            onClick={() => inputRef.current?.click()}
            className="mt-2 rounded-lg border border-edge bg-surface px-4 py-2 text-sm font-medium text-ink hover:bg-canvas"
          >
            Choose file
          </button>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT_ATTR}
            className="hidden"
            onChange={(e) => e.target.files?.[0] && onSelect(e.target.files[0])}
          />
        </div>

        {file && (
          <div className="mt-4 flex items-center justify-between rounded-lg border border-edge bg-surface px-4 py-3">
            <div>
              <p className="text-sm font-medium text-ink">{file.name}</p>
              <p className="text-xs text-slate-500">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
            </div>
            <button onClick={() => setFile(null)} className="text-xs font-medium text-slate-400 hover:text-rose">
              Remove
            </button>
          </div>
        )}

        {error && (
          <div className="mt-4 rounded-lg border border-rose/30 bg-rose/10 px-4 py-3 text-sm text-rose-700">{error}</div>
        )}

        <div className="mt-6 flex items-center gap-3">
          <button
            onClick={onUpload}
            disabled={!file || uploading}
            className="rounded-lg bg-indigo px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo/90 disabled:opacity-50"
          >
            {uploading ? "Uploading…" : "Upload Document"}
          </button>
          <button
            onClick={() => router.push("/documents")}
            className="rounded-lg border border-edge px-5 py-2.5 text-sm font-medium text-ink hover:bg-canvas"
          >
            Cancel
          </button>
        </div>

        <div className="mt-10 border-t border-edge pt-6">
          <h2 className="text-sm font-semibold text-ink">Or ingest a YouTube video's transcript</h2>
          <p className="mt-1 text-sm text-slate-500">Paste a youtube.com or youtu.be link. The video's own captions are used -- no audio is transcribed.</p>
          <div className="mt-3 flex items-center gap-3">
            <input
              type="url"
              value={youtubeUrl}
              onChange={(e) => setYoutubeUrl(e.target.value)}
              placeholder="https://www.youtube.com/watch?v=..."
              className="w-full rounded-lg border border-edge bg-surface px-3 py-2 text-sm text-ink placeholder:text-slate-400"
            />
            <button
              onClick={onSubmitYoutube}
              disabled={!youtubeUrl.trim() || submittingYoutube}
              className="whitespace-nowrap rounded-lg bg-indigo px-4 py-2 text-sm font-medium text-white hover:bg-indigo/90 disabled:opacity-50"
            >
              {submittingYoutube ? "Fetching…" : "Ingest video"}
            </button>
          </div>
          {youtubeError && (
            <div className="mt-3 rounded-lg border border-rose/30 bg-rose/10 px-4 py-3 text-sm text-rose-700">{youtubeError}</div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
