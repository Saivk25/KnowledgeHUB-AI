/**
 * API client.
 *
 * Decision: a thin fetch wrapper instead of a generated OpenAPI client.
 * Why: the API surface is small and frozen (see docs/api-contract.md); a
 * codegen step would add build tooling for marginal benefit.
 * `credentials: "include"` is required on calls that need auth so the
 * httpOnly auth cookie set by the API is sent on subsequent requests.
 *
 * Milestone status: only `liveness` and `readiness` are wired to a live
 * backend router in Milestone 1 (Project Foundation) -- app/main.py does
 * not mount auth/documents/chat yet. The methods below for those features
 * are kept here (rather than deleted) because the screens in
 * app/_future/ already call them and are ready to go live the moment each
 * router is approved and mounted; see app/_future/README.md.
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

// -- Future milestones: auth, workspace, documents, chat ----------------
// (types and methods below are not yet backed by a mounted router)

export interface UserOut {
  id: string;
  email: string;
  displayName: string;
}
export interface WorkspaceOut {
  id: string;
  name: string;
}
export interface AuthResponse {
  user: UserOut;
  workspace: WorkspaceOut;
  accessToken: string;
}
export interface DocumentOut {
  id: string;
  filename: string;
  status: "QUEUED" | "PROCESSING" | "READY" | "FAILED";
  pageCount: number;
  sizeBytes: number;
  errorMessage: string | null;
  createdAt: string;
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

  // Milestone 2 -- auth/workspace (not mounted yet)
  register: (email: string, password: string, displayName: string) =>
    request<AuthResponse>("/api/v1/auth/register", { method: "POST", body: JSON.stringify({ email, password, displayName }) }),
  login: (email: string, password: string) =>
    request<AuthResponse>("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => request<void>("/api/v1/auth/logout", { method: "POST" }),
  me: () => request<{ user: UserOut; workspace: WorkspaceOut | null }>("/api/v1/auth/me"),

  getWorkspace: () =>
    request<{ workspace: WorkspaceOut; stats: { readyDocuments: number; processingDocuments: number; failedDocuments: number } }>(
      "/api/v1/workspace"
    ),
  updateWorkspace: (name: string) =>
    request<{ workspace: WorkspaceOut }>("/api/v1/workspace", { method: "PATCH", body: JSON.stringify({ name }) }),
  updateProfile: (displayName: string) =>
    request<{ user: UserOut }>("/api/v1/users/me", { method: "PATCH", body: JSON.stringify({ displayName }) }),

  // Milestone 3 -- documents (not mounted yet)
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
