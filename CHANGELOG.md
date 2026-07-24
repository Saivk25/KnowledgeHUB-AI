# Changelog

All notable changes to KnowledgeHub AI are recorded here, one entry per
frozen milestone. Each entry links to that milestone's full design/
implementation/verification record under `docs/milestones/`; this file is
a summary index, not a replacement for those documents.

## [v0.12.0] -- Production Hardening & Portfolio Polish

See `docs/milestones/MILESTONE_12.md` for the full implementation and
verification record, and `docs/adr/0019-production-hardening.md` for the
design decisions summarized below. A hardening pass over Milestones
1-11, not a feature milestone -- concludes the original 12-milestone
roadmap as tabled.

### Added
- `app/services/job_reconciliation.py` (`reconcile_stale_jobs`) -- a
  startup-time, bounded/indexed check that marks any `IngestionJob` left
  `RUNNING` by a crashed prior process as `FAILED`/`INTERRUPTED`, so it
  becomes resumable via the existing retry/reextract endpoints instead of
  stuck forever. Wired into `app/main.py`'s startup event, wrapped
  defensively so a reconciliation failure never blocks API startup. New
  `STALE_JOB_THRESHOLD_MINUTES` config setting.
- `embedding_model_version` on `VectorPoint` (`app/services/vector_repo.py`)
  and a `version` string on every `EmbeddingProvider`
  (`app/services/embeddings.py`: `"local-hash-v1"` /
  `"openai:<model>"`) -- every vector point written from this milestone
  forward (both Qdrant collections) carries which provider produced it.
  A payload index on the new field is created for both newly-created and
  already-existing collections.
- `app/services/reembed.py` -- a batched, resumable re-embed procedure
  that migrates a workspace's mismatched-version points to the currently
  configured provider, reusing the existing `VectorRepository`
  upsert/delete write path rather than a new one.
- `demo-data/` extended with one fixture per remaining supported source
  type (`data_retention_policy.{docx,pptx,md,py,png}`,
  `YOUTUBE_REFERENCE.md`) and `demo-data/seed.py`, a documented seeding
  script that ingests every fixture through the real
  `POST /api/v1/documents` upload path.
- Alembic migration `0010_concept_dedup_unique_index` -- a partial unique
  index on `concepts(workspace_id, normalized_name)` `WHERE status =
  'ACTIVE'`, backing an invariant that was previously enforced only at
  the application layer.
- `WorkspaceStatsOut` schema (`app/schemas/auth.py`) and a
  `_workspace_stats()` helper (`app/api/v1/routes/workspace.py`) --
  `GET /workspace` now returns per-status `Resource` counts
  (`readyDocuments`/`processingDocuments`/`failedDocuments`), reusing the
  same counting pattern `chat.py`'s message-send route already used.
- `docs/DEMO_SCRIPT.md` -- a guided, ~10-15 minute walkthrough of the
  seeded workspace, verified live against a real deployment.
- `docs/assets/screenshots/{documents-library,concept-graph,
  chat-provenance,upload-flow}.png` -- captured from the real, seeded,
  running application and wired into `README.md`.
- 5 new backend test modules: `test_job_reconciliation.py`,
  `test_embedding_versioning.py`, `test_seed_data_cross_format_concept.py`,
  `test_concept_resolution_concurrency.py`, `test_workspace_stats.py`.

### Fixed (discovered during live verification, not TestClient-only testing)
- **Concept-resolution concurrency race:** `resolve_concept()`'s
  exact-match-then-insert check was not atomic across concurrent
  `BackgroundTask` ingestion runs -- two overlapping uploads resolving
  the same concept name could both pass the check before either
  committed, producing duplicate `ACTIVE` concepts. Closed by migration
  `0010` plus an `IntegrityError`-recovery path in `resolve_concept()`
  (scoped to its own `SAVEPOINT` via `db.begin_nested()`), which
  transparently joins the winning row instead of failing. Existing
  application-layer duplicate-evidence/relationship checks are
  unaffected. See `docs/milestones/MILESTONE_12.md` Section 12.
