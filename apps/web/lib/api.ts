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
 * `updateProfile` (Milestone 2), `listDocuments`/`getDocumentDetail`/
 * `uploadDocument`/`deleteDocument`/`retryDocument`/`fileUrl` (Milestone 3),
 * `listConcepts`/`getConceptDetail`/`getRelatedConcepts`/`mergeConcept`
 * (Milestone 7), `createConversation`/`getConversation`/`sendMessage`
 * (Milestone 8), `sendIntent` -- now dispatching all nine FR-8
 * intents, Milestones 9-10 -- and `getCorrections`/`reextractDocument`
 * (Milestone 11, Confidence & Correction UX) are all wired to live
 * backend routers.
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
// Milestone 12 (Section 13 addendum) update: `stats` is now populated by
// the real GET /workspace response -- see
// apps/api/app/api/v1/routes/workspace.py's `_workspace_stats()`.
//
// History, for context: this interface was originally declared back when
// Milestone 4's chat screen still lived, dormant, at
// app/_future/chat/page.tsx -- `stats` was typed here only to keep that
// screen's `ws.stats?.readyDocuments` read type-checking cleanly, since
// GET /workspace didn't return it yet (Milestone 3 shipped a
// client-computed, listDocuments()-based count on the Documents page
// instead). Milestone 8 then promoted that screen to the live
// app/chat/page.tsx route *without* also wiring up this backend field --
// a real, unnoticed regression that left the live chat page's compose UI
// permanently hidden behind a false "0 ready documents" blocker until
// Milestone 12 caught and fixed it. The field stays optional (`?` on the
// consuming call below) defensively, not because it's unimplemented.
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
  // Milestone 11 (Confidence & Correction UX): the most recent automatic
  // classification run, regardless of whether content_category/subject
  // have since been confirmed -- previously computed on every
  // (re)classification but never returned by the API at all.
  autoContentCategory: ContentCategory | null;
  autoContentCategoryConfidence: number | null;
  autoSubject: string | null;
  autoSubjectConfidence: number | null;
}
export interface IngestionJobOut {
  step: string;
  status: string;
  errorCode: string | null;
}

// -- Milestone 7: concept graph -----------------------------------------

export type ContributionType = "DEFINES" | "APPLIES" | "TESTS" | "EXTENDS" | "MENTIONS";
export type RelationshipType =
  | "RELATED_TO"
  | "PREREQUISITE_OF"
  | "DEPENDS_ON"
  | "EXTENDS"
  | "APPLIES"
  | "CONTRADICTS"
  | "REVISES";

export interface ConceptLinkOut {
  conceptId: string;
  name: string;
  contributionType: ContributionType;
  confidence: number;
}

export interface ConceptOut {
  id: string;
  name: string;
  description: string | null;
  status: "ACTIVE" | "MERGED" | "UNUSED";
  evidenceCount: number;
  possibleDuplicateOfConceptId: string | null;
  createdAt: string;
}

export interface EvidenceOut {
  resourceId: string;
  filename: string;
  contributionType: ContributionType;
  confidence: number;
  evidenceChunkId: string;
  excerpt: string;
}

export interface RelatedConceptOut {
  conceptId: string;
  name: string;
  relationshipType: RelationshipType;
  depth: number;
}

export interface ConceptDetailOut {
  concept: ConceptOut;
  evidence: EvidenceOut[];
  related: RelatedConceptOut[];
}
// -- Milestone 8: local-first retrieval & provenance --------------------

export type Provenance = "LOCAL" | "HYBRID" | "EXTERNAL";

export interface CitationOut {
  documentId: string;
  documentFilename: string;
  chunkId: string;
  pageNumber: number;
  excerpt: string;
  order: number;
  // Milestone 9: which Compare target this citation supports. Undefined
  // for Explain/Search/resource- or concept-targeted Summarize.
  targetLabel?: string | null;
}
export interface AnswerOut {
  id: string;
  status: "OK" | "INSUFFICIENT" | "ERROR";
  provenance: Provenance | null;
  sufficiencyScore: number;
  retrievalConfidence: number;
  canOfferExternalFallback: boolean;
  content: string;
  citations: CitationOut[];
  // Milestone 11: one of the five fixed sufficiency reason codes from
  // services/sufficiency.py. Already computed/persisted since Milestone
  // 8 -- this just exposes it. See SUFFICIENCY_REASON_LABELS below.
  sufficiencyReason?: string | null;
}
export interface MessageOut {
  id: string;
  role: "user" | "assistant";
  content: string;
}

// -- Milestone 9: intent workflows (Explain, Compare, Summarize, Search) -

export type IntentType =
  | "EXPLAIN"
  | "SEARCH"
  | "SUMMARIZE"
  | "COMPARE"
  | "QUIZ"
  | "FLASHCARDS"
  | "VIVA"
  | "REVISION"
  | "STUDY_PLAN";

