# ADR-0011: `Resource` replaces `Document` (nullable storage fields,
content_source discriminator, text-hash dedup)

**Status:** Accepted (Milestone 4)

**Decision:** `app/models/document.py`'s `Document` / `DocumentStatus` /
`DocumentPage` / `DocumentChunk` are renamed to `Resource` /
`ResourceStatus` / `ResourcePage` / `ResourceChunk`
(`app/models/resource.py`), with three additions:

1. `content_source` discriminator (`ResourceContentSource.FILE | CAPTURE`).
2. `filename`, `storage_key`, `mime_type`, `size_bytes`, `checksum` become
   nullable (previously `NOT NULL`).
3. New `text_hash` column: sha256 of the resource's extracted/captured
   text, for content-level (not byte-level) deduplication.

This is a rename-and-extend of the existing entity, not a new entity
alongside it. `documents` becomes `resources` at the table level (see
ADR-0010 / migration `0002_resource_content_model`); every reference across
the codebase (routes, ingestion, the dormant retrieval/chat modules) was
updated to match.

**Why rename instead of adding a second, parallel entity:** the Design
Readiness Review's own wording was the direct input here: *"sequence the
roadmap so the Resource schema migration happens before new file types land
(avoids migrating the data model twice)."* "Avoids migrating twice" only
makes sense if `Resource` and `Document` are the same entity at different
points in time -- if they were parallel entities, there would be nothing to
migrate, just a new table to add. Product Philosophy #2 (*"Resources should
simply contribute evidence to concepts... think through whether the current
architecture can naturally evolve toward this without replacing the
Resource model"*) reinforces this: `Resource` is meant to be the one
standing entity that future file types and capture sources all become
instances of, not a second concept.

**Why nullable columns instead of two subclasses / a separate
`CapturedResource` table:** Product Philosophy #4 (*"Capture must be as
important as Retrieval... quick note, pasted text, screenshot, copied code,
browser article, URL, voice note, image"*) describes several fileless
content sources arriving in later milestones. All of them share every other
`Resource` field (workspace, status, page_count, chunks, text_hash) and
differ only in "is there a file backing this." A discriminator + nullable
columns on one table keeps every downstream consumer (ingestion, retrieval,
chunk/citation relationships) working against a single `Resource` type
regardless of source, rather than needing to branch on which table/subtype
it is. Joined-table inheritance was considered and rejected for the MVP: it
would add a second table and a join to every query for a distinction
(file-backed vs. not) that, so far, only matters at ingestion time.

**Why nullability is enforced at the application layer, not a CHECK
constraint:** matches this codebase's existing style of keeping cross-field
invariants in Python (see e.g. the workspace tenant-boundary comment in
`models/workspace.py`) rather than SQL. The upload route
(`api/v1/routes/documents.py`) is the only place that constructs a
`content_source=FILE` resource today, and it always sets all five storage
fields together -- there is exactly one code path to keep honest, so a DB
constraint would add enforcement surface without a second writer to guard
against yet.

**Why `text_hash` doesn't reject duplicates (yet):** the DRR's Milestone 4
scope is schema + Alembic. Turning "these two resources have the same
text_hash" into a rejected upload (or a merge, or a suggested-duplicate UI
affordance) is a product decision -- what should happen differs depending
on whether the duplicate is exact re-ingestion, a re-exported file, or two
independent captures of the same idea (see Product Philosophy #2's "one
evolving knowledge object" framing, which argues for merging evidence, not
rejecting it). This milestone populates the signal
(`services/ingestion_service.py` computes it right after extraction) so
whichever future milestone makes that product decision does not also need
a backfill migration for historical data computed on the fly at read time.

**What did NOT change:** the `/documents` API prefix, `DocumentOut` /
`DocumentListOut` / `DocumentDetailOut` schema names and fields, and every
Milestone 3 error code (`DOCUMENT_NOT_FOUND`, `DUPLICATE_DOCUMENT`,
`DOCUMENT_NOT_FAILED`, `UNSUPPORTED_FILE_TYPE`, etc.) are unchanged. Those
are the frozen Milestone 3 API contract; Milestone 4's approved scope is the
data model underneath it, not the wire contract on top of it.

**Alternatives considered:** leaving `Document` in place and adding a
separate `CapturedResource`/`Note` table for fileless content once that
milestone arrives. Rejected per the DRR's explicit "avoids migrating the
data model twice" framing above -- that alternative is precisely the
double-migration this ADR exists to avoid.

**Revisit when:** a future milestone actually implements a CAPTURE ingestion
path (pasted text, URL fetch, etc.) and needs to decide what "duplicate
text_hash" means as a product behavior; and when a file type beyond PDF is
added (DOCX, images, etc.), which should not require another schema
migration for `Resource` itself -- only new extraction logic feeding the
same model.
