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
| `models/document.py`, `models/ingestion_job.py` | 3 -- Document Ingestion | **Yes** |
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