export interface CompareTarget {
  label: string;
  resourceId?: string;
  conceptId?: string;
  question?: string;
}

export interface IntentRequest {
  intent: IntentType;
  question?: string;
  resourceId?: string;
  conceptId?: string;
  targets?: CompareTarget[];
  useExternalFallback?: boolean;
  // -- Milestone 10 (Study Workflows) --
  questionCount?: number; // QUIZ: how many questions to generate (generation turn only)
  quizId?: string; // QUIZ: grading turn, references the generation turn's quizId
  quizAnswers?: QuizAnswerIn[]; // QUIZ: grading turn, the user's selections
  sessionId?: string; // VIVA: continuing an existing session
  vivaAnswer?: string; // VIVA: answer to the current question
  targetDate?: string; // STUDY_PLAN: optional deadline (ISO date)
  horizonDays?: number; // STUDY_PLAN: fallback window if no targetDate is given
}

export interface ExplainResultOut {
  kind: "explain";
  content: string;
}
export interface SearchResultOut {
  kind: "search";
  hits: CitationOut[];
  assistedSynthesis: string | null;
}
export interface SummarizeResultOut {
  kind: "summarize";
  content: string;
  target: string;
}
export interface CompareTargetResultOut {
  label: string;
  hasEvidence: boolean;
  citations: CitationOut[];
}
export interface CompareResultOut {
  kind: "compare";
  content: string;
  targets: CompareTargetResultOut[];
}
// -- Milestone 10: study workflows (Quiz me, Flashcards, Viva mode,
// Revision mode, Study planner) -- extends Milestone 9's envelope
// additively only; every field above is unchanged in meaning. -----------

export interface QuizAnswerIn {
  questionNumber: number;
  selectedChoice: number;
}

export interface QuizQuestionOut {
  questionNumber: number;
  prompt: string;
  choices: string[];
}
export interface QuizGradedQuestionOut {
  questionNumber: number;
  prompt: string;
  choices: string[];
  selectedChoice: number;
  correctChoice: number;
  isCorrect: boolean;
  citation: CitationOut;
}
export interface QuizResultOut {
  kind: "quiz";
  quizId: string;
  target: string;
  status: "AWAITING_ANSWERS" | "GRADED";
  questions?: QuizQuestionOut[];
  gradedQuestions?: QuizGradedQuestionOut[];
  score?: number;
}

export interface FlashcardOut {
  front: string;
  back: string;
  citation: CitationOut;
}
export interface FlashcardsResultOut {
  kind: "flashcards";
  target: string;
  cards: FlashcardOut[];
}

export interface VivaEvaluationOut {
  verdict: "correct" | "partial" | "incorrect";
  feedback: string;
}
export interface VivaResultOut {
  kind: "viva";
  sessionId: string;
  target: string;
  isComplete: boolean;
  turnNumber: number;
  previousEvaluation: VivaEvaluationOut | null;
  nextQuestion: string | null;
}

export interface RevisionItemOut {
  label: string;
  resourceId: string | null;
  conceptId: string | null;
  reason: string;
  priority: number;
}
export interface RevisionResultOut {
  kind: "revision";
  items: RevisionItemOut[];
}

export interface StudyPlanDayOut {
  day: number;
  date: string | null;
  targets: string[];
  note: string;
}
export interface StudyPlanResultOut {
  kind: "study_plan";
  days: StudyPlanDayOut[];
}

export type IntentResultOut =
  | ExplainResultOut
  | SearchResultOut
  | SummarizeResultOut
  | CompareResultOut
  | QuizResultOut
  | FlashcardsResultOut
  | VivaResultOut
  | RevisionResultOut
  | StudyPlanResultOut;

export interface IntentResponse {
  intent: IntentType;
  status: "OK" | "INSUFFICIENT" | "ERROR";
  provenance: Provenance | null;
  sufficiencyScore: number;
  retrievalConfidence: number;
  canOfferExternalFallback: boolean;
  citations: CitationOut[];
  result: IntentResultOut;
  // Milestone 11: mirrors AnswerOut's own addition above. Always
  // undefined today -- no intent handler was modified to populate it
  // (matching every existing handler's unchanged IntentResponse
  // construction, a Pydantic optional-field default on the backend).
  // Declared here as forward-compatible plumbing for when a handler
  // starts resolving a real sufficiency verdict, not as something wired
  // end to end yet.
  sufficiencyReason?: string | null;
}

// -- Milestone 11: Confidence & Correction UX ----------------------------

// Mirrors app/core/config.py's LOW_CONFIDENCE_THRESHOLD -- there is no
// config-exposing endpoint, so this threshold is duplicated here, same
// as every other client-side constant in this file that has no live
// backend counterpart to read it from.
export const LOW_CONFIDENCE_THRESHOLD = 0.5;

