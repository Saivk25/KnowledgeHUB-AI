# Milestone 7 -- Concept Graph

**Status: Implemented and Verified.** Every item below was run for real
against this repository -- local SQLite test suite, Ruff/Black, and a full
Docker Compose build/up against real Postgres and Qdrant -- with output
reviewed and, where issues surfaced, fixed and re-verified before this
milestone was committed and tagged.

## Approved scope (verbatim from the Roadmap, plus DRR/Vision v2 refinements)

"concepts/resource_concepts/concept_relationships schema; incremental
concept-linking on ingestion; browse-by-concept UI; this is the
'continuously improving understanding' requirement." Plus DRR Section 11's
two critical fixes (concept deduplication/entity-resolution, cycle-safe
graph traversal) and Product Vision v2 Sections 2/5's two MVP-classified
refinements (typed/asymmetric relationships; an evidence link enriched
with `contribution_type`, not just a confidence score).

Approved design decisions: scope boundary excludes concept synthesis,
auto-generated concept pages, Knowledge Timeline, Personal Learning Layer,
Proactive AI, graph visualization, and a dedicated graph database. Local
concept linker reuses Milestone 6's `subject`/`content_category` fields,
no new NLP dependency. Concept vectors reuse the existing Qdrant
deployment via a second collection. Three-zone deduplication
(auto-merge / possible-duplicate flag / new concept), never a silent
ambiguous-zone merge. Every relationship and every evidence link requires
a real evidence chunk pointer -- no exceptions. `CONCEPT_LINKING` runs
after `INDEXING`, before `DONE`; failure never fails the resource; retried
via the existing `/retry` route. Remain on `BackgroundTask` this
milestone, with the re-evaluation documented in an ADR. Merge is one-way;
the merged-from concept is preserved, not restorable. No concept is ever
left without an evidence link -- one that loses its last link is marked
`UNUSED`, never silently dangling or hard-deleted.

## Implemented