- **Workspace stats missing, hiding the chat UI:** `GET /workspace` never
  returned the `stats` field `apps/web/app/chat/page.tsx` has read since
  Milestone 4 (`ws.stats?.readyDocuments`) -- a silent regression from
  Milestone 8 promoting that screen from dormant to live without also
  building the backend field it depends on. `readyDocuments` was always
  `0`, permanently hiding the chat compose UI for every workspace. Fixed
  by populating `stats` in the existing `GET /workspace` response; no new
  endpoint, no frontend behavior change beyond unblocking the UI the
  contract already promised. See `docs/milestones/MILESTONE_12.md`
  Section 13.

### Changed
- `app/models/concept.py`'s docstring updated to reflect the partial
  unique index as a deliberate, documented exception to this codebase's
  "no DB UNIQUE constraint for cross-field invariants" convention.
- `apps/api/app/api/v1/routes/workspace.py`'s module docstring and
  `apps/web/lib/api.ts`'s `WorkspaceStatsOut`/`getWorkspace()` comments
  corrected to stop describing a state (unpopulated `stats`, a dormant
  chat screen) that stopped being true since Milestone 8.

### Operational notes
- Applying migration `0010` to a deployment that already contains
  duplicate `ACTIVE` concepts fails at `alembic upgrade head` (the
  partial unique index's `CREATE INDEX` is rejected by pre-existing
  duplicate data), and this project's single-container deployment model
  means the API -- including the merge endpoint that would otherwise
  clean up those duplicates -- is unreachable until the same migration
  succeeds. Any deployment carrying real, pre-existing duplicate `ACTIVE`
  concepts needs them resolved by a one-off maintenance step *before* the
  new image is deployed. See `docs/milestones/MILESTONE_12.md` Section
  12.1.

### Testing
- Full suite: 228 passed, 0 failed, 0 skipped (36 test files). Both
  amendment regression tests independently confirmed to fail against
  their respective pre-fix code and pass against the fix.
- Ruff (`ruff check app tests`) and Black (`black --check app tests`)
  clean; `tsc --noEmit` clean.
- Live-verified against a freshly rebuilt `docker compose` deployment
  seeded via `demo-data/seed.py`: single "Data Retention Policy" concept
  with 5 evidence links; `GET /workspace` returns accurate stats; `/chat`
  renders the compose UI; Search mode returns a real provenance-badged,
  cited answer.

### Documentation
- `docs/milestones/MILESTONE_12.md` updated to "Implemented and
  Verified" with the full verification record (Section 14).
- `docs/adr/0019-production-hardening.md` added, covering the
  BackgroundTask re-evaluation, embedding-version tag format, the
  concept-resolution concurrency fix, the workspace-stats fix, and the
  migration-order operational note.

## [v0.11.0] -- Confidence & Correction UX

See `docs/milestones/MILESTONE_11.md` for the full implementation and
verification record, and `docs/adr/0018-confidence-correction-ux.md` for
the design decisions summarized below.

### Added
- `resource_corrections` table (migration `0009_confidence_correction_ux.py`,
  `app/models/correction.py`: `ResourceCorrection`, `CorrectionField`
  enum) -- logs one row per classification field (`CONTENT_CATEGORY` /
  `SUBJECT`) changed via `PATCH /documents/{id}/classification`,
  capturing the prior value and confidence immediately before they're
  overwritten.
- `GET /documents/{id}/corrections` -- new, read-only, workspace-scoped
  route returning a document's correction history, newest first.
- `POST /documents/{id}/reextract` -- new, additive route that re-runs
  the identical ingestion pipeline on an already-`READY` document whose
  extraction confidence is low (409 `DOCUMENT_NOT_READY` otherwise).
  `POST /documents/{id}/retry` and its route are completely unchanged.
- `DocumentOut` gained four optional fields --
  `autoContentCategory`/`autoContentCategoryConfidence`/`autoSubject`/
  `autoSubjectConfidence` -- exposing `Resource.auto_*` (written on every
  classification run since Milestone 6, never returned by the API
  before now).
- `AnswerOut` and `IntentResponse` each gained one optional field,
  `sufficiencyReason` -- exposing `Answer.sufficiency_reason` (computed
  by the unchanged sufficiency scorer since Milestone 8). Populated for
  the `/messages` (Explain) chat path; not yet populated by any of the
  nine `IntentHandler`s, since none was modified this milestone.