// The five fixed reason codes services/sufficiency.py's compute_sufficiency()
// can return (see AnswerOut.sufficiencyReason / IntentResponse.sufficiencyReason
// above), mapped to a plain-language sentence for the chat "Why?" affordance.
export const SUFFICIENCY_REASON_LABELS: Record<string, string> = {
  no_candidates: "No matching content was found in your documents.",
  strong_single_hit: "A single strongly matching passage was found.",
  insufficient_supporting_hits: "A match was found, but not enough supporting evidence to be confident.",
  below_min_score: "The best match found was too weak to be considered reliable evidence.",
  top_score: "The best available match was used to answer this question.",
};

export interface CorrectionOut {
  id: string;
  field: "CONTENT_CATEGORY" | "SUBJECT";
  previousValue: string | null;
  previousConfidence: number | null;
  newValue: string;
  correctedAt: string;
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

  // `stats` is now populated by GET /workspace (Milestone 12 Section 13 --
  // see WorkspaceStatsOut's doc comment above and
  // apps/api/app/api/v1/routes/workspace.py's module docstring for why it
  // wasn't before). Left optional (`?`) defensively, not because it's
  // unimplemented -- an older cached response or a future auth failure
  // path could still omit it.
  getWorkspace: () => request<{ workspace: WorkspaceOut; stats?: WorkspaceStatsOut }>("/api/v1/workspace"),
  updateWorkspace: (name: string) =>
    request<{ workspace: WorkspaceOut }>("/api/v1/workspace", { method: "PATCH", body: JSON.stringify({ name }) }),
  updateProfile: (displayName: string) =>
    request<{ user: UserOut }>("/api/v1/users/me", { method: "PATCH", body: JSON.stringify({ displayName }) }),

  // Milestone 3 -- documents -- live
  listDocuments: () => request<{ items: DocumentOut[] }>("/api/v1/documents"),
  getDocumentDetail: (id: string) =>
    request<{ document: DocumentOut; processingJob: IngestionJobOut | null; concepts: ConceptLinkOut[] }>(
      `/api/v1/documents/${id}`
    ),
  uploadDocument: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentOut>("/api/v1/documents", { method: "POST", body: form });
  },
  deleteDocument: (id: string) => request<void>(`/api/v1/documents/${id}`, { method: "DELETE" }),
  retryDocument: (id: string) => request<DocumentOut>(`/api/v1/documents/${id}/retry`, { method: "POST" }),
  fileUrl: (id: string) => `${API_URL}/api/v1/documents/${id}/file`,

  // Milestone 11 -- confidence & correction UX -- live
  getCorrections: (id: string) =>
    request<{ items: CorrectionOut[] }>(`/api/v1/documents/${id}/corrections`),
  reextractDocument: (id: string) =>
    request<DocumentOut>(`/api/v1/documents/${id}/reextract`, { method: "POST" }),

  // Milestone 5 -- multi-format ingestion -- live
  ingestYoutubeVideo: (url: string) =>
    request<DocumentOut>("/api/v1/documents/youtube", { method: "POST", body: JSON.stringify({ url }) }),

  // Milestone 6 -- classification correction -- live
  updateClassification: (id: string, body: { contentCategory?: string; subject?: string }) =>
    request<DocumentOut>(`/api/v1/documents/${id}/classification`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  // Milestone 7 -- concept graph -- live
  listConcepts: () => request<{ items: ConceptOut[] }>("/api/v1/concepts"),
  getConceptDetail: (id: string) => request<ConceptDetailOut>(`/api/v1/concepts/${id}`),
  getRelatedConcepts: (id: string, depth?: number) =>
    request<RelatedConceptOut[]>(`/api/v1/concepts/${id}/related${depth ? `?depth=${depth}` : ""}`),
  mergeConcept: (id: string, intoConceptId: string) =>
    request<ConceptOut>(`/api/v1/concepts/${id}/merge`, {
      method: "POST",
      body: JSON.stringify({ intoConceptId }),
    }),

  // Milestone 8 -- chat / local-first retrieval -- live
  createConversation: () => request<{ id: string; title: string }>("/api/v1/conversations", { method: "POST", body: JSON.stringify({}) }),
  getConversation: (id: string) =>
    request<{ conversation: { id: string; title: string }; messages: MessageOut[] }>(`/api/v1/conversations/${id}`),
  sendMessage: (id: string, content: string, useExternalFallback = false) =>
    request<{ userMessage: MessageOut; answer: AnswerOut }>(`/api/v1/conversations/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ content, useExternalFallback }),
    }),

  // Milestone 9 -- intent workflows -- live
  sendIntent: (conversationId: string, body: IntentRequest) =>
    request<IntentResponse>(`/api/v1/conversations/${conversationId}/intents`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