- **`apps/api/app/models/concept.py`** -- new. `ConceptStatus`
  (`ACTIVE`/`MERGED`/`UNUSED`), `ContributionType`
  (`DEFINES`/`APPLIES`/`TESTS`/`EXTENDS`/`MENTIONS`), `RelationshipType`
  (`RELATED_TO` + six directed types, `recurs_in` deliberately excluded --
  see the model's docstring), `normalize_concept_name()`, and three
  models: `Concept`, `ResourceConcept` (the evidence link, required
  `evidence_chunk_id`), `ConceptRelationship` (typed directed edge,
  required `evidence_chunk_id`).
- **`apps/api/alembic/versions/0005_concept_graph.py`** -- migration
  creating `concepts`, `resource_concepts`, `concept_relationships` and
  their indexes. No existing table's columns changed.
- **`apps/api/app/models/resource.py`** -- new `concept_links` cascade
  relationship, mirroring `pages`/`chunks`/`jobs`.
- **`apps/api/app/models/ingestion_job.py`** -- new
  `IngestionStep.CONCEPT_LINKING`, between `INDEXING` and `DONE`.
- **`apps/api/app/core/config.py`** -- new settings:
  `CONCEPT_LINKER_PROVIDER`, `QDRANT_CONCEPT_COLLECTION`,
  `SIMILARITY_MERGE_THRESHOLD` (0.85), `POSSIBLE_DUPLICATE_THRESHOLD`
  (0.65), `MAX_TRAVERSAL_DEPTH` (5).
- **`apps/api/app/services/vector_repo.py`** -- `VectorPoint` gained an
  optional `concept_id` field (other fields gained defaults);
  `VectorRepository` gained `delete_by_concept`; new
  `get_concept_vector_repository()` reusing the same Qdrant deployment
  via a second collection.
- **`apps/api/app/services/concept_linking.py`** -- new. `ConceptLinker`
  (ABC), `LocalConceptLinker` (reuses `subject`/`content_category`; falls
  back to a filename-derived name when `subject` is null -- discovered
  during implementation to be necessary, see "Design refinement" below;
  never proposes relationships), `OpenAIConceptLinker`
  (retrieval-grounded, every id it returns validated against what it was
  actually shown), `get_concept_linker()`.
- **`apps/api/app/services/concept_graph.py`** -- new. `resolve_concept()`
  (three-zone dedup), `find_nearby_concepts()` (grounding context for the
  OpenAI linker), `merge_concepts()` (the manual-merge escape hatch),
  `recompute_concept_usage()` (orphan-prevention), `traverse_concept_graph()`
  (the one shared, cycle-safe traversal helper -- application-level BFS
  with a visited-node set + independent max-depth bound).
- **`apps/api/app/services/ingestion_service.py`** -- new
  `CONCEPT_LINKING` stage (`_link_concepts`, `_upsert_relationship`).
  Same graceful-degradation rule as classification: a failure is logged,
  never fails the resource. Evidence links are replaced (not appended) on
  every run for retry-idempotency; relationships are deduplicated at
  write time instead.
- **`apps/api/app/schemas/concept.py`**, **`apps/api/app/api/v1/routes/concepts.py`**
  -- new. `GET /concepts`, `GET /concepts/{id}`, `GET /concepts/{id}/related`,
  `POST /concepts/{id}/merge`. Mounted in `api/v1/router.py`. Read/merge
  only -- concepts are only ever created by the ingestion pipeline.
- **`apps/api/app/schemas/document.py`**, **`apps/api/app/api/v1/routes/documents.py`**
  -- `DocumentDetailOut` gained a `concepts` field; `delete_document` now
  collects affected concept ids before its cascade delete and runs the
  orphan-prevention check afterward.
- **`docs/adr/0014-concept-graph.md`** -- new, documents every decision
  above including the two-threshold dedup design, the evidence-required
  rule, the traversal-safety design, and the BackgroundTask re-evaluation.
  **`apps/api/app/README.md`** -- module map updated.
- **Frontend**: `apps/web/lib/api.ts` -- new types + `listConcepts`/
  `getConceptDetail`/`getRelatedConcepts`/`mergeConcept`; `DocumentDetailOut`
  extended with `concepts`. `apps/web/app/concepts/page.tsx` -- new list
  page. `apps/web/app/concepts/[id]/page.tsx` -- new detail page (evidence,
  one-hop related concepts, a bare merge affordance for flagged possible
  duplicates). `apps/web/components/Sidebar.tsx` -- new "Concepts" nav
  item. `apps/web/app/documents/[id]/page.tsx` -- `CONCEPT_LINKING` added
  to the progress steps; a new minimal Concepts section on `READY`
  documents.
- **Tests** (all new): `tests/test_concept_graph_models.py`,
  `tests/test_concept_deduplication.py` (the DRR-mandated dedup suite --
  exact match, similarity match via the real `LocalHashEmbeddingProvider`,
  the possible-duplicate zone, workspace isolation, manual merge),
  `tests/test_concept_graph_traversal.py` (the DRR-mandated cycle-safety
  suite -- a real A→B→A cycle terminates correctly, max-depth capping,
  correct multi-hop neighbors), `tests/test_concept_linking_ingestion.py`
  (end-to-end: filename-fallback concept creation, dedup across two real
  uploads, graceful degradation on linker failure, the orphan-prevention
  rule after resource deletion, that the local linker never fabricates a
  relationship), `tests/test_concepts_api.py` (list/detail/related/merge,
  workspace isolation, auth). `tests/test_alembic_migrations.py`'s
  `EXPECTED_TABLES` updated proactively.

## Design refinement discovered during implementation

`LocalHeuristicClassifier` (Milestone 6) deliberately never sets
`subject` -- it's an honest "no real signal" restraint documented in that
classifier's own code. Building `LocalConceptLinker` strictly against
"reuse `subject`" as originally approved would therefore mean a fully
zero-config deployment (both provider settings left at their `local`
defaults, with no `OPENAI_API_KEY`) never creates a single concept --
silently contradicting this codebase's established "zero-config golden
path" precedent that every prior milestone has upheld. Fix: when
`subject` is `None`, the local linker falls back to a name derived from
the resource's own filename (strip extension, replace separators with
spaces, title-case) -- plain string manipulation, not NLP, so it remains
within the approved "no new NLP dependency" constraint -- at a flat,
honest, deliberately low confidence (`_FILENAME_FALLBACK_CONFIDENCE =
0.3`). Documented in `docs/adr/0014-concept-graph.md`'s sub-decision 2b
and called out here so it's visible before this milestone is verified,
not buried in a diff.

## Issues found and fixed during verification

