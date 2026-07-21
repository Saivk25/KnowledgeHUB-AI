# KnowledgeHub AI

**Your Organization's Intelligence, Instantly Searchable.**

> **Status: Milestone 3 -- Document Upload & Ingestion.** This README
> describes only what exists right now. RAG chat with citations is
> specified in the frozen SRS and will be built in the milestone that
> follows, after review. See [Roadmap](#roadmap) below.

## What this milestone proves

A real, working ingestion pipeline: upload a PDF into your own workspace,
watch it move from `QUEUED` through extraction and indexing to `READY`,
and have its text genuinely chunked, embedded, and stored in Qdrant --
scoped to your workspace and nobody else's -- on top of the Milestone 2
authentication foundation. Nothing in this milestone reads that index
back yet; that's Milestone 4.

## What's included

- Monorepo layout (`apps/api`, `apps/web`)
- FastAPI backend: CORS (`GET`/`POST`/`PATCH`/`DELETE`, credentials
  enabled for the session cookie), structured logging, generic error
  handling, liveness/readiness endpoints
- Authentication + workspace (Milestone 2, unchanged): register, login,
  logout, profile, workspace rename -- all still live and tested
- Document upload & ingestion (this milestone):
  - `POST /api/v1/documents` -- accepts a PDF, returns immediately with
    `status: "QUEUED"`; validates file type, size (`MAX_UPLOAD_MB`,
    default 25), and rejects empty files or exact duplicate re-uploads
    (by content checksum) within the same workspace
  - Ingestion runs as a FastAPI `BackgroundTask` (ADR-0005):
    **extract** (PyMuPDF native text layer) -> **chunk** (page-aware,
    ~500-token chunks with overlap, so every chunk still maps to exactly
    one page) -> **embed** (pluggable provider, defaults to a
    zero-config local hashing embedder; swaps to OpenAI's embeddings API
    by setting `OPENAI_API_KEY` and `EMBEDDING_PROVIDER=openai`) ->
    **index** (upsert into Qdrant, payload-filtered by `workspace_id`)
  - `GET /api/v1/documents` (list), `GET /api/v1/documents/{id}` (detail
    + processing-job status), `GET /api/v1/documents/{id}/file`
    (download the original PDF), `DELETE /api/v1/documents/{id}`
    (removes DB rows, vector points, and the stored file),
    `POST /api/v1/documents/{id}/retry` (only for `FAILED` documents)
  - Document metadata (filename, status, page count, size, checksum,
    error message) lives in PostgreSQL; extracted page text and chunks
    live in their own tables (`document_pages`, `document_chunks`) so
    Milestone 4's retrieval path can query them directly
  - Scanned/image-only PDFs (no extractable text) fail fast with a clear
    `SCANNED_PDF_UNSUPPORTED` error rather than silently indexing nothing
    (ADR-0006 -- no OCR in this MVP)
  - Next.js: a documents library (search, status chips, delete), an
    upload screen (drag-and-drop, client-side validation), and a detail
    screen that polls and shows live ingestion progress
- All document endpoints have explicit Pydantic `response_model`s and
  OpenAPI `summary`/`description`s, matching Milestone 2's pattern
- Docker Compose: added a named `api_storage` volume so uploaded files
  survive `docker compose down`/rebuilds, same as `postgres_data`/
  `qdrant_data` already do
- CI: unchanged commands (`pytest`, `ruff`, `black --check`,
  `tsc --noEmit`, `next build`) now exercise the ingestion pipeline too

## What's deliberately not included yet

No retrieval, no chat, no citations, no LLM question answering -- see
Milestone 4. `app/api/v1/router.py` mounts `auth`, `workspace`, and
`documents`, but not `chat`; the corresponding Next.js chat screen still
sits in `app/_future/` (see
[`apps/web/app/_future/README.md`](apps/web/app/_future/README.md)).
`app/services/embeddings.py` and `app/services/vector_repo.py` are
already shared with Milestone 4 (see
[`apps/api/app/README.md`](apps/api/app/README.md)), but only their
*write* paths (embed a chunk, upsert/delete a vector) are exercised this
milestone -- their *read* paths (embed a question, search the vector
store) belong to `app/services/retrieval_service.py`, which nothing
imports yet. This split was already at the function level before this
milestone started, which is exactly what makes Milestone 4 "consume
without architectural changes" possible.

## Security posture for this milestone

Everything from Milestone 2's security posture still holds (password
hashing, session cookie flags, validation-error redaction, workspace
isolation, no hardcoded secrets, no debug flags, minimal runtime
dependencies -- see `docs/` history for the full list). New this
milestone:

- Every document route resolves "whose document" strictly from the
  authenticated session's workspace (no cross-workspace id guessing is
  possible); a document that doesn't exist or belongs to another
  workspace returns the same 404 `DOCUMENT_NOT_FOUND` either way.
- Upload validates content type, size, and non-emptiness before anything
  touches disk or the database. `MAX_UPLOAD_MB` is enforced server-side,
  not just as a client-side UI hint.
- `workspaces.owner_user_id` was already indexed (Milestone 2 audit);
  this milestone adds an index on `documents.checksum` for the same
  reason -- duplicate-detection runs a `(workspace_id, checksum)`
  lookup on every upload.
- PyMuPDF's wheel bundles MuPDF statically; empirically verified to need
  no extra OS packages in the `python:3.11-slim` runtime image for text
  extraction, so none were added (kept the "runtime images stay
  dependency-minimal" property from the Milestone 1 audit).
- `httpx` (imported directly by `app/services/embeddings.py` for the
  optional OpenAI provider) is now declared explicitly in
  `requirements.txt` rather than relied upon as a transitive dependency
  of `qdrant-client`.

## Running it locally

### Docker Compose (recommended)

```bash
cd knowledgehub-ai
docker compose up --build
```

- Web: http://localhost:3000
- API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Liveness: http://localhost:8000/health
- Readiness: http://localhost:8000/health/ready

No `.env` file is required to run the Docker Compose stack locally.

### Running services individually

```bash
# Backend
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
# Falls back to SQLite automatically if DATABASE_URL is unset -- see
# app/core/config.py. Qdrant reachability will show as "down" in
# /health/ready unless a Qdrant instance is actually running -- ingestion
# still works in that case, falling back to an in-memory vector store
# (see app/services/vector_repo.get_vector_repository).

# Frontend (separate terminal)
cd apps/web
npm install
npm run dev
```

## Manual test cases

1. `docker compose up --build`, then open http://localhost:3000, register
   an account, and land on `/workspace`.
2. Go to Documents -> Upload a PDF. The upload returns immediately and the
   document shows as processing; within a few seconds it reaches
   **Ready** with a real page count.
3. Open the ready document's detail page -- it shows the page count and a
   note that asking questions about it arrives in Milestone 4 (no dead
   link to a chat screen that doesn't exist yet).
4. Try uploading the exact same PDF again -- rejected with 409
   `DUPLICATE_DOCUMENT`. Try uploading a `.txt` file -- rejected with 422
   `UNSUPPORTED_FILE_TYPE`. Try uploading an empty file -- rejected with
   422 `EMPTY_FILE`.
5. Upload a PDF with no extractable text (e.g. export a blank page to
   PDF) -- it reaches **Failed** with a clear "appears to be a scanned
   image" message, not a silent empty index. Click "Retry Processing" --
   it fails again the same way, deterministically.
6. Delete a document from the library -- it disappears from the list
   immediately; re-uploading the same file afterward succeeds (no longer
   a duplicate).
7. Register a second, separate account and confirm it cannot see, open,
   download, or delete the first account's documents (404 either way).
8. `curl http://localhost:8000/health` and `/health/ready` still behave
   exactly as in Milestone 1/2 (see those milestones' test cases).
9. Visiting a not-yet-built route (e.g. http://localhost:3000/chat or
   http://localhost:8000/api/v1/conversations) still returns a 404,
   confirming Milestone 4 is not silently half-available.

## Testing

```bash
cd apps/api
pip install -r requirements-dev.txt
pytest -q      # 36 passed, 3 skipped (deferred to Milestone 4)
ruff check app tests
black --check app tests
```

```bash
cd apps/web
npm install
npx tsc --noEmit
npm run build
```

## Assumptions

- Ingestion runs as an in-process FastAPI `BackgroundTask`, not a
  separate worker queue (ADR-0005). If the API process crashes mid-job,
  that document's `IngestionJob` row is left `RUNNING` and the document
  stays `PROCESSING` forever until manually retried or cleaned up --
  acceptable for local/demo use, not yet a production guarantee.
- No OCR: PDFs with no extractable text layer fail with
  `SCANNED_PDF_UNSUPPORTED` rather than being processed (ADR-0006).
- The zero-config default embedding provider (`LocalHashEmbeddingProvider`)
  is lexical (hashed bag-of-words), not deep-semantic -- it rewards
  vocabulary overlap between a query and a chunk, which is sufficient for
  the seeded demo corpus and this milestone's scope (there is no query
  path yet to evaluate retrieval quality against). Swapping to
  `EMBEDDING_PROVIDER=openai` is a config change, not a code change.
- Uploaded files are stored on local disk (`STORAGE_DIR`, ADR-0007)
  inside a named Docker volume (`api_storage`) so they survive container
  rebuilds; they are not yet backed by S3 or any object store.
- `GET /workspace` still does not return a `stats` field -- see
  `apps/api/app/README.md` for why that's a deliberate scope choice, not
  an oversight.
- Schema changes still use `Base.metadata.create_all` rather than Alembic
  migrations (ADR-0008); acceptable while there's no production data yet
  to migrate around.

## Repository layout

```
knowledgehub-ai/
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── README.md                  # module -> milestone map
│   │   │   ├── api/routes/health.py        # Milestone 1 -- live
│   │   │   ├── api/v1/routes/auth.py       # Milestone 2 -- live
│   │   │   ├── api/v1/routes/workspace.py  # Milestone 2 -- live
│   │   │   ├── api/v1/routes/documents.py  # Milestone 3 -- live
│   │   │   ├── api/v1/routes/chat.py       # Milestone 4 -- not mounted
│   │   │   ├── services/storage.py, extraction.py, chunking.py,
│   │   │   │   ingestion_service.py        # Milestone 3 -- live
│   │   │   ├── services/embeddings.py, vector_repo.py  # write path:
│   │   │   │   Milestone 3 -- live; read path: Milestone 4 -- not used
│   │   │   ├── services/llm.py, retrieval_service.py    # Milestone 4
│   │   │   ├── core/, db/, models/, schemas/
│   │   │   └── main.py
│   │   └── tests/
│   └── web/
│       ├── app/
│       │   ├── page.tsx, layout.tsx        # Milestone 1 -- live
│       │   ├── login/, register/, workspace/, settings/  # Milestone 2
│       │   ├── documents/                  # Milestone 3 -- live
│       │   └── _future/chat/               # Milestone 4 -- not routed
│       ├── components/, lib/
├── docs/
│   ├── adr/            # architecture decision records
│   └── architecture/
├── demo-data/           # sample PDFs prepared for the ingestion milestone
├── docker-compose.yml
└── .github/workflows/ci.yml
```

## Roadmap

| Milestone | Scope | Status |
|---|---|---|
| 1 | Project foundation: monorepo, Docker Compose, Postgres, Qdrant, health checks | Frozen (`v0.1.0-foundation`) |
| 2 | Authentication + workspace | Frozen (`v0.2.0-authentication`) |
| 3 | Document upload + ingestion pipeline | **Current** |
| 4 | RAG chat with page-level citations | Not started |
| 5 | Source Viewer + UX polish | Not started |
| 6 | Portfolio release: seed data, docs, demo | Not started |

Detailed architecture decisions for the whole system (already reviewed and
frozen in the SRS) live in [`docs/adr/`](docs/adr/) -- they describe where
the project is going even though most of that code isn't wired in yet.

## License

MIT -- see [LICENSE](LICENSE).
