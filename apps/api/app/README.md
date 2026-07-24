# apps/api/app -- module map

`app/main.py` mounts four routers right now: `app/api/routes/health.py`
(Milestone 1), `app/api/v1/routes/auth.py` +
`app/api/v1/routes/workspace.py` (Milestone 2), and
`app/api/v1/routes/documents.py` (Milestone 3) -- the latter three via
`app/api/v1/router.py`. Everything else below exists in the repository
because it was already built and reviewed in an earlier pass, but is not
imported by anything on the live request path. This file exists so that
is never ambiguous from a directory listing alone.

| Path | Milestone that activates it | Mounted in app.main today? |
|---|---|---|
| `api/routes/health.py` | 1 -- Project Foundation | **Yes** |
| `core/config.py`, `main.py`, `db/` | 1 -- Project Foundation | **Yes** |
| `core/security.py` | 2 -- Authentication | **Yes** |
| `deps.py` | 2 -- Authentication | **Yes** |
| `models/user.py`, `models/workspace.py` | 2 -- Authentication | **Yes** |
| `schemas/auth.py` | 2 -- Authentication | **Yes** |
| `api/v1/routes/auth.py`, `api/v1/routes/workspace.py` | 2 -- Authentication | **Yes** |
| `models/resource.py` (renamed from `models/document.py` in Milestone 4 -- see `docs/adr/0011-resource-content-model.md`), `models/ingestion_job.py` | 3 -- Document Ingestion | **Yes** |
| `services/storage.py`, `services/extraction.py`, `services/chunking.py`, `services/ingestion_service.py` | 3 -- Document Ingestion | **Yes** |
| `services/embeddings.py` (embed/write path), `services/vector_repo.py` (upsert/delete) | 3 -- Document Ingestion | **Yes** |
| `schemas/document.py`, `api/v1/routes/documents.py` | 3 -- Document Ingestion | **Yes** |
| `models/concept.py`, `services/concept_linking.py`, `services/concept_graph.py`, `schemas/concept.py`, `api/v1/routes/concepts.py` | 7 -- Concept Graph | **Yes** |
| `models/conversation.py`, `models/answer.py`, `models/citation.py` | 8 -- Local-First Retrieval & Provenance | **Yes** |
| `services/embeddings.py` (`embed_one` on a query), `services/vector_repo.py` (`search`), `services/llm.py`, `services/retrieval_service.py`, `services/sufficiency.py` | 8 -- Local-First Retrieval & Provenance | **Yes** |
| `schemas/chat.py`, `api/v1/routes/chat.py` | 8 -- Local-First Retrieval & Provenance | **Yes** |
| `schemas/intents.py`, `services/intents/` (`base.py`, `explain.py`, `search.py`, `summarize.py`, `compare.py`, `registry.py`) | 9 -- Intent Workflows | **Yes** |
| `models/study.py` (`QuizAttempt`, `VivaSession`), `services/study_signals.py`, `services/intents/` (`quiz.py`, `flashcards.py`, `viva.py`, `revision.py`, `study_planner.py`) | 10 -- Study Workflows | **Yes** |
| `models/correction.py` (`ResourceCorrection`, `CorrectionField`) | 11 -- Confidence & Correction UX | **Yes** |
| `services/job_reconciliation.py` | 12 -- Production Hardening & Portfolio Polish | **Yes** -- called from `main.py`'s startup event |
| `services/reembed.py` | 12 -- Production Hardening & Portfolio Polish | Standalone tooling, not mounted as a route (script/procedure, per Section 4.2's design) |
| `api/v1/router.py` | 2/3/7/8 (all aggregated here) | **Yes** -- imports `auth`, `workspace`, `documents`, `concepts`, and (as of Milestone 8) `chat` |

Note on `services/embeddings.py` and `services/vector_repo.py`: both files
are shared between Milestone 3 and Milestone 8, not duplicated. Milestone
3 only calls the *write* side of each (`embed()` on chunks at ingest time,
`upsert()`/`delete_by_document()` on the vector store); the *read* side
(`embed_one()` on a user's question, `search()` against the vector store)
is exercised by `services/retrieval_service.py`, mounted as of Milestone 8.
This is why documents.py could be mounted in Milestone 3 without pulling
in any Milestone 8 behavior -- the split was already at the function
level before Milestone 8 started, not something that milestone had to
introduce.

Note on `workspace.py`: as of Milestone 12 (Section 13 addendum),
`GET /workspace` now returns a `stats` field (per-status `Resource`
counts: `readyDocuments`/`processingDocuments`/`failedDocuments`) --
see `_workspace_stats()` in `api/v1/routes/workspace.py` and
`schemas/auth.py`'s `WorkspaceStatsOut`. This was left unimplemented from
Milestone 2 through Milestone 11 because no consumer was known to need a
server-computed aggregate (the Documents page calls `GET /documents` and
computes its own counts client-side); Milestone 12 discovered live that
`apps/web/app/chat/page.tsx` had actually depended on this field since
Milestone 4 and silently broke when that screen went live in Milestone 8
-- see `docs/milestones/MILESTONE_12.md` Section 13 for the full
discovery.

## Milestone 6 note (Metadata, Classification & Confidence)

`services/classification.py` is a new `Classifier` registry, the same
shape as `EmbeddingProvider`/`LLMProvider`:
`LocalHeuristicClassifier` (default, zero-config, keyword-rule based) and
`OpenAIClassifier` (auto-selected only when `CLASSIFICATION_PROVIDER=openai`
and `OPENAI_API_KEY` are both set). Classification runs as a new
`IngestionStep.CLASSIFYING` stage between extraction and chunking
(`services/ingestion_service.py`). `models/resource.py` gained ten nullable
columns (migration `0004_classification_metadata`): authoritative/display
fields (`content_category`, `subject`, their confidences, and
`_confirmed` flags) plus `auto_content_category`/`auto_subject` (always the
latest automatic result, independent of confirmation state -- see
`docs/adr/0013-classification-confidence.md` for why these are two
separate layers, not one). `api/v1/routes/documents.py` gained
**`PATCH /documents/{id}/classification`** for manual correction, and
`_to_out()` now also surfaces `extractionConfidence` (an M5 field, exposed
in the API for the first time here).

**Confidence definitions, written down once (per DRR Section 9):**
`extraction_confidence` = the extractor's own reported score (always 1.0
except image OCR, which is Tesseract's real per-word confidence -- see
ADR-0012). `content_category_confidence`/`subject_confidence` from
`LocalHeuristicClassifier` = a documented, deterministic function of which
keyword/phrase rules matched (see `classification.py`'s `CATEGORY_RULES`
and the confidence-mapping constants) -- never invented. From
`OpenAIClassifier`, both confidences are the number the model reported in
its structured JSON response, unmodified. A confidence of `1.0` on a
`_confirmed` field means "a human said so," not a model's estimate.

As of Milestone 8, nothing under `app/` remains dormant -- `chat.py`,
`retrieval_service.py`, and `llm.py` (with its new
`answer_general_knowledge` method) are all on the live request path. Two
things about how they got there are worth keeping visible, since the
convention below applied to every milestone up to and including this one:

1. **Runtime dependencies stay minimal on purpose.** No new Python
   packages were required to activate `services/llm.py` and
   `api/v1/routes/chat.py` -- both already depended only on `httpx`
   (already installed since Milestone 4's original build) and this
   codebase's own modules. Their dependencies would have moved into
   `requirements.txt` in the same commit that mounted their router, had
   any been needed -- that is what "the Docker image contains only this
   milestone's runtime dependencies" means in practice.
2. **`app/core/config.py` is the one exception to "only declare what's
   used."** Settings fields for later milestones are declared with safe
   defaults ahead of the milestone that consumes them, grouped by
   milestone in that file. A dormant module finding a missing settings
   *field* is a silent landmine (`AttributeError` the moment it's
   reactivated); a dormant module finding a missing *package* is loud and
   expected (`ModuleNotFoundError`). Declaring a config field costs
   nothing and isn't "implementing" the feature it belongs to.

To activate a milestone: add its dependencies to `requirements.txt`,
mount its router(s) in `app/api/v1/router.py`, and move its tests out of
the skip/importorskip guard in `apps/api/tests/`.

## Milestone 4 note (schema/tooling only, not in the table above)

Milestone 4 (per the DRR, not the "RAG Chat" milestone this file's table
numbers above) made two implementation-detail changes across the whole
`app/` tree rather than to one milestone's slice of it: `models/document.py`
was renamed to `models/resource.py` (`Document` -> `Resource`, table
`documents` -> `resources` -- see `docs/adr/0011-resource-content-model.md`),
and schema management moved from `Base.metadata.create_all` to Alembic
(`alembic/`, see `docs/adr/0010-alembic-migrations.md`). Every file that
imported the old `Document` model -- including `services/retrieval_service.py`
and `api/v1/routes/chat.py`, both dormant at the time -- was updated to
import `Resource` instead, so the "Mounted in app.main today?" column
above stayed accurate without any dormant module also being a landmine
against a model that no longer existed.

## Milestone 5 note (Multi-Format Ingestion, per the roadmap's own numbering)

`services/extraction.py` is no longer one PyMuPDF-only function -- it is an
`Extractor` registry (`PdfExtractor`, `DocxExtractor`, `PptxExtractor`,
`TextExtractor`, `CodeExtractor`, `ImageOcrExtractor`), resolved by file
extension, all returning the same `ExtractionResult` contract. See
`docs/adr/0012-multi-format-extraction.md` for why each format was built the
way it was (OCR engine choice, code-file allowlist, YouTube-as-virtual-file).
New module `services/youtube.py` fetches a YouTube video's transcript and
hands it to the same upload pipeline via `POST /documents/youtube` --
`api/v1/routes/documents.py` gained this one new route; every other route on
that file is unchanged. `models/resource.py` gained one new nullable column,
`extraction_confidence` (migration `0003_extraction_confidence`), populated
by every extractor (1.0 except image OCR, which reports Tesseract's real
per-word confidence) -- stored now, not yet surfaced in the API response
(that's Roadmap Milestone 10/11's job). New runtime dependencies
(`python-docx`, `python-pptx`, `pytesseract`, `Pillow`,
`youtube-transcript-api`, plus the `tesseract-ocr` system package in the
Dockerfile) all landed in this milestone specifically because this is the
first milestone that needs them, continuing the discipline described above.

## Milestone 7 note (Concept Graph, per the roadmap's own numbering)

Three new tables (migration `0005_concept_graph`, models in
`models/concept.py`): `Concept`, `ResourceConcept` (the evidence link --
resource contributes evidence to concept, with a required
`evidence_chunk_id`), `ConceptRelationship` (a typed, directed edge
between two concepts, also with a required `evidence_chunk_id`). No new
runtime dependencies -- concept linking reuses `services/embeddings.py`
and `services/vector_repo.py` exactly as they already existed.

Two new service modules mirror the existing registry pattern:
`services/concept_linking.py` (`ConceptLinker`: `LocalConceptLinker`
reuses Milestone 6's `subject`/`content_category` fields as a seed, never
adds NLP; `OpenAIConceptLinker` is retrieval-grounded and auto-selected
only when `CONCEPT_LINKER_PROVIDER=openai` and `OPENAI_API_KEY` are both
set) and `services/concept_graph.py` (entity-resolution/dedup via
`resolve_concept`, the manual-merge escape hatch via `merge_concepts`,
orphan-prevention via `recompute_concept_usage`, and the one shared
cycle-safe traversal helper, `traverse_concept_graph`, that every current
and future graph query must use). `services/vector_repo.py` gained a
second collection (`get_concept_vector_repository()`) for concept-level
embeddings, reusing the same Qdrant deployment rather than a new store.

Ingestion gains a new `CONCEPT_LINKING` stage between indexing and
`DONE` (`services/ingestion_service.py`'s `_link_concepts`), with the same
graceful-degradation rule Milestone 6 established for classification: a
concept-linking failure is logged and never fails the resource.
`api/v1/routes/concepts.py` (new, mounted in `api/v1/router.py`) is
read/merge only -- concepts are only ever created by the ingestion
pipeline. `api/v1/routes/documents.py`'s `get_document` now additionally
returns this resource's concept evidence links; `delete_document` runs
the orphan-prevention check after its cascade delete removes a resource's
evidence links. See `docs/adr/0014-concept-graph.md` for the full set of
approved design decisions, including the dedup thresholds, the
evidence-required rule, and the BackgroundTask-vs-queue re-evaluation.

## Milestone 8 note (Local-First Retrieval & Provenance, per the roadmap's own numbering)

`chat.router` is mounted for the first time -- migration
`0006_retrieval_provenance` finally creates `conversations`, `messages`,
`answers`, `citations` (dormant since Milestone 4, per
`0001_baseline_schema.py`'s own docstring). `services/retrieval_service.py`
is rewritten, not replaced: Milestone 4's dense-only top-k Qdrant search
and citation-integrity rule (ADR-0003) are unchanged; new is hybrid
candidate assembly (raw vector hits + Milestone 7's one-hop
`find_nearby_concepts()`), an additive ranking formula
(`vector_similarity + concept_match_boost + metadata_match_boost`), and a
delegated call to the new `services/sufficiency.py` for the sufficiency
verdict/score/confidence. `services/llm.py` gained
`answer_general_knowledge()`, following ADR-0004's exact provider pattern
(a real answer via `OpenAIChatProvider`, an honest degraded message via
`ExtractiveFallbackProvider`, never fabricated). `models/answer.py` gained
`provenance`/`sufficiency_score`/`retrieval_confidence`/`sufficiency_reason`;
`models/workspace.py` gained `allow_external_fallback` (default `False`).
See `docs/adr/0015-retrieval-provenance.md` for the full design,
including the vector-hit ↔ concept-expansion chunk-identity
reconciliation this milestone's hybrid merge depends on.

## Milestone 9 note (Intent Workflows, per the roadmap's own numbering)

New package `services/intents/` -- one `IntentHandler` per intent
(`ExplainIntent`, `SearchIntent`, `SummarizeIntent`, `CompareIntent`),
registered in `registry.py`, mirroring the `Extractor`/`Classifier`/
`ConceptLinker` plugin-registry pattern rather than a single function
branching on intent type (amended into the design specifically so
Milestone 10's five additional intents stay additive). `schemas/intents.py`
defines the DRR Section 4 shared envelope (`IntentRequest`/
`IntentResponse`, `result` a discriminated union per intent).

`services/retrieval_service.py` gained five new functions
(`resolve_question_candidates`, `resolve_citations_and_evidence`,
`resolve_freeform_evidence`, `resolve_resource_evidence`,
`resolve_concept_evidence`) -- shared retrieval primitives every intent
calls; `answer_question()` itself is unchanged in behavior, now just
calling `resolve_question_candidates()` instead of duplicating that
logic inline. `services/llm.py` gained `summarize()`/`compare()` on
`LLMProvider`, same real-vs-honest-fallback pattern as
`answer_general_knowledge()`.

New route `POST /conversations/{id}/intents` (`api/v1/routes/chat.py`) is
the one real dispatch entry point for all four intents.
`POST /conversations/{id}/messages` (Milestone 8) is kept, unchanged, as
a separate full-fidelity EXPLAIN-only path -- both call the identical
`retrieval_service.answer_question()`, so there is exactly one
implementation of the retrieval logic; see `create_intent()`'s docstring
for why this is a refinement of the "thin wrapper" design, not a
deviation from it. `models/answer.py` gained `intent`/`intent_payload`;
`models/citation.py` gained `target_label`; `schemas/chat.py`'s
`CitationOut` gained `chunkId`/`targetLabel` (migration
`0007_intent_workflows`). See `docs/adr/0016-intent-workflows.md` and
`docs/milestones/MILESTONE_9.md` for the full design, including the three
approved trade-offs (Compare's partial-evidence handling, provenance's
unchanged 3-value contract, and Search's confidence-triggered LLM call).

## Milestone 10 note (Study Workflows, per the roadmap's own numbering)

Five new `IntentHandler`s complete the nine-intent set ADR-0016 started:
`QuizIntent`, `FlashcardsIntent`, `VivaIntent`, `RevisionIntent`,
`StudyPlannerIntent` (`services/intents/`), registered in the same
`registry.py` alongside Milestone 9's four. `schemas/intents.py`'s
`IntentType` and `IntentRequest` grow additively (new fields only,
nothing renamed or repurposed); `IntentResult`'s discriminated union goes
from four members to nine.

Two new tables (migration `0008_study_workflows`, models in
`app/models/study.py`): `QuizAttempt` (`questions_payload` holds the
full generated answer key, server-side only) and `VivaSession`
(`transcript_payload` holds the full turn-by-turn grading rubric and
evidence, also server-side only). These exist because Quiz me and Viva
mode are the first two intents in this codebase that are genuinely
multi-turn -- a generation/start turn and a later grading/continuation
turn, with private state that must survive between them without ever
being echoed back to the client in between. See
`docs/adr/0017-study-workflows.md` decision 1 for why this is two new
tables and not a widened `Answer.intent_payload`.

New shared service module `services/study_signals.py` --
`assess_review_need()` is called by both `RevisionIntent` and
`StudyPlannerIntent` (never duplicated), deriving a priority/reason from
a concept or resource's own `QuizAttempt`/`VivaSession` history plus
existing `ResourceConcept` evidence density. It reads Milestone 7's
concept graph and this milestone's two new tables; it does not read or
modify anything belonging to Milestone 9's four intents.

`services/llm.py` gained four new `LLMProvider` methods --
`generate_quiz`, `generate_flashcards`, `conduct_viva_turn`,
`narrate_study_plan` -- following the same real-vs-honest-fallback
pattern as `answer_general_knowledge`/`summarize`/`compare`:
`OpenAIChatProvider` calls the model (one retry on malformed JSON, then a
`RuntimeError`); `ExtractiveFallbackProvider` never calls out --
cloze-deletion quiz questions, sentence-based flashcards,
keyword-overlap viva grading, and pass-through study-plan narration
(the `reason` text unchanged), so the whole golden path stays runnable
with zero paid dependencies, same as every provider-backed feature
before it.

`api/v1/routes/chat.py`'s transcript-rendering helpers
(`_describe_intent_request`, `_extract_assistant_content`) gained five
new branches, one per new intent -- the only touch to a Milestone 9 file
this milestone made, and explicitly approved as scoped/cosmetic-only
(see `docs/adr/0017-study-workflows.md` decision 5). No other Milestone
9 file changed. No changes to `Resource`/`Concept`/`ResourceConcept`/
`ConceptRelationship`/`Answer`/`Citation`. See
`docs/adr/0017-study-workflows.md` and `docs/milestones/MILESTONE_10.md`
for the full design, including all five approved decisions.

## Milestone 11 note (Confidence & Correction UX, per the roadmap's own numbering)

One new table (migration `0009_confidence_correction_ux`, model in
`models/correction.py`): `ResourceCorrection` (`CorrectionField` enum:
`CONTENT_CATEGORY`/`SUBJECT`) -- logs one row per classification field
changed via the existing `PATCH /documents/{id}/classification` route,
capturing the prior value/confidence immediately before it's
overwritten. New read-only route `GET /documents/{id}/corrections`
(`api/v1/routes/documents.py`) surfaces this history newest-first; the
route itself is additive, `PATCH .../classification`'s own
request/response shape is unchanged.

New route `POST /documents/{id}/reextract` re-runs the identical
ingestion pipeline on an already-`READY` document with low extraction
confidence; `POST /documents/{id}/retry` (Milestone 3, `FAILED`-only) has
zero lines changed. `DocumentOut` gained four optional fields exposing
`Resource.auto_content_category`/`auto_subject` and their confidences
(written on every classification run since Milestone 6, never returned
by the API before now). `AnswerOut`/`IntentResponse` each gained
`sufficiencyReason`, exposing `Answer.sufficiency_reason` (computed by
the unchanged Milestone 8 sufficiency scorer). New
`LOW_CONFIDENCE_THRESHOLD` config setting, shared by extraction and
classification triage. See `docs/adr/0018-confidence-correction-ux.md`
and `docs/milestones/MILESTONE_11.md` for the full design.

## Milestone 12 note (Production Hardening & Portfolio Polish, per the roadmap's own numbering)

A hardening pass, not a feature milestone -- no new entity, endpoint, or
capability is introduced anywhere in this milestone; every change below
either extends an existing response/model additively or corrects a
previously-incorrect behavior.

New module `services/job_reconciliation.py` (`reconcile_stale_jobs`),
called from `main.py`'s startup event: marks any `IngestionJob` left
`RUNNING` by a crashed prior process as `FAILED`/`INTERRUPTED`, resumable
via the existing retry/reextract endpoints. New
`STALE_JOB_THRESHOLD_MINUTES` config setting. No change to
`_run_ingestion`'s stage logic itself.

`services/embeddings.py`'s `EmbeddingProvider`s each gained a `version`
string (`"local-hash-v1"` / `"openai:<model>"`); `services/vector_repo.py`'s
`VectorPoint` gained `embedding_model_version`, written on every point in
both collections (chunk points via `services/ingestion_service.py`,
concept points via `services/concept_graph.py`). New standalone module
`services/reembed.py` provides a batched, resumable re-embed procedure --
not mounted as a route, invoked as tooling.

Alembic migration `0010_concept_dedup_unique_index` adds a partial
unique index on `concepts(workspace_id, normalized_name) WHERE status =
'ACTIVE'` -- `services/concept_graph.py`'s `resolve_concept()` now
catches the resulting `IntegrityError` (scoped to its own `SAVEPOINT` via
`db.begin_nested()`) and transparently joins the winning row instead of
failing, closing a concurrency race discovered during real (not
`TestClient`-only) concurrent ingestion. `models/concept.py`'s docstring
updated accordingly. See `docs/milestones/MILESTONE_12.md` Section 12.

`schemas/auth.py` gained `WorkspaceStatsOut`;
`api/v1/routes/workspace.py`'s `get_workspace` now computes and returns
per-status `Resource` counts via a new `_workspace_stats()` helper,
reusing `chat.py`'s existing counting pattern -- closing a Milestone
4-through-8 contract gap that had left the live chat compose UI
permanently hidden. See `docs/milestones/MILESTONE_12.md` Section 13.

No changes to `Resource`/`Concept`/`ResourceConcept`/
`ConceptRelationship`/`Answer`/`Citation`/`ResourceCorrection` beyond
what's described above. See `docs/adr/0019-production-hardening.md` and
`docs/milestones/MILESTONE_12.md` for the full design, including both
discovered-in-flight amendments.
