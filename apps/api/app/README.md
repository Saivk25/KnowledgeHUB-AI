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

Note on `workspace.py`: `GET /workspace` still does not return a `stats`
field (document ready/processing/failed counts). The `Document` model now
exists (as of this milestone), so the `OperationalError` that blocked this
in Milestone 2 no longer applies -- it remains unimplemented because no
consumer needs a server-computed aggregate yet: the Documents page calls
`GET /documents` and computes its own counts client-side. Add a real
`stats` field to this endpoint only when a future milestone actually needs
it computed server-side.

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
