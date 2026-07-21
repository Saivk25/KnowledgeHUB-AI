/**
 * API client.
 *
 * Decision: a thin fetch wrapper instead of a generated OpenAPI client.
 * Why: the API surface is small and frozen (see docs/api-contract.md); a
 * codegen step would add build tooling for marginal benefit.
 * `credentials: "include"` is required on calls that need auth so the
 * httpOnly auth cookie set by the API is sent on subsequent requests.
 *
 * Milestone status: `liveness`/`readiness` (Milestone 1),
 * `register`/`login`/`logout`/`me`/`getWorkspace`/`updateWorkspace`/
 * `updateProfile` (Milestone 2), and `listDocuments`/`getDocumentDetail`/
 * `uploadDocument`/`deleteDocument`/`retryDocument`/`fileUrl` (Milestone 3)
 * are all wired to live backend routers. Everything under "Milestone 4"
 * below is kept here (rather than deleted) because the dormant chat
 * screen in app/_future/ already calls it and is ready to go live the
 * moment that router is approved and mounted; see app/_future/README.md.
 */
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      ...(init?.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers || {}),
    },
  });

  if (res.status === 204) {
    return undefined as T;
  }

  const isJson = res.headers.get("content-type")?.includes("application/json");
  const data = isJson ? await res.json() : null;

  if (!res.ok) {
    const err = data?.error;
    throw new ApiError(res.status, err?.code || "UNKNOWN_ERROR", err?.message || "Something went wrong.");
  }
  return data as T;
}

// -- Milestone 1: health -----------------------------------------------

export interface ComponentHealth {
  status: "up" | "down";
  detail: string;
}
export interface ReadinessResponse {
  status: "ready" | "degraded";
  components: {
    database: ComponentHealth;
    vector_db: ComponentHealth;
  };
}
export interface LivenessResponse {
  status: string;
  app: string;
}

// -- Milestones 2-3: auth, workspace, documents (all live) --------------
// -- Milestone 4: chat (type kept for the dormant app/_future/ screen,
//    not yet backed by a mounted router) -------------------------------

export interface UserOut {
  id: string;
  email: string;
  displayName: string;
}
export interface WorkspaceOut {
  id: string;
  name: string;
}
// Milestone note: `stats` is optional because the backend does not return
// it -- GET /workspace still only returns { workspace }. It is declared
// here -- rather than omitted -- only because the dormant Milestone 4
// chat screen (app/_future/chat/page.tsx) already reads it; making it
// optional keeps that type-check honest without reactivating or
// rewriting that screen. (It was going to be Milestone 3's job per the
// original module map, but the Document model in this milestone tracks
// per-document status, not workspace-level aggregate counts -- the
// Documents page instead calls listDocuments() and computes its own
// counts client-side. Add a real `stats` aggregate to GET /workspace
// only if a future milestone needs it server-computed.)
export interface WorkspaceStatsOut {
  readyDocuments: number;
  processingDocuments: number;
  failedDocuments: number;
}
export interface AuthResponse {
  user: UserOut;
  workspace: WorkspaceOut;
  accessToken: string;
}
export type ContentCategory =
  | "LECTURE"
  | "ASSIGNMENT"
  | "QUESTION_PAPER"
  | "LAB_MANUAL"
  | "RESEARCH_PAPER"
  | "PERSONAL_NOTE"
  | "OTHER";

export interface DocumentOut {
  id: string;
  filename: string;
  status: "QUEUED" | "PROCESSING" | "READY" | "FAILED";
  pageCount: number;
  sizeBytes: number;
  errorMessage: string | null;
  createdAt: string;
  // Milestone 6: extraction confidence (M5 field, first exposed here) +
  // classification metadata. See docs/adr/0013-classification-confidence.md.
  extractionConfidence: number | null;
  contentCategory: ContentCategory | null;
  contentCategoryConfidence: number | null;
  contentCategoryConfirmed: boolean;
  subject: string | null;
  subjectConfidence: number | null;
  subjectConfirmed: boolean;
}
export interface IngestionJobOut {
  step: string;
  status: string;
  errorCode: string | null;
}
export interface CitationOut {
  documentId: string;
  documentFilename: string;
  pageNumber: number;
  excerpt: string;
  order: number;
}
export interface AnswerOut {
  id: string;
  status: "OK" | "NO_EVIDENCE" | "ERROR";
  content: string;
  citations: CitationOut[];
}
export interface MessageOut {
  id: string;
  role: "user" | "assistant";
  content: string;
}

export const api = {
  // Milestone 1 -- live
  liveness: () => request<LivenessResponse>("/health"),
  readiness: () => request<ReadinessResponse>("/health/ready"),

  // Milestone 2 -- auth/workspace -- live
  register: (email: string, password: string, displayName: string) =>
    request<AuthResponse>("/api/v1/auth/register", { method: "POST", body: JSON.stringify({ email, password, displayName }) }),
  login: (email: string, password: string) =>
    request<AuthResponse>("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => request<void>("/api/v1/auth/logout", { method: "POST" }),
  me: () => request<{ user: UserOut; workspace: WorkspaceOut | null }>("/api/v1/auth/me"),

  // `stats` is not present on the live response -- see WorkspaceStatsOut's
  // doc comment above.
  getWorkspace: () => request<{ workspace: WorkspaceOut; stats?: WorkspaceStatsOut }>("/api/v1/workspace"),
  updateWorkspace: (name: string) =>
    request<{ workspace: WorkspaceOut }>("/api/v1/workspace", { method: "PATCH", body: JSON.stringify({ name }) }),
  updateProfile: (displayName: string) =>
    request<{ user: UserOut }>("/api/v1/users/me", { method: "PATCH", body: JSON.stringify({ displayName }) }),

  // Milestone 3 -- documents -- live
  listDocuments: () => request<{ items: DocumentOut[] }>("/api/v1/documents"),
  getDocumentDetail: (id: string) => request<{ document: DocumentOut; processingJob: IngestionJobOut | null }>(`/api/v1/documents/${id}`),
  uploadDocument: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentOut>("/api/v1/documents", { method: "POST", body: form });
  },
  deleteDocument: (id: string) => request<void>(`/api/v1/documents/${id}`, { method: "DELETE" }),
  retryDocument: (id: string) => request<DocumentOut>(`/api/v1/documents/${id}/retry`, { method: "POST" }),
  fileUrl: (id: string) => `${API_URL}/api/v1/documents/${id}/file`,

  // Milestone 5 -- multi-format ingestion -- live
  ingestYoutubeVideo: (url: string) =>
    request<DocumentOut>("/api/v1/documents/youtube", { method: "POST", body: JSON.stringify({ url }) }),

  // Milestone 6 -- classification correction -- live
  updateClassification: (id: string, body: { contentCategory?: string; subject?: string }) =>
    request<DocumentOut>(`/api/v1/documents/${id}/classification`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  // Milestone 4 -- chat (not mounted yet)
  createConversation: () => request<{ id: string; title: string }>("/api/v1/conversations", { method: "POST", body: JSON.stringify({}) }),
  getConversation: (id: string) =>
    request<{ conversation: { id: string; title: string }; messages: MessageOut[] }>(`/api/v1/conversations/${id}`),
  sendMessage: (id: string, content: string) =>
    request<{ userMessage: MessageOut; answer: AnswerOut }>(`/api/v1/conversations/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
};