- `LOW_CONFIDENCE_THRESHOLD` config setting (`0.5`), shared by extraction
  and classification triage; mirrored client-side in `lib/api.ts` since
  there is no config-exposing endpoint.
- Frontend: a correction-history list, a reclassification-suggestion
  banner ("Use this" / "Keep mine", client-only dismissal), a
  `subjectConfidence`/`subjectConfirmed` display fix, and a "Re-run
  extraction" button, all on the document detail page; a "Needs review"
  filter, a lowest-confidence sort, and a per-row confidence indicator
  on the document library page (built entirely on already-returned
  `DocumentOut` fields, no new route); the previously-dropped
  `sufficiencyScore` now rendered in chat, plus a "Why?" affordance
  mapping `sufficiencyReason`'s five fixed codes to plain-language
  sentences.
- 18 new backend tests in `tests/test_confidence_correction_ux.py`:
  correction-row insertion (single field, both fields, pre-overwrite
  value/confidence capture), correction-history read (newest-first,
  auth, 404, workspace isolation), `auto_*` field exposure surviving a
  later reclassification, `reextract` success/rejection cases, and
  `sufficiencyReason` presence on both `AnswerOut` and `IntentResponse`.

### Changed
- `PATCH /documents/{id}/classification` -- request/response shape and
  externally-visible behavior unchanged; now additionally inserts a
  `resource_corrections` row per changed field.
- `tests/test_alembic_migrations.py` -- `EXPECTED_TABLES` extended with
  `resource_corrections`.

