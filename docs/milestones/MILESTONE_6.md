# Milestone 6 -- Metadata, Classification & Confidence

**Status: Implemented and Verified.** Every check below was run for real,
on the local machine, with output pasted back and diagnosed turn by turn.
Two issues were found and fixed during verification (see below) -- this
document reflects the final, verified state, not the first draft.

## Approved scope (roadmap, verbatim)

"Auto-classification (source type disambiguation, subject/topic
suggestion) with stored confidence scores; manual-correction UI and API;
extraction-confidence surfaced for OCR'd content." Depends on Milestone 5
(frozen, `v0.5.0-multi-format-ingestion`).

Approved design decisions: fixed 7-category taxonomy (not configurable this
milestone); classifier failure degrades gracefully (resource still reaches
READY, category=OTHER, confidence=0.0) rather than failing the resource;
library-list category badge included; automatic classification keeps
running after a user correction and its output is preserved separately
(`auto_*` columns) rather than being permanently locked out -- only the
authoritative, user-facing fields stop following it once confirmed.

## Implemented

- **`apps/api/app/models/resource.py`** -- new `ResourceContentCategory`
  taxonomy (`LECTURE`, `ASSIGNMENT`, `QUESTION_PAPER`, `LAB_MANUAL`,
  `RESEARCH_PAPER`, `PERSONAL_NOTE`, `OTHER`). Ten new nullable columns:
  authoritative `content_category`/`subject` (+ confidences +
  `_confirmed` bools) and `auto_content_category`/`auto_subject` (+
  confidences, always overwritten by the latest automatic run). See the
  fields' own inline comments and
  `docs/adr/0013-classification-confidence.md`.
- **`apps/api/alembic/versions/0004_classification_metadata.py`** -- the
  migration adding all ten columns + an index on `content_category`.
- **`apps/api/app/services/classification.py`** -- new. `Classifier`
  (ABC), `Classification` (dataclass), `LocalHeuristicClassifier`
  (weighted keyword/phrase rules per category, a documented deterministic
  confidence formula, deliberately no subject guessing), `OpenAIClassifier`
  (one chat-completion call, JSON response, confidence = the model's own
  reported number), `get_classifier()` (auto-selects OpenAI only when
  `CLASSIFICATION_PROVIDER=openai` and `OPENAI_API_KEY` are both set,
  mirroring `embeddings.py`/`llm.py` exactly).
- **`apps/api/app/models/ingestion_job.py`** -- new `IngestionStep.CLASSIFYING`,
  between `EXTRACTING` and `INDEXING`.
- **`apps/api/app/services/ingestion_service.py`** -- runs classification
  after extraction; `_apply_classification()` writes `auto_*` fields
  unconditionally and authoritative fields only when not `_confirmed`.
  Classifier exceptions are caught, logged, and substituted with
  `Classification(category=OTHER, category_confidence=0.0)` -- the
  resource still reaches READY.
- **`apps/api/app/api/v1/routes/documents.py`** -- `_to_out()` now
  surfaces `extractionConfidence` (M5 field, exposed here for the first
  time) and all six classification fields. New route,
  **`PATCH /documents/{id}/classification`**: validates at least one field
  is present (422 `EMPTY_UPDATE`), validates `contentCategory` against the
  fixed taxonomy (422 `INVALID_CATEGORY`), sets `confidence=1.0` and
  `confirmed=True` for whichever field(s) are provided.
- **`apps/api/app/schemas/document.py`** -- `DocumentOut` extended;
  new `ClassificationUpdateRequest`.
- **`apps/api/app/core/config.py`** -- new `CLASSIFICATION_PROVIDER`
  setting (`local` | `openai`, default `local`).
- **`apps/api/app/models/__init__.py`** -- exports
  `ResourceContentCategory`.
- **Frontend**: `apps/web/lib/api.ts` -- `DocumentOut` extended,
  `ContentCategory` type, `updateClassification()`.
  `apps/web/components/CategoryBadge.tsx` -- new, mirrors
  `StatusBadge.tsx`'s pattern exactly.
  `apps/web/app/documents/page.tsx` -- new Category column in the library
  table.
  `apps/web/app/documents/[id]/page.tsx` -- `CLASSIFYING` added to the
  progress steps; a new classification section on `READY` documents
  (category badge, confidence, subject, extraction-confidence badge when
  below 100%, and an inline edit form calling the new PATCH route).
