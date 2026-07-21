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
| `models/conversation.py`, `models/answer.py`, `models/citation.py` | 4 -- RAG Chat | No |
| `services/embeddings.py` (`embed_one` on a query), `services/vector_repo.py` (`search`), `services/llm.py`, `services/retrieval_service.py` | 4 -- RAG Chat | No |
| `schemas/chat.py`, `api/v1/routes/chat.py` | 4 -- RAG Chat | No |
| `api/v1/router.py` | 2/3 (live) / 4 (aggregates the above) | **Yes, partially** -- imports `auth`, `workspace`, and `documents`; `chat` is intentionally left out (see comment in that file) because it transitively imports `app.services.llm`, not wired until Milestone 4 |

Note on `services/embeddings.py` and `services/vector_repo.py`: both files
are shared between Milestone 3 and Milestone 4, not duplicated. Milestone
3 only calls the *write* side of each (`embed()` on chunks at ingest time,
`upsert()`/`delete_by_document()` on the vector store); the *read* side
(`embed_one()` on a user's question, `search()` against the vector store)
is exercised only by `services/retrieval_service.py`, which is not
imported by anything yet. This is why documents.py could be mounted in
Milestone 3 without pulling in any Milestone 4 behavior -- the split was
already at the function level before this milestone started, not
something this milestone had to introduce.

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

Two consequences of the remaining dormant modules (Milestone 4 only, now)
are worth being explicit about:

1. **Runtime dependencies stay minimal on purpose.** `requirements.txt`
   installs Milestone 1 + 2 + 3 dependencies only. `app/services/llm.py`
   and `app/api/v1/routes/chat.py` will raise `ModuleNotFoundError` or
   `ImportError` if imported today if they need a package not yet
   declared -- that is intentional, not a bug, and is exactly what "the
   Docker image contains only this milestone's runtime dependencies"
   means in practice. Their dependencies move into `requirements.txt` in
   the same commit that mounts their router.
2. **`app/core/config.py` is the one exception to "only declare what's
   used."** Settings fields for later milestones (embedding/LLM provider,
   OpenAI keys, etc.) are already declared with safe defaults, grouped by
   milestone in that file. This is deliberate: a dormant module finding a
   missing settings *field* is a silent landmine (`AttributeError` the
   moment it's reactivated); a dormant module finding a missing *package*
   is loud and expected (`ModuleNotFoundError`, fixed by installing it
   alongside mounting the router). Declaring a config field costs nothing
   and isn't "implementing" the feature it belongs to.

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
imported the old `Document` model -- including the still-dormant
`services/retrieval_service.py` and `api/v1/routes/chat.py` -- was updated
to import `Resource` instead, so the "Mounted in app.main today?" column
above stays accurate without any dormant module also being a landmine
against a model that no longer exists.

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
