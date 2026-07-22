# Milestone 8 -- Local-First Retrieval & Provenance

**Status: Implemented and Verified.** Every item below was run for real
against this repository -- local SQLite test suite, Ruff/Black, and a full
Docker Compose build/up against real Postgres and Qdrant -- with output
reviewed and, where issues surfaced, fixed and re-verified before this
milestone was committed and tagged.

## Approved scope (Roadmap, verbatim)

"Local vector search (+ concept-graph expansion), sufficiency scorer,
provenance-labeled answer composer, explicit/configurable external
fallback. Hard gate: FR-10 test suite must pass before this milestone can
freeze."

## Approved design decisions

1. **Embedding provider**: `LocalHashEmbeddingProvider` stays the
   zero-config default. No new embedding provider introduced.
2. **Concept expansion**: one-hop only, via Milestone 7's
   `find_nearby_concepts()`. No recursive graph traversal during
   retrieval.
3. **Sufficiency scorer**: a standalone component
   (`app/services/sufficiency.py`), the single source for the sufficiency
   verdict, sufficiency score, and retrieval confidence. Never duplicated
   elsewhere.
4. **External fallback**: `Workspace.allow_external_fallback` defaults to
   `False`. An external model is never called without either that setting
   or explicit per-request confirmation.
5. **Hybrid provenance**: `HYBRID` only exists when the user explicitly
   requests supplementation -- never a silent blend of local evidence and
   general knowledge.
6. **Ranking**: `final_score = vector_similarity + concept_match_boost +
   metadata_match_boost`. ADR-0003 (no BM25, no cross-encoder reranker, no
   learned ranking model) stays intact.
7. **UI**: reactivate the existing dormant chat UI. Only three additions:
   provenance badge, retrieval confidence, external fallback confirmation.
   No interface redesign.

Additional mandatory constraints: every factual statement generated from
local knowledge remains traceable to one or more citations; every citation
points at the exact supporting chunk; concept-expanded retrieval produces
citations through the same citation pipeline as vector retrieval; the
answer-generation layer never knows whether a citation originated from
vector search or concept expansion; fail closed -- if sufficiency cannot
be computed, return `INSUFFICIENT`, never assume sufficient.

## Implemented

- **`apps/api/app/services/sufficiency.py`** -- new. `ScoredCandidate`,
  `SufficiencyVerdict` dataclasses; `compute_sufficiency()` -- fail-closed
  formula (see ADR-0015 for the exact rules: strong single hit, thin
  single hit penalized, corroborated hits, min-score gate, clamped to
  `[0, 1]`).
- **`apps/api/app/services/retrieval_service.py`** -- rewritten (not
  replaced: dense-only top-k search, `MIN_SCORE_THRESHOLD`, and citation
  integrity from Milestone 4 are unchanged). New: `_build_candidates()`
  (hybrid vector + one-hop concept expansion, with the vector-hit ↔
  concept-expansion chunk-identity reconciliation documented in this
  module's own docstring and in ADR-0015), `_score_candidates()` (additive
  ranking formula), `_build_citations_and_evidence()`, `_insufficient_result()`
  (the 4-way provenance decision), and an extended `answer_question()`
  signature (`use_external_fallback`, `allow_external_fallback`).
  `AnswerResult` gained `provenance`, `sufficiency_score`,
  `retrieval_confidence`, `sufficiency_reason`, `can_offer_external_fallback`.