### Testing
- Full suite: 207 passed, 0 failed, 3 skipped (skips are the
  Tesseract-OCR-dependent tests, unchanged from Milestone 10, skipped
  only when the `tesseract` binary isn't on `PATH`).
- Full regression of every existing `/retry` test: unchanged behavior
  confirmed (`retry_document` has zero lines changed).
- Ruff and Black clean on every new/changed file; `tsc --noEmit` clean.

### Documentation
- `docs/milestones/MILESTONE_11.md` updated to "Implemented and
  Verified" with the full verification record and a pre-freeze
  implementation review (four minor documentation/cleanup fixes found
  and applied; zero functional or scope issues).
- `docs/adr/0018-confidence-correction-ux.md` added, covering why
  `resource_corrections` is a separate, persisted table; why
  `reextract` is a new route rather than a change to `retry`; why
  confidence metadata is exposed additively; and why chat-answer
  feedback was intentionally left out of scope.

## [v0.10.0] -- Study Workflows

See `docs/milestones/MILESTONE_10.md` for the full implementation and
verification record.

### Added
- Five new `IntentHandler`s completing the nine-intent FR-8 set:
  `QuizIntent`, `FlashcardsIntent`, `VivaIntent`, `RevisionIntent`,
  `StudyPlannerIntent` (`app/services/intents/`), registered in the same
  plugin registry alongside Milestone 9's four.
- Two new tables (migration `0008_study_workflows.py`,
  `app/models/study.py`): `QuizAttempt` (server-side-only generated
  answer key) and `VivaSession` (server-side-only turn-by-turn grading
  rubric and transcript) -- the first genuinely multi-turn intents in
  this codebase, needing private state that survives between a
  generation/start turn and a later grading/continuation turn without
  ever being echoed back to the client in between.
- Quiz me: multiple-choice only, generated then graded by exact-match
  against the stored `correctChoice` index -- zero additional LLM calls
  to grade.
- Flashcards: the same resource/concept/freeform three-mode resolution
  Summarize already established, generating cited front/back pairs.
- Viva mode: an adaptive, N-turn oral-exam-style flow -- each turn grades
  the previous answer against its private rubric and asks a new question
  grounded in the same evidence, completing at `VIVA_MAX_TURNS`.
- Revision mode: ranks concepts/resources by review urgency (never
  reviewed / low quiz score / thin evidence), reading only this
  milestone's own `QuizAttempt`/`VivaSession` history and the existing
  concept graph.
- Study planner: spreads 2+ targets across a schedule that is always
  computed deterministically in Python (day/target assignment is never
  LLM-decided); a single batched `LLMProvider.narrate_study_plan()` call
  phrases the already-decided schedule.
- New shared helper `app/services/study_signals.py`'s
  `assess_review_need()`, called by both Revision mode and Study planner
  rather than duplicating "what needs review" logic.
- `LLMProvider` gained four new methods -- `generate_quiz`,
  `generate_flashcards`, `conduct_viva_turn`, `narrate_study_plan` -- on
  both `OpenAIChatProvider` (one retry on malformed JSON) and
  `ExtractiveFallbackProvider` (cloze-deletion quiz, sentence-based
  flashcards, keyword-overlap viva grading, pass-through narration).
- `IntentRequest`/`IntentResult` extended additively: `IntentType` gains
  `QUIZ`/`FLASHCARDS`/`VIVA`/`REVISION`/`STUDY_PLAN`; new optional
  request fields (`questionCount`, `quizId`, `quizAnswers`, `sessionId`,
  `vivaAnswer`, `targetDate`, `horizonDays`); `IntentResult`'s
  discriminated union grows from four members to nine. Every Milestone 9
  field's meaning is unchanged.
- Frontend: `components/StudyPanels.tsx` (`QuizPanel`/`FlashcardsPanel`/
  `VivaPanel`), embedded on both the document and concept detail pages;
  two new pages, `/revision` and `/study-plan`.

### Changed
- `api/v1/routes/chat.py`'s transcript-rendering helpers
  (`_describe_intent_request`, `_extract_assistant_content`) gained five
  new branches, one per new intent -- the only touch to a Milestone 9
  file this milestone made, and purely cosmetic transcript text; no
  routing, persistence, or dispatch logic changed.

See `docs/adr/0017-study-workflows.md` for the full design, including all
five approved decisions (statefulness via two new tables, MCQ-only quiz,
Revision mode's data sources, Study planner's deterministic-scheduling-
plus-LLM-narration split, and the scoped exception to touch `chat.py`).

## [v0.9.0-intent-workflows] -- Intent Workflows

See `docs/milestones/MILESTONE_9.md` for the full implementation and
verification record.

### Added
- `app/services/intents/`: an `IntentHandler` plugin registry (mirroring
  the `Extractor`/`Classifier`/`ConceptLinker` pattern) with one class
  per intent -- `ExplainIntent`, `SearchIntent`, `SummarizeIntent`,
  `CompareIntent` -- and a `registry.get_intent_handler()` lookup, rather
  than a branching dispatcher.
- Shared `IntentRequest`/`IntentResponse` envelope
  (`app/schemas/intents.py`), discriminated on `result.kind`, satisfying
  DRR Section 4's "define the envelope before the first intent" mandate.
- `POST /api/v1/conversations/{id}/intents` -- the one real dispatch
  route for all four intents.
- Search: always returns ranked hits with zero sufficiency gating;
  additionally calls the LLM for a grounded, clearly-labeled
  `assistedSynthesis` only when the top result's confidence is below
  `SEARCH_LLM_CONFIDENCE_THRESHOLD`.
- Summarize: resource-target, concept-target, and freeform-question
  modes, the last going through the same sufficiency gate Explain uses.
- Compare: 2-4 targets (resource, concept, or freeform per target);
  partial evidence gaps are labeled honestly rather than silently
  filled; total insufficiency behaves like Explain's insufficient case.
- `Answer.intent`/`Answer.intent_payload` and `Citation.target_label`
  columns (migration `0007_intent_workflows.py`).
- `LLMProvider.summarize()`/`compare()` on both `OpenAIChatProvider` and
  `ExtractiveFallbackProvider`.
- Frontend: an Explain/Search toggle in chat, a Summarize panel on
  document and concept detail pages, and a multi-select Compare flow on
  the concepts list.

### Changed
- `POST /api/v1/conversations/{id}/messages` (Milestone 8) is now a thin
  EXPLAIN-only wrapper over the same intent dispatch path -- unchanged
  from the frontend's point of view, per DRR Section 8's "one contract,
  thin wrapper" principle.
- `services/retrieval_service.py` refactored (behavior unchanged):
  shared resource-target/concept-target/freeform evidence-resolution
  helpers extracted for reuse by Summarize and Compare.

See `docs/adr/0016-intent-workflows.md` for the full design and
`docs/milestones/MILESTONE_9.md` for the complete implementation record.

## [v0.8.0-local-first-retrieval] -- Local-First Retrieval & Provenance

See `docs/milestones/MILESTONE_8.md` for the full implementation and
verification record.

### Added
- Hybrid retrieval: dense vector search plus one-hop concept-graph
  expansion (reusing Milestone 7's `find_nearby_concepts()`), merged and
  deduplicated by real chunk identity.
- Additive ranking: `final_score = vector_similarity + concept_match_boost
  + metadata_match_boost` (ADR-0003's "no reranker" stays in force).
- A standalone sufficiency scorer (`services/sufficiency.py`) -- fail-closed
  by construction, the single source for the sufficiency verdict,
  sufficiency score, and retrieval confidence.
- Structural provenance on every answer: `LOCAL`, `HYBRID`, `EXTERNAL`, or
  none, each requiring explicit consent for anything beyond `LOCAL`.
- Workspace-level (`allow_external_fallback`) and per-request
  (`useExternalFallback`) consent gates before any external model call.
- `/api/v1/conversations` (chat) mounted for the first time; dormant since
  Milestone 4.
- Chat UI reactivated (`apps/web/app/chat/`) with a provenance badge,
  retrieval confidence, and an external-fallback confirmation control.

### Changed
- `Answer.status` values renamed `NO_EVIDENCE` -> `INSUFFICIENT`.
- `services/retrieval_service.py` rewritten (not replaced): Milestone 4's
  dense-only search and citation-integrity rule are unchanged; hybrid
  candidate assembly, ranking, and provenance decisioning are new.
- `services/llm.py`'s `LLMProvider` interface gained
  `answer_general_knowledge()`.

### Fixed (pre-verification audit)
- Consolidated a duplicated cosine-similarity implementation into
  `services/vector_repo.py`'s (now public) `cosine_similarity()`.
- Sufficiency corroboration now counts distinct resources, not raw chunk
  hits -- two chunks from the same document no longer count as two
  independent supporting hits.
- `api/v1/routes/chat.py` now uses the `ResourceStatus.READY` constant
  instead of a string literal, for consistency with the rest of the
  codebase.
- Added a retrieval-latency sanity test so `RETRIEVAL_LATENCY_TARGET_MS`
  is actually exercised by the test suite, not just documented.
- Added the structured logging DRR Section 16 requires (sufficiency score,
  reason, provenance, citation count) at every point a provenance decision
  is made -- previously only persisted to the `Answer` row, not logged.

See `docs/adr/0015-retrieval-provenance.md` for the full design and
`docs/milestones/MILESTONE_8.md` for the complete implementation record,
including the pre-verification audit this entry summarizes.

## [v0.7.0-concept-graph] -- Concept Graph
concepts/resource_concepts/concept_relationships schema, incremental
concept-linking on ingestion, browse-by-concept UI, deduplication and
cycle-safe traversal. See `docs/milestones/MILESTONE_7.md`.

## [v0.6.0-metadata-classification] -- Metadata, Classification & Confidence
Content-category/subject classification with confidence scores and
manual-correction workflow. See `docs/milestones/MILESTONE_6.md`.

## [v0.5.0-multi-format-ingestion] -- Multi-Format Ingestion
DOCX/PPTX/TXT/MD/code/image-OCR/YouTube-transcript ingestion via an
`Extractor` registry. See `docs/milestones/MILESTONE_5.md`.

## [v0.4.0-resource-model] -- Resource Model
`Document` renamed to `Resource`; schema management moved to Alembic. See
`docs/milestones/MILESTONE_4.md`.

## [v0.3.0-document-ingestion] -- Document Ingestion
PDF upload, extraction, chunking, embedding, and vector indexing.

## [v0.2.0-authentication] -- Authentication
User registration/login and per-user workspace creation.

## [v0.1.0-foundation] -- Project Foundation
Initial FastAPI + Next.js + Postgres + Qdrant scaffold, health checks,
Docker Compose.
