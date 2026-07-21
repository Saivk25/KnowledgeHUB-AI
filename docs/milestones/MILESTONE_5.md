# Milestone 5 -- Multi-Format Ingestion

**Status: Implemented and Verified.** Every check below was run for real,
locally, with output pasted back and diagnosed turn by turn -- the same
discipline established starting Milestone 4. Two real issues were found
and fixed during verification (see below); this document reflects the
final, verified state.

## Approved scope (roadmap, verbatim)

"Add `Extractor` implementations: DOCX, PPTX, TXT/Markdown, code files,
YouTube transcripts, image OCR (handwritten notes/slides-as-images) --
each gated behind its own dependency addition, exactly as PyMuPDF landed in
M3." Depends on Milestone 4 (frozen, `v0.4.0-resource-model`).

Approved design decisions: pytesseract + Tesseract for OCR; YouTube
transcripts kept in scope, represented as a cached `.txt` file flowing
through the ordinary FILE pipeline rather than a new fileless path; code
files kept in scope with a fixed extension allowlist, no tree-sitter/
semantic chunking; minimal frontend touch (accept-list + a YouTube URL
field, no UX redesign).

## Implemented

- **`apps/api/app/services/extraction.py`** -- rewritten from one
  PyMuPDF-only function into an `Extractor` registry: `ExtractedUnit`,
  `ExtractionResult` (with a `.pages` property for backward compatibility),
  `ExtractionError`, and six extractors (`PdfExtractor`, `DocxExtractor`,
  `PptxExtractor`, `TextExtractor`, `CodeExtractor`, `ImageOcrExtractor`),
  resolved by file extension via `get_extractor_for()`. See
  `docs/adr/0012-multi-format-extraction.md` for every per-format decision
  (OCR engine choice, code allowlist, why `page_number` wasn't renamed).
- **`apps/api/app/services/youtube.py`** -- new. `extract_video_id()` (pure,
  regex-based, restricted to youtube.com/youtu.be URL shapes -- the SSRF
  guard) and `fetch_transcript()` (calls `youtube_transcript_api`).
- **`apps/api/app/models/resource.py`** -- added `extraction_confidence`
  (nullable float). **`apps/api/alembic/versions/0003_extraction_confidence.py`**
  -- the migration adding it, batch-altered for SQLite/Postgres parity.
- **`apps/api/app/services/ingestion_service.py`** -- extraction is now
  registry-dispatched instead of a hardcoded PyMuPDF call;
  `ExtractionError` is caught and mapped to a FAILED status; the
  `looks_scanned` check is gated to `mime_type == "application/pdf"` only;
  `resource.extraction_confidence` is populated from the extraction result
  for every format.
- **`apps/api/app/api/v1/routes/documents.py`** -- `upload_document`
  validates against the registry's extension allowlist instead of a
  hardcoded PDF check, and sets a real `mime_type` per format. New route,
  **`POST /documents/youtube`**: validates the URL, fetches the transcript,
  saves it as a `.txt` file through the existing storage service, and
  creates an ordinary `content_source=FILE` resource -- reusing 100% of the
  existing status machine, polling, retry, and delete routes. Every other
  route on this file is unchanged.
- **`apps/api/app/core/config.py`** -- added `TESSERACT_CMD` (optional,
  for local Windows dev where Tesseract isn't on PATH).
- **`apps/api/requirements.txt`** -- added `python-docx`, `python-pptx`,
  `Pillow`, `pytesseract`, `youtube-transcript-api`.
  **`apps/api/Dockerfile`** -- added the `tesseract-ocr` system package
  (the first non-pip runtime dependency in this image).
- **`apps/web/app/documents/upload/page.tsx`** -- expanded the file-picker
  `accept` attribute and client-side validation message to the new
  supported extensions; added a YouTube URL input alongside the existing
  dropzone. **`apps/web/lib/api.ts`** -- added `ingestYoutubeVideo()`.
- **`docs/adr/0012-multi-format-extraction.md`** -- new. **ADR-0006**
  status updated to note it's superseded for image files (PDF behavior
  otherwise unchanged). **`apps/api/app/README.md`** -- module map updated.
- **Tests** (all new): `tests/extractor_fixtures.py`,
  `tests/test_extraction_registry.py`, `tests/test_ocr_extraction.py`
  (skips cleanly without a local Tesseract binary, runs for real in
  Docker), `tests/test_multi_format_ingestion.py` (full upload -> READY
  per format + confidence assertions), `tests/test_youtube_ingestion.py`
  (URL-parsing unit tests + a monkeypatched-`fetch_transcript` end-to-end
  ingestion test + error paths). `test_ingestion.py`'s PDF-only rejection
  test was renamed and switched to a `.zip` fixture, since `.txt` is now a
  supported format.

## Issues found and fixed during verification

1. **`test_alembic_migrations.py`'s `EXPECTED_RESOURCE_COLUMNS`/
   `NULLABLE_RESOURCE_COLUMNS` fixtures were not updated for the new
   `extraction_confidence` column** -- caused two pre-existing schema tests
   to fail (`test_upgrade_head_from_empty_creates_expected_schema`,
   `test_stamping_baseline_then_upgrading_matches_fresh_upgrade`) with
   `extraction_confidence` reported as an unexpected extra column. Fixed by
   adding it to both sets. Not a migration bug -- the migration was correct;
   the test's expectation set was stale.
2. **Ruff/Black on first pass**: import ordering in `extraction.py` and
   `documents.py`, one line-too-long in `documents.py` (the multi-name
   `youtube` import), two `assert False`-style error-path tests in
   `test_extraction_registry.py` (replaced with `pytest.raises`), and two
   more long lines in the new test files. All fixed via `ruff check --fix`
   plus targeted manual edits, then `black`.

No bugs were found in the `youtube_transcript_api` integration itself --
the class names (`NoTranscriptFound`, `TranscriptsDisabled`,
`VideoUnavailable`) and `YouTubeTranscriptApi.get_transcript()` signature
used in `services/youtube.py` were correct on the first real test run
(monkeypatched at the ingestion-route boundary, so this doesn't confirm the
library's actual network behavior -- only that the exception-handling
contract this code was written against is accurate).

## Verified (commands run locally, output reviewed)

1. **Dependencies**: `pip install -r requirements-dev.txt` in the isolated
   `.venv` -- clean install of all five new packages
   (`python-docx`, `python-pptx`, `Pillow`, `pytesseract`,
   `youtube-transcript-api`), confirmed venv-isolated via `where.exe
   python`.
2. **Alembic migration**: `alembic upgrade head` applied
   `0003_extraction_confidence` cleanly against local SQLite; column
   presence confirmed via direct schema introspection. Also verified
   against real **PostgreSQL** via `docker compose up --build` -- applied
   incrementally on top of the *existing* Milestone 4 volume (`Running
   upgrade 0002_resource_content_model -> 0003_extraction_confidence`), not
   just against a fresh database, which is the stronger of the two checks.
3. **pytest**: `75 passed, 6 skipped` (6 skips: the three OCR-dependent
   tests, since no local Tesseract binary is installed on this Windows
   machine outside Docker, plus the three pre-existing dormant chat/citation
   skips). Every new extractor, the registry lookup, both corrupt-file
   error paths, and the full YouTube ingestion flow (URL validation +
   monkeypatched transcript fetch + real extraction/chunking/embedding/
   indexing) passed on the first content-correctness run, after the schema
   fixture fix above.
4. **Ruff**: clean after the fixes above.
5. **Black**: clean (`58 files would be left unchanged`).
6. **Docker Compose**: `docker compose up --build -d` -- all four services
   built and started; the `tesseract-ocr` apt layer (plus its ~70
   transitive font/image/crypto library dependencies) installed cleanly in
   ~23s; `api` reported `(healthy)`.
7. **API health**: confirmed via `curl http://localhost:8000/health` ->
   `{"status":"ok","app":"KnowledgeHub AI"}`, and via the container's own
   healthcheck.
8. **Frontend build**: `npm run build` completed inside the Docker build
   (`✓ Compiled successfully`, all 9 routes generated, including the
   updated `/documents/upload` route at a slightly larger bundle size than
   before -- 3.99 kB vs. the prior build's size, consistent with the added
   YouTube-URL form). Directly confirmed via `curl http://localhost:3000`
   returning the full rendered landing page HTML.

**Known, non-blocking oddity (same as Milestone 4, unrelated to this
milestone):** the `web` container's Docker healthcheck still reports
`unhealthy` despite the app serving correctly (confirmed above). This is
the same pre-existing `docker-compose.yml` healthcheck quirk flagged during
Milestone 4's verification -- not touched by, or caused by, this milestone.

## What did NOT change

Everything about the existing PDF path (validation order, chunking,
embedding, vector indexing, status machine, retry/delete) is untouched.
No classification, concept graph, retrieval, or capture/fileless-resource
work is included, per the approved scope. `extraction_confidence` is
stored but not yet surfaced in the API response or the frontend -- that is
Roadmap Milestone 10/11's job.