1. **Test-data flaw in `test_manual_merge_repoints_evidence_and_marks_source_merged`.**
   The test originally resolved two concepts named "Concept A" and
   "Concept B". `LocalHashEmbeddingProvider`'s tokenizer drops
   single-character tokens (`len(t) > 1`), so both names reduced to the
   single token `"concept"` -- identical embeddings, cosine similarity
   1.0 -- and `resolve_concept` correctly (per its own dedup logic)
   resolved "Concept B" to the same concept as "Concept A" instead of
   creating a second one, so the test's premise (merging two distinct
   concepts) never held. This was a real bug caught by the local-first
   verification loop, not a mock or an assumption -- `resolve_concept`
   and `merge_concepts` themselves were correct throughout. Fixed by
   renaming the two fixture concepts to genuinely unrelated names
   ("Merge Source Concept" / "Unrelated Target Subject") that share no
   tokens.
2. **Lint (Ruff): two `B011` (`assert False, ...`) findings** in
   `test_merge_into_self_is_rejected` and
   `test_merge_across_workspaces_is_rejected` -- replaced with
   `pytest.raises(concept_graph.ConceptMergeError)`, the idiomatic form.
3. **Lint (Ruff): one `E501`** (an overlong test-function signature) in
   `test_concept_linking_ingestion.py` -- wrapped across lines.
4. **Lint (Ruff): one `E501` and one `I001`** in the new
   `0005_concept_graph.py` migration -- the long `merged_into_concept_id`
   column definition was wrapped across lines. The `I001` (import order)
   finding was deliberately left as-is: it is the exact same pattern
   already present, unmodified, in every prior migration file
   (`alembic/env.py`, `0001`-`0004`), all of which were already frozen
   with it -- fixing it only in `0005` would make this file
   inconsistent with the rest of the chain instead of matching an
   established (if imperfect) convention.
5. **Black**: 7 files needed reformatting (`app/models/concept.py`,
   `app/models/resource.py`, `app/services/concept_graph.py`,
   `app/services/concept_linking.py`, `app/services/ingestion_service.py`,
   `tests/test_concept_graph_models.py`,
   `tests/test_concept_deduplication.py`) -- all whitespace-only,
   applied directly.

No other issues were found. `resolve_concept`, `merge_concepts`,
`recompute_concept_usage`, `traverse_concept_graph`, the ingestion
integration, and the API routes all passed on the first real run.

## Verification results

1. **Dependencies**: unchanged this milestone (concept linking uses only
   `httpx`, already present, and stdlib `re`/`json`) -- confirmed no new
   install was required.
2. **`alembic upgrade head`**: ran clean against both a fresh local
   SQLite database and, separately, a real PostgreSQL 16 instance via
   Docker Compose. Log confirms `0004_classification_metadata ->
   0005_concept_graph` applied with no errors in either environment.
3. **`pytest`**: **123 passed, 6 skipped** (final run, after the fixes
   above). The dedup-threshold tests (exact match, similarity-match via
   the real `LocalHashEmbeddingProvider`, the possible-duplicate zone,
   workspace isolation) and the cycle-safe-traversal tests (a real
   A->B->A cycle, max-depth capping, multi-hop neighbors) all passed
   against real embeddings and a real BFS traversal -- no mocks.
4. **Ruff / Black**: clean except for the pre-existing, already-frozen
   `I001`/`E501` findings in `alembic/env.py` and migrations
   `0001`-`0004` (12 total, none new, none in this milestone's
   application code) -- confirmed identical before and after this
   milestone's changes.
5. **Docker Compose build**: both `api` and `web` images built
   successfully; `next build` compiled and type-checked the two new
   concept pages, the new nav item, and the new document-detail section
   with no errors (`web` build output confirms `/concepts` and
   `/concepts/[id]` routes were generated).
6. **Docker Compose up**: all four containers (`postgres`, `qdrant`,
   `api`, `web`) started and reported healthy; API logs confirm
   migration `0005_concept_graph` applied against the real Postgres
   volume on container start.
7. **API health + frontend**: `GET /health` returned
   `{"status":"ok","app":"KnowledgeHub AI"}`; `GET /` on the frontend
   returned the expected rendered HTML.
8. **`docker compose down`**: tore down cleanly, all four containers and
   the network removed.

## What did NOT change

Extraction, chunking, embedding, classification, and chunk-level vector
indexing are untouched -- concept-linking is a new, independent stage
inserted after indexing, not a modification of any of them. No concept
synthesis/auto-summary, no Knowledge Timeline, no Personal Learning Layer,
no Proactive AI, no graph visualization, no dedicated graph database --
all explicitly out of this milestone's approved scope.
