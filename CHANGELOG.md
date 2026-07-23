# Changelog

All notable changes to KnowledgeHub AI are recorded here, one entry per
frozen milestone. Each entry links to that milestone's full design/
implementation/verification record under `docs/milestones/`; this file is
a summary index, not a replacement for those documents.

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