- **`docs/adr/0013-classification-confidence.md`** -- new, documents every
  decision above including the two-layer `auto_*`/authoritative design.
  **`apps/api/app/README.md`** -- module map updated with a written
  confidence-definitions note (per DRR Section 9).
- **Tests** (all new): `tests/test_classification.py` (one test per
  category's rule set, confidence-formula determinism and monotonicity,
  no-signal fallback, registry default), `tests/test_classification_ingestion.py`
  (end-to-end category/auto-field population, correction API behavior,
  confirmed-value-survives-reclassification via a monkeypatched classifier,
  graceful-degradation-on-classifier-failure, PATCH validation errors,
  auth/workspace isolation). `tests/test_alembic_migrations.py`'s expected
  column sets were updated proactively this time (a lesson from Milestone
  5, where this same fixture update was missed on the first pass).

## How this milestone was verified

1. **No new runtime dependencies.** Classification uses only `httpx`
   (already a dependency) and stdlib `re`/`json` -- confirmed no
   `pip install` was required; the existing `.venv` ran everything below
   unchanged.
2. **`alembic upgrade head`** -- run against local SQLite first: migration
   `0004_classification_metadata` applied cleanly on top of `0003`. A
   follow-up python one-liner introspecting the resulting schema confirmed
   all ten new columns (`content_category`, `content_category_confidence`,
   `content_category_confirmed`, `subject`, `subject_confidence`,
   `subject_confirmed`, `auto_content_category`,
   `auto_content_category_confidence`, `auto_subject`,
   `auto_subject_confidence`) plus the `ix_resources_content_category`
   index were present. Later re-confirmed against real PostgreSQL via
   `docker compose up --build` (see point 5).
3. **`pytest -q`** -- first run: 94 passed, 6 skipped (the 6 skips are the
   pre-existing OpenAI-provider tests that only run with a real API key,
   unchanged from Milestones 3/5). All 11 `test_classification.py` cases
   and all 9 `test_classification_ingestion.py` cases passed on the first
   try -- the hand-computed confidence-formula constants and keyword-rule
   weights matched the fixtures' wording as designed, no off-by-a-little
   failures.
4. **Ruff / Black** -- `ruff check app tests` found 3 errors (E501
   line-too-long): the confidence formula in `classification.py` and two
   long test-function signatures in `test_classification_ingestion.py`.
   Fixed by extracting a `confidence_range` local variable and wrapping the
   test signatures across multiple lines. `black --check app tests` flagged
   4 files needing reformatting (`resource.py`, `ingestion_service.py`,
   `classification.py`, `test_classification_ingestion.py`); ran `black app
   tests` to apply, then re-ran `pytest -q` to confirm no behavior change
   (94 passed, 6 skipped, unchanged). Final `ruff check` / `black --check`
   both clean.
5. **Docker Compose build** -- `docker compose up --build -d`: image build
   succeeded (the `tesseract-ocr` apt layer cached from Milestone 5), all
   four services started (`postgres` healthy, `qdrant` started, `api`
   healthy, `web` health: starting), migration log showed `Running upgrade
   0003_extraction_confidence -> 0004_classification_metadata, Milestone 6:
   add classification & confidence metadata to Resource` applied cleanly
   against the real Postgres volume. Frontend build output showed updated
   route bundle sizes reflecting the new classification UI code
   (`/documents` 4.18 kB, `/documents/[id]` 4.47 kB, `/documents/upload`
   4.01 kB) -- `next build` type-checked the new state/section/table-column
   changes with no errors.
6. **API health + frontend serving** -- `curl http://localhost:8000/health`
   returned `{"status":"ok","app":"KnowledgeHub AI"}`. `curl
   http://localhost:3000` returned the rendered homepage HTML (the frozen
   Milestone 2 landing page -- unaffected by this milestone, confirming no
   regression). `docker compose down` cleanly removed all four containers
   and the network.

## Issues found and fixed during verification

- Two Ruff E501 (line-too-long) errors and four files needing Black
  reformatting, listed in point 4 above. No logic changes -- purely
  formatting/line-length fixes, confirmed by an unchanged pytest result
  before and after.

## What did NOT change

Extraction, chunking, embedding, and vector indexing are untouched --
classification is a new, independent stage inserted between extraction and
chunking, not a modification of either. No concept graph, no retrieval, no
capture/fileless-resource work, no active-learning use of corrections
beyond storing them. The category taxonomy is fixed and not
user-configurable, per the approved design.
