# ADR-0007: Local filesystem storage behind a narrow adapter interface

**Status:** Accepted (MVP)

**Decision:** Original PDFs are written to a local Docker volume through a
`LocalStorage` class exposing `save`, `read`, `path_for`, and `delete`. Every
caller (upload, ingestion, file download, delete) goes through this
interface rather than touching the filesystem directly.

**Alternatives considered:** S3-compatible storage (AWS S3 or MinIO) is the
production-correct answer in the full enterprise SRS and requires no code
changes to adopt later — only a new adapter behind the same interface.

**Why this wins for 2 days:** zero extra infrastructure, trivially backed
up as a Docker volume, and sufficient for the demo corpus. The Source
Viewer's PDF file route reads through this same adapter, so switching
backends is confined to one file.

**MVP impact:** no pre-signed URLs; the Source Viewer's `/documents/{id}/file`
route is authorized the same way as every other document route and relies
on the browser sending the same-site auth cookie for the embedded iframe.

**Revisit when:** deploying outside a single Docker host, or when multiple
API replicas need to share uploaded files (Phase 2 — S3/MinIO adapter).
