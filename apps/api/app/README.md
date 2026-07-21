# apps/api/app -- module map

`app/main.py` mounts three routers right now: `app/api/routes/health.py`
(Milestone 1) and `app/api/v1/routes/auth.py` +
`app/api/v1/routes/workspace.py` (Milestone 2, via `app/api/v1/router.py`).
Everything else below exists in the repository because it was already
built and reviewed in an earlier pass, but is not imported by anything on
the live request path. This file exists so that is never ambiguous from a
directory listing alone.

| Path | Milestone that activates it | Mounted in app.main today? |
|---|---|---|
| `api/routes/health.py` | 1 -- Project Foundation | **Yes** |
| `core/config.py`, `main.py`, `db/` | 1 -- Project Foundation | **Yes** |
| `core/security.py` | 2 -- Authentication | **Yes** |
| `deps.py` | 2 -- Authentication | **Yes** |
| `models/user.py`, `models/workspace.py` | 2 -- Authentication | **Yes** |
| `schemas/auth.py` | 2 -- Authentication | **Yes** |
| `api/v1/routes/auth.py`, `api/v1/routes/workspace.py` | 2 -- Authentication | **Yes** |
| `models/document.py`, `models/ingestion_job.py` | 3 -- Document Ingestion | No |
| `services/storage.py`, `services/extraction.py`, `services/chunking.py`, `services/ingestion_service.py` | 3 -- Document Ingestion | No |
| `schemas/document.py`, `api/v1/routes/documents.py` | 3 -- Document Ingestion | No |
| `models/conversation.py`, `models/answer.py`, `models/citation.py` | 4 -- RAG Chat | No |
| `services/embeddings.py`, `services/llm.py`, `services/vector_repo.py`, `services/retrieval_service.py` | 4 -- RAG Chat | No |
| `schemas/chat.py`, `api/v1/routes/chat.py` | 4 -- RAG Chat | No |
| `api/v1/router.py` | 2 (live) / 3 / 4 (aggregates the above) | **Yes, partially** -- imports only `auth` and `workspace`; `documents` and `chat` are intentionally left out (see comment in that file) because they transitively `import fitz` / `import httpx`, neither installed yet |

Note on `workspace.py`: `GET /workspace` does not return a `stats` field
(document ready/processing/failed counts) yet. The original prototype
queried the `Document` model for those counts, but that model/table isn't
registered until Milestone 3 -- querying it now would raise
`OperationalError: no such table`. This was the smallest change needed to
reactivate the endpoint honestly for Milestone 2; `stats` returns once the
Document model exists.

Two consequences of the remaining dormant modules are worth being
explicit about:

1. **Runtime dependencies stay minimal on purpose.** `requirements.txt`
   installs Milestone 1 + Milestone 2 dependencies only. Modules in the
   table above that import `PyMuPDF` or `python-multipart` will raise
   `ModuleNotFoundError` if imported today -- that is intentional, not a
   bug, and is exactly what "the Docker image contains only this
   milestone's runtime dependencies" means in practice. Their dependencies
   move into `requirements.txt` in the same commit that mounts their
   router.
2. **`app/core/config.py` is the one exception to "only declare what's
   used."** Settings fields for later milestones (storage, embedding
   provider, etc.) are already declared with safe defaults, grouped by
   milestone in that file. This is deliberate: a dormant module finding a
   missing settings *field* is a silent landmine (`AttributeError` the
   moment it's reactivated); a dormant module finding a missing *package*
   is loud and expected (`ModuleNotFoundError`, fixed by installing it
   alongside mounting the router). Declaring a config field costs nothing
   and isn't "implementing" the feature it belongs to.

To activate a milestone: add its dependencies to `requirements.txt`,
mount its router(s) in `app/api/v1/router.py`, and move its tests out of
the skip/importorskip guard in `apps/api/tests/`.