- **`apps/api/app/services/llm.py`** -- `LLMProvider` gained an abstract
  `answer_general_knowledge(question) -> str`, implemented on
  `OpenAIChatProvider` (a distinct system prompt requiring the model to
  disclose the answer is not from the user's documents) and
  `ExtractiveFallbackProvider` (an honest "requires a configured AI
  provider" message -- never fabricated, per ADR-0004's precedent).
- **`apps/api/app/core/config.py`** -- new settings: `CONCEPT_MATCH_BOOST`
  (0.15), `METADATA_MATCH_BOOST` (0.10), `CONCEPT_EXPANSION_TOP_K` (5),
  `SUFFICIENCY_MIN_SCORE` (0.35), `SUFFICIENCY_STRONG_SCORE` (0.75),
  `SUFFICIENCY_SECONDARY_FLOOR` (0.20), `SUFFICIENCY_MIN_SUPPORTING_HITS`
  (2), `RETRIEVAL_LATENCY_TARGET_MS` (2000 -- DRR Section 5's first
  concrete, testable latency target in this codebase).
- **`apps/api/app/models/answer.py`** -- new columns: `provenance`,
  `sufficiency_score`, `retrieval_confidence`, `sufficiency_reason`.
  `status` values renamed `NO_EVIDENCE` -> `INSUFFICIENT` for consistency
  with the new provenance model.
- **`apps/api/app/models/workspace.py`** -- new column:
  `allow_external_fallback` (`NOT NULL DEFAULT False`).
- **`apps/api/app/models/citation.py`** -- docstring updated: no longer
  describes itself as dormant/unmigrated.
- **`apps/api/alembic/versions/0006_retrieval_provenance.py`** -- new.
  Creates `conversations`, `messages`, `answers`, `citations` for the
  first time (dormant since Milestone 4 -- see `0001_baseline_schema.py`'s
  own docstring) and alters `workspaces` to add
  `allow_external_fallback`.
- **`apps/api/app/schemas/chat.py`** -- `CreateMessageRequest` gained
  `useExternalFallback: bool = False`. `AnswerOut` gained `provenance`,
  `sufficiencyScore`, `retrievalConfidence`, `canOfferExternalFallback`.
- **`apps/api/app/api/v1/routes/chat.py`** -- passes the new
  `use_external_fallback`/`allow_external_fallback` arguments through to
  `answer_question()`; persists the four new `Answer` columns; builds the
  extended `AnswerOut`.
- **`apps/api/app/api/v1/router.py`** -- `chat.router` mounted for the
  first time.
- **Frontend**: `apps/web/lib/api.ts` -- `AnswerOut`/`Provenance` types
  updated; `sendMessage` takes `useExternalFallback`; chat endpoints moved
  from "not mounted yet" to "live". `apps/web/app/chat/page.tsx` -- moved
  out of `app/_future/` (deleted there); added exactly the three approved
  UI elements (a provenance badge with confidence, shown per assistant
  message; an external-fallback confirmation button shown only when
  `status === "INSUFFICIENT"` and `canOfferExternalFallback` is true) with
  no other layout changes. `apps/web/components/Sidebar.tsx` -- "AI Chat"
  nav item restored. `apps/web/app/documents/page.tsx` and
  `apps/web/app/documents/[id]/page.tsx` -- "arrives in Milestone 4"
  placeholders replaced with real links to `/chat`. `apps/web/app/_future/README.md`
  -- updated; nothing remains dormant under `_future/`.
- **`docs/adr/0015-retrieval-provenance.md`** -- new, documents the
  ranking formula, the sufficiency formula, the provenance state machine,
  the external-fallback consent mechanism, and the chunk-identity
  reconciliation in full.
- **Tests** (all new except the un-skipped file): `tests/test_sufficiency.py`
  (pure unit tests against `compute_sufficiency()` -- no DB, no HTTP);
  `tests/test_retrieval_service.py` (monkeypatched vector repo/concept
  lookup, pinning the exact chunk-identity reconciliation and boost
  behavior deterministically); `tests/test_chat_citations.py` (un-skipped
  -- `chat.router` is mounted now; extended with the FR-10 adversarial
  test, explicit-consent and workspace-setting external-fallback tests,
  and a HYBRID-provenance test, alongside the original three citation/
  workspace-isolation tests updated for the new response fields);
  `tests/test_cross_content_type_retrieval.py` (DRR Section 14 -- a
  corpus with one PDF, one code file, and one video-transcript resource,
  confirming citations aren't structurally biased toward a single content
  type). `tests/test_alembic_migrations.py`'s `EXPECTED_TABLES` and a new
  `EXPECTED_WORKSPACE_COLUMNS` updated.

## What did NOT change

Extraction, chunking, embedding generation, classification, and the
concept graph itself (Milestones 4-7) are untouched. ADR-0003's "dense
retrieval only, no reranker" and ADR-0004's "zero-config provider
fallback" both remain in force -- this milestone extends the ranking
formula and the provider interface, it does not replace either decision.
Milestone 9's Intent Workflows (Explain/Compare/Summarize/Search) are out
of scope; this milestone ships the single underlying retrieval/answer
contract those workflows will share.

## Pre-verification implementation audit

Before running the verification loop, this milestone's implementation was
audited against ADR-0003/ADR-0004/ADR-0015 and the Vision/PRD/Architecture/
Roadmap/DRR. The audit found no architectural blockers -- retrieval stayed
dense-only with additive ranking (ADR-0003 intact), providers stayed
zero-config-first (ADR-0004 intact), provenance stayed structurally
required, and the chunk-identity reconciliation ADR-0015 depends on was
implemented correctly. It did find six real issues, all fixed:

1. **Duplicated cosine-similarity logic.** `services/vector_repo.py` already
   had a private `_cosine()`; the new concept-expansion-only candidate path
   in `retrieval_service.py` reimplemented an identical function rather
   than reusing it. Fixed: `vector_repo.py`'s helper was made public
   (`cosine_similarity()`, with a docstring explaining why it's shared) and
   `retrieval_service.py` now imports it instead of duplicating it.
   (A third, independent cosine implementation exists in
   `services/concept_linking.py` -- pre-existing, frozen Milestone 7 code,
   deliberately left untouched per this project's own precedent of not
   retroactively modifying already-frozen milestones, e.g. MILESTONE_7.md's
   decision to leave a pre-existing `I001` lint finding alone.)
2. **Sufficiency corroboration counted raw candidate hits, not distinct
   resources.** `compute_sufficiency()`'s docstring described "several
   independent resources agreeing" as the corroboration signal, but the
   implementation counted any candidates clearing the secondary floor --
   so two chunks from the *same* document could satisfy
   `SUFFICIENCY_MIN_SUPPORTING_HITS` even though that's one source, not
   two. Fixed: corroboration now counts distinct `resource_id`s clearing
   the floor. Three tests updated/added in `test_sufficiency.py` to cover
   both the cross-resource case (sufficient) and the same-resource case
   (still penalized).
3. **Inconsistent status-constant usage.** `api/v1/routes/chat.py` filtered
   on the string literal `"READY"` where `retrieval_service.py` (and every
   other route) uses the `ResourceStatus.READY` constant. Fixed to use the
   constant, for consistency with the rest of the codebase.
4. **`RETRIEVAL_LATENCY_TARGET_MS` was documented as "used by tests" but no
   test asserted it**, so DRR Section 5's "first concrete, testable
   latency target" wasn't actually being tested. Fixed: added
   `test_local_answer_retrieval_latency_is_under_the_documented_target`,
   with an explicit docstring caveat that a single request is a floor
   sanity check, not a statistical P95 measurement (a real P95 harness is
   out of this milestone's scope).
5. **Two undocumented design assumptions**, now written down explicitly in
   code comments rather than left implicit: (a) `sufficiency_score` and
   `retrieval_confidence` are deliberately the same number today (kept as
   two fields, not collapsed, since they answer conceptually different
   questions that happen to share one formula under "don't duplicate
   confidence calculations elsewhere"); (b) `metadata_match_boost` is
   deliberately subject-only -- `content_category_confirmed` is excluded
   because a fixed enum label has no natural token-overlap semantics with
   a free-text question, unlike `subject`.
6. **`Workspace.allow_external_fallback` has no API or UI exposure yet** --
   noted explicitly in the model's own comment. This is intentional (the
   approved design scoped the UI to exactly three additions, none of which
   was a settings toggle), not an oversight, but worth being explicit about
   so a future milestone doesn't have to rediscover it.
7. **DRR Section 16 ("log the sufficiency score and matched evidence
   alongside every answer's provenance label") was only half-implemented.**
   The four values were persisted on the `Answer` row, but never actually
   logged -- `services/ingestion_service.py` already establishes a real
   `logging.getLogger(__name__)` precedent in this codebase for exactly
   this kind of claim (`classification_failed`, `concept_linking_failed`,
   `ingestion_ready`), and `retrieval_service.py` wasn't following it.
   Fixed: added one `logger.info("retrieval_answer workspace_id=%s
   provenance=%s sufficiency_score=%.3f reason=%s citations=%d", ...)`
   call at each of the three points a provenance decision is made (LOCAL/
   HYBRID, EXTERNAL, and no-answer-given), matching the existing logging
   style exactly.

No changes were made to already-frozen Milestones 1-7, to the Vision/PRD/
Architecture/Roadmap/DRR, or to ADR-0003/ADR-0004. All seven fixes are
confined to Milestone 8's own files.

## Issues found and fixed during verification

1. **Ruff: 7 findings in this milestone's own files** -- 6 `E501`
   (overlong lines in `app/models/answer.py`, `app/services/retrieval_service.py`,
   `tests/test_chat_citations.py`, `tests/test_cross_content_type_retrieval.py`
   (x2), `tests/test_retrieval_service.py`, `tests/test_sufficiency.py`) and
   1 `F841` (an unused `body` variable left over in
   `test_local_answer_retrieval_latency_is_under_the_documented_target`
   after the test was rewritten to read the answer back from the database
   instead). All fixed by wrapping lines and removing the unused
   assignment.
2. **A real test bug**: `test_external_fallback_requires_explicit_consent`
   asserted the substring `"requires a configured AI provider"`, but
   `ExtractiveFallbackProvider.answer_general_knowledge()`'s actual message
   reads "General-knowledge **answers require** a configured AI provider"
   (correct subject-verb agreement for the plural subject "answers") --
   the test had the wrong verb form. Fixed the test to match the real
   (correct) message; the message itself was never wrong.
3. **Pre-existing, frozen-file lint/format findings, left untouched per
   established precedent** (see MILESTONE_7.md's identical decision on a
   pre-existing `I001`): `alembic/env.py` and `alembic/versions/0001`-`0005`
   all still carry the same `I001` import-order finding every prior
   milestone's verification loop has already accepted; the new
   `0006_retrieval_provenance.py` carries the identical `I001` by design,
   for consistency with that chain. `alembic/versions/0002_resource_content_model.py`
   also still carries its 6 pre-existing `E501` findings from Milestone 4.
   Additionally, this verification pass is the first time `black --check`
   was run since those `E501`s were introduced, and it reports
   `0002_resource_content_model.py` would also be reformatted -- this is
   pre-existing drift in already-frozen Milestone 4 code, not caused by
   any Milestone 8 change (Milestone 8 never touched this file), and is
   left untouched for the same reason.
4. **Local environment note, not a code issue**: `pip install -r requirements.txt`
   failed with `PermissionError` / "Application Control policy has blocked
   this file" -- a Windows endpoint-security policy on this machine
   blocking execution inside the venv, unrelated to this milestone (no new
   Python dependencies were added -- see the ADR and this document's
   "Implemented" section). The existing venv already had everything
   needed, confirmed by `alembic`/`ruff`/`black`/`pytest` all running
   successfully immediately afterward.

One additional round-trip was needed after the first fix pass: my manual
line-wrap of `tests/test_cross_content_type_retrieval.py`'s overlong lines
satisfied Ruff's `E501` but didn't exactly match Black's own formatting
preference. Rather than guess Black's formatting a second time, `black`
was run directly (not `--check`) against exactly the 6 files this
milestone touched -- it reformatted only `test_cross_content_type_retrieval.py`
and left the other 5 unchanged, confirming those were already correct.
This is the safer way to reconcile Ruff and Black on wrapped lines: let
Black itself apply its formatting rather than hand-replicate it.

No other issues were found. Docker Compose build, up, health checks
(`/health`, `/health/ready`, frontend `/`), and teardown all passed on the
first run, against real Postgres and Qdrant.

## Verification results

1. **Dependencies**: no new Python or npm packages required this
   milestone (confirmed -- see note above).
2. **`alembic upgrade head`**: ran clean against local SQLite;
   `0005_concept_graph -> 0006_retrieval_provenance` applied with no
   errors. Also confirmed clean against real PostgreSQL via Docker Compose.
3. **`pytest`**: **144 passed, 3 skipped, 0 failed** (final run, after the
   test-assertion fix above).
4. **Ruff**: clean except the pre-existing, already-frozen `I001` findings
   in `alembic/env.py` and every migration `0001`-`0006` (the new `0006`
   carries the identical finding by design, for chain consistency) plus
   `0002_resource_content_model.py`'s 6 pre-existing `E501`s -- 13 total,
   all pre-existing/frozen, none in this milestone's own application code.
5. **Black**: clean except `alembic/versions/0002_resource_content_model.py`
   -- pre-existing drift in already-frozen Milestone 4 code, first surfaced
   by this milestone's verification pass but not caused by it (confirmed:
   this file was never touched), left untouched per the same precedent as
   its Ruff findings.
6. **Frontend build**: `next build` compiled and type-checked successfully;
   `/chat` (5.13 kB) generated alongside every other route with no errors.
7. **Docker Compose build**: both `api` and `web` images built
   successfully.
8. **Docker Compose up**: all four containers (`postgres`, `qdrant`, `api`,
   `web`) started; `postgres` and `api` reported healthy. API logs confirm
   migration `0006_retrieval_provenance` applied against the real Postgres
   volume on container start.
9. **API health + frontend**: `GET /health/ready` returned
   `{"status":"ready","components":{"database":{"status":"up",...},"vector_db":{"status":"up",...}}}`;
   `GET /` on the frontend returned the expected rendered HTML. `GET /health`
   confirmed 200 OK via the API container logs (both the Docker healthcheck
   and an external request).
10. **`docker compose down`**: tore down cleanly, all four containers and
    the network removed.
