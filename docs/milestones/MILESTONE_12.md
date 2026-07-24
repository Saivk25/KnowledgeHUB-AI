# Milestone 12: Production Hardening & Portfolio Polish

**Status: Implemented and Verified.** All nine implementation-plan steps
(Section 11) are complete, including both discovered-in-flight amendments
(Sections 12 and 13). See Section 14 for the final verification summary,
consolidated test results, and confirmation that no scope changes
occurred beyond what was explicitly approved.

This is the twelfth and final row of the original
`KnowledgeOS_Architecture_PRD_Roadmap.md` Section 8 roadmap table.
Milestone 12 concludes that plan as tabled. It does not introduce new
product surface, new intents, new entities, or any capability from
`KnowledgeOS_Product_Vision_v2.md` -- see Section 6 (Design decisions) and
Section 7 (Non-goals) for the two scope questions already resolved before
this draft was written.

---

## 1. Scope

Per `KnowledgeOS_Architecture_PRD_Roadmap.md` Section 8, Milestone 12 is:

> **Production Hardening & Portfolio Polish** -- Revisit BackgroundTask
> vs. queue decision under real concept-graph load, embedding-version
> migration tooling, seed data across all source types, full
> documentation, demo script.

Confirmed as the current, unedited scope statement in both the frozen
roadmap document and the as-shipped `README.md` roadmap table (`| 12 |
Production Hardening & Portfolio Polish | Queue re-evaluation, embedding
migrations, seed data, docs, demo | Not started |`) and its "What's
deliberately not built yet" bullet ("No production hardening pass --
queue-vs-BackgroundTask re-evaluation under real load, embedding-version
migration tooling, full seed data, demo script (M12)."). This design
treats that line as the literal, exhaustive scope -- five items, no more,
no less -- not as a springboard to infer additional work from.

## 2. Governing constraints reviewed

- **ADR-0005 (BackgroundTasks, not Celery/Temporal)** -- its own stated
  revisit trigger: "the product needs multi-instance workers, ingestion
  retries with backoff, or ingestion volume high enough to need
  independent scaling from the API (Phase 2)." Section 4.1 below applies
  this trigger literally, using this project's actual, current scale and
  usage pattern rather than a hypothetical one.
- **Architecture doc, Section 9, items 6-7** -- "Version embeddings...
  Build the re-embed-on-upgrade job as part of [this] milestone, not as
  an afterthought" and "Re-evaluate BackgroundTask vs. a real task queue
  at Milestone 7 (Concept Graph), not before. That is the first stage
  whose cost depends on the *existing* corpus size rather than just the
  new upload." Concept Graph (M7) has since shipped and is frozen
  (`v0.7.0-concept-graph`), which is what makes this milestone the
  correct point to actually perform that re-evaluation, per the
  Architecture doc's own sequencing logic.
- **DRR Section 15 (Failure Recovery)** -- ADR-0005's accepted limitation
  ("BackgroundTask crash loses the in-flight job") was scoped against a
  single linear four-stage pipeline; the pipeline has since grown to six
  stages (extract -> classify -> chunk -> embed -> index -> concept-link,
  confirmed in `app/models/ingestion_job.py`'s `IngestionStep` enum).
  DRR's recommended mitigation -- "extend the existing `IngestionJob.step`
  tracking to cover the new stages" -- was **already applied** in
  Milestones 6 and 7 (`CLASSIFYING`/`CONCEPT_LINKING` are both real,
  tracked steps today); what DRR flagged that remains genuinely
  unaddressed is the crash-recovery gap itself: a process crash mid-job
  still leaves the `IngestionJob` row `RUNNING` forever, with no
  detection or resumption mechanism. Section 4.1 scopes a narrow fix for
  exactly this, and only this.
- **DRR Section 17 (Deployment Strategy)** -- flagged a backup/restore gap
  for the three named Docker volumes. Per the approved Decision 1 (this
  milestone's preceding scope-resolution turn), this is **out of scope**
  for Milestone 12 -- documented as a future operational item only
  (Section 7).
- **`KnowledgeOS_Product_Vision_v2.md`** -- per the approved Decision 2,
  **no capability from this document** (Capture, Personal Learning Layer,
  typed concept relationships, Knowledge Timeline, Proactive AI, concept
  synthesis) is in scope for this milestone. Milestone 12 concludes the
  original roadmap table as tabled; Vision v2, if pursued at all, is a
  distinct future initiative requiring its own explicit approval and
  design pass.
- **Architecture doc risk #1 (Scope explosion)** -- the standing warning
  against a milestone doing more than one dimension of new work at once
  applies here in a different shape than usual: the risk for a hardening
  milestone isn't multiple new *features*, it's silently drifting from
  "harden what exists" into "add what's missing" (Vision v2 items,
  backup tooling, or a wholesale task-queue migration). Section 7's
  explicit non-goals list exists specifically to keep that boundary
  visible.
- **ADR-0002 (Qdrant)** -- its own revisit trigger ("corpus size or
  hybrid lexical retrieval requirements justify OpenSearch alongside
  Qdrant... or multi-region/managed Qdrant Cloud") is unrelated to and
  unaffected by this milestone; Section 4.2's embedding-version tagging
  extends Qdrant's existing payload mechanism, it does not touch this
  decision.
- **ADR-0009 (Docker Compose, not Kubernetes)** -- reconfirmed by DRR
  Section 17 with no action needed; still the deployment model this
  milestone designs against. Introducing a broker/worker service (were
  Section 4.1's evaluation to conclude one is needed, which it does not --
  see Section 4.1) would be exactly the kind of departure ADR-0009 and
  ADR-0005 both weigh against for a personal-scale system; not proposed
  here.
- **Testing/verification discipline** (real fixtures, full-suite
  regression, ruff/black/`tsc --noEmit` clean, additive-only backend
  changes, workspace isolation on anything new) carries forward
  unchanged from every prior milestone.

## 3. Confirmed implementation baseline (this pass)

| Area | Current state | Evidence |
|---|---|---|
| Ingestion execution | FastAPI `BackgroundTask`, single `api` container, single process; no worker/broker service in `docker-compose.yml` (4 services total: `postgres`, `qdrant`, `api`, `web`) | `docker-compose.yml`; `apps/api/requirements.txt` (no Celery/Redis/RQ dependency anywhere) |
| Per-stage job tracking | `IngestionStep`: `UPLOADED -> EXTRACTING -> CLASSIFYING -> INDEXING -> CONCEPT_LINKING -> DONE`/`FAILED`, all six stages tracked | `app/models/ingestion_job.py:9-29` |
| Crash recovery | None -- a crashed process leaves `IngestionJob.status == "RUNNING"` indefinitely; no reconciliation job, no stale-job detection | `app/services/ingestion_service.py:134` (`job.status = "RUNNING"`); ADR-0005's own "MVP impact" note, unchanged since Milestone 1 |
| Vector point versioning | Collection names carry a static `_v1` suffix (`document_chunks_v1`, `concept_vectors_v1`); no per-point version field | `app/core/config.py:40, 85`; `app/services/vector_repo.py:120-145` (payload indexes exist for `workspace_id`/`document_id`/`concept_id` only) |
| Embedding provider switching | `EMBEDDING_PROVIDER` (`local`/`openai`) is a static config value with no migration path; switching it does not re-embed existing points | `app/core/config.py:49`; confirmed no `embedding_model_version` string anywhere in `apps/api/app` or `apps/api/alembic` |
| Seed/demo data | Three PDF fixtures + a generator script; no DOCX/PPTX/TXT-MD/code/YouTube/image sample content | `demo-data/` (`Employee_Handbook_Excerpt.pdf`, `Expense_Policy.pdf`, `Vendor_Contract_Summary.pdf`, `generate_demo_pdfs.py`) |
| Documentation | README (Parts 1-2, roadmap table, module map), 18 ADRs, 11 milestone docs, CHANGELOG, CONTRIBUTING/SECURITY/CODE_OF_CONDUCT, architecture diagram -- all already built (largely during the Milestone 8-era portfolio pass) | `README.md`; `docs/adr/`; `docs/milestones/`; `CHANGELOG.md` |
| Screenshots | Spec written, zero images captured | `docs/assets/screenshots/README.md` ("None are checked in yet") |
| Demo script | Does not exist | No `DEMO_SCRIPT.md` or equivalent anywhere in the repository |
| Backup/restore | Does not exist; out of scope per Decision 1 | `docker-compose.yml:106-109` (three named volumes, no backup tooling referencing them) |

Every row above was confirmed directly against the live repository during
this design pass, not inferred from the roadmap text alone -- the same
discipline Milestone 11's audit-based design used.

## 4. Proposed design

### 4.1 BackgroundTask vs. production task queue -- evaluation and outcome

**Motivation:** Architecture doc Section 9, item 7 explicitly deferred
this re-evaluation to "Milestone 7 (Concept Graph), not before" -- concept
graph now exists and is the first ingestion stage whose cost scales with
the *existing* corpus, not just the new upload (Architecture Section 5).
Milestone 12, being the last roadmap slot, is the last point at which
this evaluation is scheduled to happen at all.

**Existing implementation:** Section 3 above. `_run_ingestion` (the
function backing `BackgroundTask`) is already framework-agnostic --
ADR-0005 notes it "takes a DB session and a document ID and returns
nothing," specifically so it could be called from a Celery task or
Temporal activity later without rewriting ingestion logic. That seam is
unchanged and still available if ever needed.

**Gap:** No actual measurement of concept-linking cost at this project's
real scale exists; the re-evaluation ADR-0005 and the Architecture doc
both call for has never been performed with real data, only anticipated.
Separately, and independently of whichever way that evaluation comes out,
DRR Section 15's crash-recovery gap (a crashed process leaves a job
`RUNNING` forever) remains unaddressed and has gotten more consequential
as the pipeline grew from four stages to six.

**Proposed change:** Perform the evaluation explicitly, against
ADR-0005's own stated trigger conditions, using this system's actual
profile:
- *Multi-instance workers* -- not needed; `docker-compose.yml` runs one
  `api` replica by design (ADR-0009), and nothing in this project's scope
  (a personal, single-user system per Vision v2's own Non-Goals) creates
  a driver for horizontal API scaling.
- *Ingestion retries with backoff* -- partially needed, but not for the
  reason a task queue would solve; the actual gap is crash *detection*,
  not retry *scheduling* (a resource stuck `RUNNING` isn't being retried
  incorrectly, it's never being retried at all).
- *Ingestion volume needing independent scaling from the API* --
  concept-linking's per-upload cost is bounded by `MAX_TRAVERSAL_DEPTH`
  and the existing ANN-based dedup lookup (DRR Section 3's recommended,
  already-implemented mitigation), not by an unbounded full-table scan;
  at personal-archive scale (Architecture Section 5: "thousands of
  resources," not enterprise volume) this has no demonstrated need for
  independent worker scaling.

None of ADR-0005's three trigger conditions is met. **Recommended
outcome: retain `BackgroundTask`; ADR-0005 reconfirmed, not superseded.**
In place of a queue migration, close the one concrete, scoped gap DRR
Section 15 actually identified: a lightweight stale-job reconciliation
check -- on API startup (and optionally on a periodic interval), find
`IngestionJob` rows `status == "RUNNING"` with a `started_at` older than a
configurable threshold, mark them `FAILED` with a distinct
`error_code` (e.g. `"INTERRUPTED"`), and rely on the existing, unchanged
retry/reextract endpoints (Milestone 3/11) for the user to resume them.
No new service, no new dependency, no change to `_run_ingestion` itself
or any pipeline stage's logic.

**Alternatives considered:**
- *Celery + Redis broker* -- ADR-0005's own originally-named alternative.
  Rejected for the same reason ADR-0005 rejected it initially and DRR
  Section 17/ADR-0009 continue to reaffirm: it adds an operated service
  (broker + worker process) for a benefit (independent scaling, task
  persistence across restarts) this system's real profile doesn't need,
  and directly contradicts the "no unnecessary framework replacement"
  constraint governing this milestone.
- *Temporal* -- same rejection as Celery, at even higher operational
  cost; ADR-0005 named this as the "enterprise-grade" option, and this
  remains explicitly a personal, not enterprise, system (Vision v2
  Non-Goals).
- *Do nothing* -- rejected because it leaves DRR Section 15's specific,
  concrete finding (indefinitely orphaned `RUNNING` jobs) unaddressed,
  which is the one part of this item that *is* squarely "hardening" and
  costs little to fix.

**Risks:** A reconciliation check running on every API startup adds a
small amount of startup-path logic to a previously trivial boot sequence
-- mitigated by keeping it a single, indexed, bounded query
(`WHERE status = 'RUNNING' AND started_at < :threshold`), not a full-table
scan, and by making it non-blocking to the health endpoint. Marking a job
`FAILED` on a false positive (a genuinely still-running job that's just
slow) is possible if the threshold is set too aggressively -- mitigated by
a generous, configurable default and by the fact that the existing
retry/reextract endpoints make recovery a one-click action either way.

**Acceptance criteria:** a written evaluation section (this one, refined
during implementation if real numbers change the picture) explicitly
addresses all three of ADR-0005's trigger conditions with a stated
outcome; if `BackgroundTask` is retained (the expected outcome), the
stale-job reconciliation check is implemented, additive, covered by a
test that simulates an orphaned `RUNNING` row and confirms it is marked
`FAILED` with the new error code and remains resumable via the existing
retry/reextract routes; zero changes to `_run_ingestion`'s internal stage
logic or to any existing ingestion test's expected behavior.

### 4.2 Embedding-version migration tooling

**Motivation:** Architecture doc Section 5 ("Embedding-model versioning...
requires re-embedding the entire corpus; this needs a documented
migration path... rather than a silent mismatch between old and new
vectors in the same collection") and Section 9 item 6 ("Version
embeddings. Tag every vector point with an `embedding_model_version`...
not as an afterthought when the first model upgrade is actually
needed"). No model upgrade has happened yet, which is exactly the
situation the Architecture doc says to build this ahead of, not in
reaction to.

**Existing implementation:** `EmbeddingProvider` registry
(`app/services/embeddings.py`, `local`/`openai`, selected via
`EMBEDDING_PROVIDER`); `VectorRepository`/`QdrantVectorRepository`
(`app/services/vector_repo.py`) writes to `QDRANT_COLLECTION`
(`document_chunks_v1`) and, since Milestone 7,
`QDRANT_CONCEPT_COLLECTION` (`concept_vectors_v1`) -- both collections
already have keyword-indexed payload fields for `workspace_id` and
`document_id` (and `concept_id` for the concept collection).

**Gap:** versioning exists only as a static string baked into the
collection *name*; there is no per-point payload field recording which
embedding model actually produced that point's vector, and no tooling to
detect or repair a mismatch. Switching `EMBEDDING_PROVIDER` today would
silently mix vectors from two different embedding spaces in the same
collection -- cosine similarity between them is meaningless, and nothing
in the system would surface that this happened.

**Proposed change:**
1. Add `embedding_model_version` (string, e.g. `"local-hash-v1"` or
   `"openai:text-embedding-3-small"`) to every vector point's payload at
   write time, in both collections -- purely additive to the existing
   write path in `vector_repo.py`, no new collection, no Postgres schema
   change.
2. Add a keyword index on `embedding_model_version` in both collections,
   mirroring the existing `workspace_id`/`document_id`/`concept_id`
   indexes (`vector_repo.py:135-144`).
3. A re-embed script/job: given a target version, find points whose
   stored `embedding_model_version` doesn't match the currently
   configured provider, regenerate their vectors through the existing
   `EmbeddingProvider.embed()` path, and upsert -- reusing the exact
   write path ingestion already uses, not a new one.
4. A visible, queryable version-distribution check (a script or a
   log-level report), so a mismatch after a provider change is at minimum
   *detectable*, not silent -- directly closing the specific risk named
   in Architecture Section 5.

**Alternatives considered:**
- *Wait until a real model upgrade is attempted* -- rejected; this is
  precisely the "afterthought" sequencing Architecture Section 9 item 6
  explicitly instructs against, and retrofitting a version tag onto
  points that were never tagged is strictly harder than tagging from the
  point this tooling ships.
- *A dedicated reindexing service/pipeline* -- rejected as unnecessary
  process/framework growth for a single-collection-pair, personal-scale
  system; violates "no unnecessary framework replacement."

**Risks:** Re-embedding every point in a collection is a real,
potentially slow bulk operation at larger corpus sizes -- mitigated by
designing the job as resumable/batchable (process N points at a time,
track progress, safe to re-run) rather than a single unbounded
transaction. A migration running against a live system could transiently
expose a mix of old/new-versioned points mid-run -- accepted and
documented as an operational note (consistent with DRR Section 15's
"acceptable at personal scale for now" framing for a related concern),
not solved with locking, since this system has no concurrent-writer
scenario that would make that unsafe.

**Acceptance criteria:** every vector point written from this milestone
forward (both collections) carries `embedding_model_version`; a
documented, tested re-embed procedure can migrate an existing
workspace's points to a new version and a test confirms old-versioned
points are fully replaced, not merely supplemented; a version-mismatch
after changing `EMBEDDING_PROVIDER` without running the migration is
detectable via the new check. No Alembic migration required -- this
entire item is a Qdrant payload/tooling change, not a Postgres schema
change.

### 4.3 Production-quality multi-format seed/demo data

**Motivation:** the system has supported seven source types since
Milestone 5 (PDF, DOCX, PPTX, TXT/Markdown, code, YouTube transcript,
image OCR), but `demo-data/` contains PDF fixtures only. Anyone following
the README's quick-start never sees classification, concept-linking, or
cross-format retrieval exercised on more than one format.
`docs/assets/screenshots/README.md` already specifies a "Documents
library" screenshot showing "a few resources of different types (PDF,
DOCX, code, YouTube)" -- multi-format seed data is a precondition for
that screenshot existing at all.

**Existing implementation:** `demo-data/generate_demo_pdfs.py` plus three
checked-in PDFs (`Employee_Handbook_Excerpt.pdf`, `Expense_Policy.pdf`,
`Vendor_Contract_Summary.pdf`). No other format has any sample content
anywhere in the repository.

**Gap:** no non-PDF seed content; no documented, repeatable seeding
procedure; no demonstration anywhere that the concept graph or
cross-format retrieval actually looks meaningful once populated.

**Proposed change:** extend `demo-data/` with one representative sample
per remaining source type -- a DOCX, a PPTX, a TXT/Markdown note, a small
code file, a YouTube URL reference, and a scanned/handwritten-style image
for OCR -- with content deliberately chosen to cross-reference the same
2-3 concepts the existing PDFs already touch, so concept-linking has
something real to connect. Pair this with a documented seeding script
that ingests every sample through the existing `POST /documents` (and
equivalent) upload path -- the real pipeline, exactly as a user would
trigger it -- rather than a database-level shortcut.

**Alternatives considered:**
- *Direct database insertion, bypassing `/documents`* -- rejected; this
  would not exercise real extraction/classification/chunking/
  embedding/concept-linking, defeating the point of seed data as an
  end-to-end proof the pipeline actually works.
- *LLM-generated synthetic content per format at seed time* -- rejected
  as unnecessary complexity and cost for what should be static, reviewed,
  checked-in fixtures, consistent with `generate_demo_pdfs.py`'s existing
  precedent of pre-baked files rather than runtime generation.

**Risks:** sample content needs deliberate cross-referencing to make the
concept graph demo meaningful, not just one file per format checked off a
list -- a content-design task, not just an engineering one. YouTube seed
data depends on a real, external, publicly available video URL this
project doesn't control -- needs a documented fallback if the reference
becomes unavailable (e.g. a short note on how to swap in a replacement
URL).

**Acceptance criteria:** `demo-data/` contains at least one sample for
every one of the seven supported source types; a single documented
command seeds a fresh workspace end to end through the real upload path;
after seeding, the concept graph shows at least one concept with evidence
from two or more different source types, and a Search/Explain query
demonstrably returns results spanning more than one format.

### 4.4 Documentation completion

**Motivation:** roadmap row 12 names "full documentation" as part of this
milestone's scope. Substantial documentation work already happened
during the Milestone 8-era portfolio pass (README badges/structure,
CONTRIBUTING, SECURITY, CODE_OF_CONDUCT, the architecture diagram), which
narrows what's genuinely left rather than requiring a fresh pass.

**Existing implementation:** README (Parts 1-2, roadmap table,
milestone-by-milestone repository layout), 18 ADRs, 11 `MILESTONE_N.md`
design/verification records, `CHANGELOG.md` with one entry per frozen
milestone, `apps/api/app/README.md`'s module map (updated every
milestone), CONTRIBUTING/SECURITY/CODE_OF_CONDUCT, and
`docs/architecture/system-architecture.md`.

**Gap:** exactly one concrete, already-named gap exists in the entire
repository: `docs/assets/screenshots/README.md` states plainly, "None are
checked in yet," and `README.md`'s own Screenshots section is a commented
placeholder. No other documentation gap was identified during this
design pass.

**Proposed change:** capture and check in the four screenshots already
specified in `docs/assets/screenshots/README.md` (documents library,
concept graph, chat with provenance, upload flow) once Section 4.3's seed
data makes a representative instance available to screenshot; uncomment
and wire the corresponding block in `README.md`'s Screenshots section.
This milestone's own `MILESTONE_12.md` (this document) and its eventual
ADR close the loop on this milestone's own documentation, consistent with
every prior milestone's practice.

**Alternatives considered:** a broader documentation restructure --
rejected; no structural documentation gap was identified by this pass or
by the DRR, and the existing README/ADR/milestone-doc discipline has held
up cleanly across 11 milestones without needing revision.

**Risks:** screenshots require an actual seeded, running instance --
sequencing dependency on Section 4.3 within this milestone, not a risk to
the wider system.

**Acceptance criteria:** all four screenshots named in
`docs/assets/screenshots/README.md` exist, meet its own size guidance
(under ~500KB each), and are visibly embedded in `README.md`.

### 4.5 Demo script / portfolio polish

**Motivation:** roadmap row 12 names "demo script" as its own explicit
item. No such artifact exists anywhere in the repository today.

**Existing implementation:** none, beyond the README's own quick-start
instructions (`docker compose up`, health check) -- which get the stack
running but don't walk through what the product actually does.

**Gap:** there is no scripted, followable walkthrough of the system's
capabilities -- multi-format ingestion, classification and correction,
concept-graph browsing, provenance-labeled answering, the study
workflows, or the Milestone 11 confidence/correction UX -- that a
recruiter, interviewer, or new contributor could follow end to end.

**Proposed change:** a single Markdown document, `docs/DEMO_SCRIPT.md` --
a step-by-step, copy-pasteable walkthrough that starts the stack, seeds
it using Section 4.3's demo data, and then walks through a deliberately
ordered sequence of actions exercising the project's actual
differentiators (ingest a PDF and a DOCX, see automatic classification,
correct a field and view its correction history, browse the resulting
concept graph, ask an Explain/Compare question and see the
provenance/citation/sufficiency-reason output, run a Quiz or Viva
session), stating the expected outcome at each step so a reader can
verify the system is behaving as documented rather than just clicking
around.

**Alternatives considered:**
- *A recorded video/GIF walkthrough* -- rejected as out of scope for this
  milestone; unlike every other artifact in this documentation-first
  project, a video can't be reviewed line-by-line the way a written
  script (or any prior design doc) can, and nothing in this milestone's
  scope calls for new tooling to produce/maintain one.
- *An automated end-to-end test suite standing in for a demo* -- rejected
  as conflating two different audiences (a human reading a script vs. CI
  verifying behavior), though the script's steps should reference
  already-tested, real behavior wherever possible rather than describe
  anything speculative.

**Risks:** a demo script can drift out of sync with the actual UI/API as
future milestones change things -- mitigated by keeping it deliberately
thin (pointing at existing documented endpoints/pages rather than
re-describing their behavior in detail) and treating it as a living
document updated alongside future changes, the same way `README.md`
already is.

**Acceptance criteria:** `docs/DEMO_SCRIPT.md` exists, walks a fresh
`docker compose up` instance through seeding and every major
differentiator listed above, and can be followed end to end by someone
unfamiliar with the codebase using only the script itself.

## 5. API, schema, and interaction summary

- **Database/schema changes:** none in Postgres. No new Alembic migration
  is required by any item in this design -- Section 4.1's stale-job check
  reads/writes existing `IngestionJob` columns only; Section 4.2's
  versioning lives entirely in Qdrant payloads.
- **API changes:** none required by Sections 4.1-4.3 as designed (the
  stale-job check runs at startup, not behind a new route; the re-embed
  and seeding tooling are scripts, not endpoints). If implementation
  finds a operator-facing trigger route genuinely useful (e.g. an
  admin-only `POST` to kick off re-embedding on demand rather than only a
  standalone script), that would be a new, additive route proposed during
  implementation, not assumed here.
- **Frontend changes:** none. This milestone touches no UI surface --
  consistent with "production hardening without feature expansion."
- **Interaction with existing systems:** Section 4.1 does not change
  `_run_ingestion`, any extractor, classifier, chunker, or concept-linker
  -- it only adds a startup-time reconciliation check reading
  `IngestionJob`. Section 4.2 does not change embedding computation
  itself (`EmbeddingProvider` implementations are untouched) -- only what
  gets stored alongside each point. Sections 4.3-4.5 touch no application
  code at all.

## 6. Design decisions

**1. Backup/restore -- DECIDED (prior turn): out of scope, deferred.**
Not designed, not implemented in this milestone. Documented in Section 7
as a future operational enhancement with its agreed revisit trigger:
revisit when the system moves from demo/portfolio use to genuine
sole-copy daily use of real personal data.

**2. Vision v2 capabilities -- DECIDED (prior turn): out of scope,
excluded.** Milestone 12 concludes the original 12-milestone architecture
roadmap exactly as tabled. No Capture, Personal Learning Layer, typed
concept relationships, Knowledge Timeline, Proactive AI, concept
synthesis, or any other Vision v2 item is included, per Section 7.

**3. BackgroundTask vs. task queue -- PROPOSED: retain BackgroundTask,
add a stale-job reconciliation check.** See Section 4.1's full evaluation
against ADR-0005's own trigger. This is the one item in this design that
is a genuine technical recommendation rather than an already-settled
scope boundary -- flagged here for your explicit approval alongside the
rest of this document, since it's the closest thing this milestone has to
an open architectural question.

**4. Embedding-version tag format -- PROPOSED: a single descriptive
string per point** (e.g. `"local-hash-v1"`, `"openai:text-embedding-3-small"`),
not a separate version-registry table. Simpler than a normalized lookup
table for what is, today, a two-provider system; consistent with how
`EMBEDDING_PROVIDER` itself is already just a string config value, not a
foreign-keyed table.

**5. Seed-data scope -- PROPOSED: one sample per source type, content
deliberately cross-referenced.** Not a large corpus -- the goal is a
believable, demonstrable concept graph and cross-format retrieval, not
volume.

**6. Demo script format -- PROPOSED: a single Markdown document,** not a
video or a scripted CLI/automation tool, matching this project's existing
documentation medium throughout.

Items 4-6 are proposed defaults consistent with existing project
conventions; flagged individually in case you'd like to redirect any of
them before implementation begins.

## 7. Non-goals -- explicitly NOT part of Milestone 12

To prevent this milestone's scope from being read more broadly later,
the following are explicitly excluded, regardless of how related they
may seem to any item in Section 4:

- **Backup/restore for `postgres_data`/`qdrant_data`/`api_storage`**
  (DRR Section 17) -- deferred per Decision 1. Documented here only as a
  future operational enhancement; revisit trigger: the system moving from
  demo/portfolio use to genuine sole-copy, long-term daily use of real
  personal data. No backup script, cron job, or tooling of any kind is
  designed or implemented by this milestone.
- **Any Vision v2 capability** -- per Decision 2, none of the following
  is in scope: Capture (quick notes, pasted text, URL/article capture,
  screenshot/voice-note capture), Personal Learning Layer (exposure
  tracking, self-reported confidence, mastery scoring, spaced
  repetition, streaks), typed concept relationships beyond what
  Milestone 7 already built, Knowledge Timeline (activity log, Event
  markers, "how my understanding evolved" views), Proactive AI (any
  scheduled/unprompted surfacing), or concept synthesis (auto-summarized
  concept pages).
- **A real task-queue migration (Celery, Temporal, or otherwise)** --
  Section 4.1's evaluation concludes `BackgroundTask` should be retained;
  no broker/worker service is introduced.
- **A dedicated graph database (e.g. Neo4j)** -- unrelated to this
  milestone, no trigger for revisiting ADR's "Postgres recursive CTEs are
  sufficient" position has occurred.
- **Any new confidence computation, classification logic, retrieval
  ranking change, or UI feature** -- this is a hardening and polish
  milestone; every item in Section 4 either operates below the API/UI
  layer (4.1, 4.2) or produces documentation/fixtures (4.3-4.5), not
  product functionality.
- **Chat-answer feedback (thumbs up/down/flagging)** -- explicitly
  deferred by Milestone 11 (ADR-0018); unchanged here.
- **Active-learning classification** (corrections improving the
  classifier automatically) -- Vision v2 Future Research, not
  reconsidered by this milestone.
- **Multi-device/offline-first sync, collaborative/shared knowledge
  graphs** -- Vision v2 Future Research, explicitly out of scope for a
  personal system.
- **Any change to the ingestion pipeline's stage shape** (extract ->
  classify -> chunk -> embed -> index -> concept-link) -- Section 4.1
  adds a reconciliation check that reads job state; it does not add,
  remove, or reorder pipeline stages.
- **A production build/deploy target beyond the existing Docker Compose
  model** (e.g. Kubernetes manifests, a managed cloud deployment guide) --
  ADR-0009 reconfirmed, not revisited.

## 8. Trade-offs

- **Retaining `BackgroundTask` instead of migrating to a queue** (Section
  4.1) keeps the system simple and dependency-light, at the accepted cost
  that a future, larger-than-personal-scale usage pattern would need this
  decision revisited again -- exactly the kind of revisit-triggered
  decision ADR-0005 was always designed to support.
- **A single string `embedding_model_version`** (Design decision 4) is
  simpler to build and query than a normalized version-registry table, at
  the cost of no referential integrity on version identifiers -- acceptable
  for a small, config-driven set of provider/model combinations.
- **Seed data sized for demonstration, not volume** (Section 4.3) keeps
  the repository lightweight and the seeding script fast, at the cost of
  not exercising the system at anything close to real archive scale --
  acceptable, since that's not this item's purpose.
- **A Markdown demo script instead of a recorded walkthrough** (Section
  4.5) is reviewable and versionable like every other doc in this
  project, at the cost of being less immediately persuasive to a casual
  viewer than a video would be -- consistent with this project's
  documentation-first practice throughout.

## 9. Risks

- **The stale-job reconciliation check (4.1) could mask a real, ongoing
  bug** if a legitimately slow job is misclassified as orphaned. Mitigated
  by a generous, configurable threshold and by the fact that recovery is
  already a one-click action via existing retry/reextract routes -- a
  false positive is inconvenient, not destructive.
- **Embedding re-embed tooling (4.2) touching every point in a collection
  is a real bulk operation.** Mitigated by designing it as resumable and
  batchable from the start, not a single unbounded transaction.
- **Seed data (4.3) not being deliberately cross-referenced** would
  produce a concept graph demo that looks the same as before this
  milestone -- this is a content-quality risk, not a technical one, and is
  called out explicitly in Section 4.3's acceptance criteria to keep it
  from being treated as "done" once files simply exist for each format.
- **Scope drift toward Vision v2 or backup tooling during
  implementation**, given how naturally "hardening" invites "just one
  more improvement." Mitigated structurally by Section 7's explicit
  exclusion list, the same mechanism Milestone 11 used successfully to
  keep its own scope narrow.

## 10. Testing / verification strategy

- **Stale-job reconciliation (4.1):** a test that seeds an `IngestionJob`
  row with `status="RUNNING"` and a `started_at` older than the
  threshold, runs the check, and confirms the row becomes `FAILED` with
  the new `error_code`, remains fetchable via the existing document-detail
  route, and is resumable via the existing retry/reextract endpoints
  unchanged. A second test confirms a recent `RUNNING` row is left
  untouched.
- **Embedding versioning (4.2):** a test that a freshly-ingested
  resource's chunk points (and, separately, a freshly-linked concept's
  points) carry the expected `embedding_model_version`; a test that the
  re-embed procedure, run against a workspace with intentionally
  mismatched versions, results in 100% of that workspace's points
  carrying the target version afterward, with the same point count before
  and after (no points silently dropped or duplicated).
- **Seed data (4.3):** an end-to-end script/test that seeds a fresh
  workspace through the real upload path and asserts every seeded
  resource reaches `READY`, and that at least one concept ends up with
  evidence from two or more distinct source types.
- **Documentation/demo script (4.4, 4.5):** manual verification --
  screenshots render correctly in `README.md`; the demo script is walked
  through start to finish against a freshly seeded stack and every stated
  expected outcome is confirmed to actually occur.
- Full existing suite (all Milestone 1-11 tests) must continue passing
  unchanged -- no item in this design touches any frozen route, model, or
  service in a way that should affect existing test expectations.
- Ruff/Black/`tsc --noEmit` clean on every new/changed file, matching
  every prior milestone's verification loop.

## 11. Implementation plan (once this design is approved)

1. Add the stale-job reconciliation check (startup-time, bounded query)
   plus its `error_code` and tests (Section 4.1). No migration required.
2. Add `embedding_model_version` to both Qdrant collections' write paths
   and payload indexes; build the re-embed script and the
   version-distribution check; write tests (Section 4.2). No migration
   required.
3. Build the multi-format seed content and the seeding script (Section
   4.3).
3a. **Amendment (Section 12): fix the concept-resolution concurrency
    race** -- partial unique index migration, `IntegrityError` retry
    path in `resolve_concept()`, `concept.py` docstring update, and a
    concurrency regression test. Sequenced here because it blocks step 4
    (the concept-graph screenshot requires the dedup behavior to hold
    under real concurrent ingestion, which is exactly what Item 3's real
    seeding run exposed it does not, as designed before this amendment).
3b. **Amendment (Section 13): fix `GET /workspace` missing `stats`,
    which blocks the live chat UI entirely** -- `WorkspaceStatsOut`
    schema addition, per-status `Resource` count computation in the
    `get_workspace` route, `workspace.py`/`api.ts` comment corrections,
    and a regression test. Sequenced here because it blocks step 4 (the
    chat-provenance screenshot requires a working chat compose UI, which
    Item 4's live browser session exposed does not currently render for
    any workspace) and step 5 (the demo script's search/explain/citation
    steps require the same UI).
4. Capture and check in the four screenshots; wire them into `README.md`
   (Section 4.4) -- sequenced after steps 3, 3a, and 3b.
5. Write `docs/DEMO_SCRIPT.md` (Section 4.5) -- sequenced after step 3
   (already complete; see Sections 12-13 for why its concept-graph and
   chat sections remain accurate once steps 3a-3b land).
6. Write tests (Section 10), including the new concurrency regression
   test added by step 3a and the workspace-stats regression test added
   by step 3b.
7. Write ADR-0019 (Production Hardening & Portfolio Polish) capturing
   this design's approved decisions, in particular the BackgroundTask
   evaluation outcome and its reasoning, and the concept-resolution
   concurrency fix from Section 12 and the workspace-stats fix from
   Section 13.
8. Update this document to "Implemented and Verified" with real
   verification results, then run the same verification loop Milestones
   4-11 used before freezing.
9. Per the standing process note (`CONTRIBUTING.md`): update
   `README.md`'s Part 2 and Roadmap table, and `CHANGELOG.md`,
   immediately after freezing -- marking the roadmap table's final row
   `Frozen` and, if desired, noting that the original 12-milestone plan
   is complete.

**Status of this plan:** all steps complete. 1-3 (stale-job
reconciliation, embedding versioning, multi-format seed data), 3a and 3b
(the two discovered-in-flight amendments, Sections 12 and 13), 4
(screenshots), 5 (demo script), 6 (tests, including both amendments'
regression tests), 7 (ADR-0019), 8 (this document updated to "Implemented
and Verified" -- see Section 14), and 9 (README/CHANGELOG/module-map
freeze pass, performed as part of the same repository freeze review as
Section 14) are all done.

## 12. Addendum: discovered concurrency race in concept resolution

**Status: approved, implemented, and verified.** See Section 12.1's own
status line for full verification detail. Discovered
during Item 4 (screenshot capture) when a real, docker-compose-deployed
instance was seeded with Section 4.3's fixtures via `demo-data/seed.py`
and the concept graph showed four separate "Data Retention Policy"
concepts (evidence counts 2/1/1/1) instead of the one concept with five
evidence links Section 4.3's acceptance criteria and
`test_seed_data_cross_format_concept.py` require.

**The race, precisely.** `concept_graph.resolve_concept()` (Milestone 7,
unmodified by this milestone until now) checks for an existing `ACTIVE`
concept with a matching `normalized_name` via a plain `SELECT`, and, if
none is found, creates a new `Concept` row. `app/models/concept.py`'s
docstring documents this as deliberate: "Uniqueness ... is enforced at
the application layer ... not via a DB UNIQUE constraint." That check
and that insert are not atomic. When two of the five same-stem uploads
are processed by overlapping `BackgroundTask`s close enough in time, both
can execute the `SELECT` before either commits its `INSERT` -- both see
"no match," both create a new `ACTIVE` concept with the same
`normalized_name`, and the dedup this project has relied on since
Milestone 7 silently doesn't happen.

**Why this was not previously observable.** Every existing test that
exercises `resolve_concept()` (including
`test_concept_linking_ingestion.py`'s
`test_two_uploads_with_equivalent_filenames_dedup_to_one_concept`, and
Item 3's own `test_seed_data_cross_format_concept.py`) runs through
`fastapi.testclient.TestClient`, which executes `BackgroundTask`s
synchronously, serially, within the same call that sends the response --
there is no window in which two ingestion runs are ever actually
in-flight at once. No prior milestone's usage pattern uploaded multiple
same-named resources in quick succession against a real, running,
concurrent server either: this is the first time in the project's
history that condition has actually occurred, via `demo-data/seed.py`
uploading five deliberately-same-stem fixtures back-to-back against the
real `docker compose` deployment for Item 4's screenshots.

**Why a database-backed uniqueness guarantee is now required.** An
application-layer check-then-act sequence cannot be made race-free
without either serializing all concept resolution (a throughput/latency
cost with no other benefit) or backing the invariant with something the
database itself enforces atomically. A partial unique index --
`(workspace_id, normalized_name)` `WHERE status = 'ACTIVE'` -- is the
standard, minimal mechanism for exactly this shape of problem: it costs
nothing on the read path this project already takes (the existing exact
-match `SELECT` is unaffected), allows unlimited `MERGED`/`UNUSED` rows
sharing a name (matching `resolve_concept()`'s own `status ==
ConceptStatus.ACTIVE` filter, so no existing status-lifecycle behavior
changes), and turns the race from "silently succeeds twice" into "the
loser's `INSERT` fails with `IntegrityError`," which `resolve_concept()`
can then catch and resolve by re-querying for the winner's now-committed
row -- the same outcome the sequential case already produces today.
Both SQLite (used by the full test suite) and Postgres (production)
support partial unique indexes, so this is testable exactly as rigorously
as every other migration in this project.

**Why this is a production-hardening bug fix, not scope expansion.**
Milestone 12's own scope statement is explicitly a hardening pass over
what Milestones 1-11 already built, not new product surface -- and
concept deduplication is not new behavior being added here, it is
existing Milestone 7 behavior (frozen, `v0.7.0-concept-graph`) that this
fix makes actually hold under conditions the real, running system can
produce. No new entity, endpoint, intent, or user-visible capability is
introduced; `resolve_concept()`'s external contract (same inputs, same
return shape, same three-zone resolution logic) is unchanged -- only the
one specific check-then-act sequence gains a database-backed guarantee
it was always intended to provide. This is squarely the kind of gap
Section 2's Architecture-doc-risk-#1 discipline exists to catch during a
hardening milestone, not an invitation to redesign concept resolution
more broadly (no other part of `concept_graph.py` is touched).

### 12.1 Amended implementation plan for this fix

1. **Alembic migration:** a partial unique index on
   `concepts(workspace_id, normalized_name)` `WHERE status = 'ACTIVE'`.
   No column changes, no data migration (existing duplicate `ACTIVE` rows
   from this discovery are left as-is by the migration itself -- see
   "Cleanup of already-duplicated data" below).
2. **`resolve_concept()` change:** wrap the no-exact-match branch's
   `db.add(concept); db.flush()` in a `try`/`except IntegrityError`; on
   conflict, roll back the failed insert, re-run the exact-match `SELECT`
   (the winner's row is now guaranteed visible), and return that concept
   instead -- same `ConceptResolution` return shape, no caller-visible
   change. The corresponding concept-vector `upsert()` (currently
   unconditional after concept creation) must only run for the actual
   winner, not the loser that fell back to the existing row.
3. **`app/models/concept.py` docstring update:** revise the "Uniqueness
   ... enforced at the application layer... not via a DB UNIQUE
   constraint" paragraph to state the amended reality (a partial unique
   index backs the `ACTIVE`-scoped name invariant; the application layer
   still owns the ANN-similarity-based near-duplicate detection, which no
   database constraint could express) and reference this addendum.
4. **Concurrency regression test:** since `TestClient` cannot itself
   reproduce the race (per the "why this was not previously observable"
   note above), this test simulates the race directly -- two
   `resolve_concept()` calls for the same workspace/name against the same
   underlying database, with the second call's transaction deliberately
   forced to attempt its insert after the first has committed but before
   the first's caller has re-queried, asserting both calls return the
   *same* concept id and exactly one `Concept` row exists afterward, not
   two.
5. **Cleanup of already-duplicated data:** the four split concepts
   already created in the Docker-deployed demo workspace during Item 4's
   screenshot attempt are a symptom, not a separate defect -- once this
   fix lands, re-running `demo-data/seed.py` against a fresh workspace
   will not reproduce them (new uploads hit the fixed path). The existing
   split rows in that specific already-seeded workspace can be resolved
   via the existing `POST /concepts/{id}/merge` endpoint (already
   designed as "the manual-merge escape hatch for anything the automated
   check misses") once this fix is approved -- no new tooling required.
6. **Operational deployment note (not an implementation change):**
   applying this migration to a deployment that already contains
   duplicate `ACTIVE` concepts fails at `alembic upgrade head` --
   confirmed directly when this fix was rolled out to the real
   `docker compose` deployment for Item 3a's live verification: Postgres
   rejected the partial unique index's `CREATE INDEX` with a
   `UniqueViolation` against the four pre-existing duplicate rows, and
   the `api` container (whose startup command runs `alembic upgrade
   head` before `uvicorn` starts) crash-looped as a result. Step 5's
   assumption -- that the existing duplicates can be cleaned up via the
   running `POST /concepts/{id}/merge` endpoint once this fix is approved
   -- does not hold in practice for this project's single-container
   deployment model, because the API that serves that endpoint is not
   reachable until the same migration that requires the cleanup has
   already succeeded. For this project's demo/portfolio deployment, the
   simplest resolution is a full local reset (`docker compose down -v`
   followed by `docker compose up -d --build`) since no real user data is
   at stake; a deployment carrying real data would instead need any
   pre-existing duplicate `ACTIVE` concepts resolved by a one-off
   maintenance step (e.g. direct SQL or a standalone script using the
   same merge logic as the endpoint) run against the database *before*
   the new `api` image is deployed, not after. This does not change
   `resolve_concept()`, the migration, or any other part of this fix's
   design -- it is a deployment-ordering fact about *this* migration,
   recorded here for anyone applying it to a non-fresh database.

**Acceptance criteria:** re-running `demo-data/seed.py` against a fresh
workspace on the real `docker compose` deployment produces exactly one
"Data Retention Policy" concept with five evidence links, matching
`test_seed_data_cross_format_concept.py`'s existing (TestClient-based)
assertions now also holding under real concurrent execution; the new
concurrency regression test fails against the pre-fix code and passes
against the fix; full existing regression suite continues passing
unchanged; Ruff/Black clean.

**Status of this addendum: approved, implemented, and verified.** All
steps 1-4 implemented and covered by passing tests (including the
concurrency regression test, confirmed to fail against pre-fix code and
pass against the fix). Step 5/6's cleanup was exercised for real via a
full local stack reset rather than the merge endpoint, per the
operational note above. Re-verified against a fresh `demo2@example.com`
workspace on the real `docker compose` deployment: the Concepts page
shows exactly one "Data Retention Policy" concept with five evidence
entries, one per seeded source format.

## 13. Addendum: discovered missing workspace stats blocking the chat UI

**Status: approved, implemented, and verified.** See Section 13.1's own
status line for full verification detail. Discovered
during Item 4 (screenshot capture) when `/chat` was opened live against
the verified `demo2@example.com` workspace (8 Ready documents) for the
`chat-provenance.png` screenshot, and the page showed "0 ready documents
in this workspace" with the entire message-compose UI hidden behind a
"you need at least one Ready document" blocker -- despite the workspace
genuinely having 8 Ready documents, confirmed moments earlier on
`/documents` and `/concepts`.

**The bug, precisely.** `apps/web/app/chat/page.tsx` reads
`ws.stats?.readyDocuments ?? 0` from `api.getWorkspace()` and uses it to
decide whether to render the compose form at all (`readyCount !== 0`) or
the blocking screen (`readyCount === 0`) -- not a cosmetic count, a hard
UI gate. `apps/api/app/schemas/auth.py`'s `WorkspaceOut` has only `id`
and `name`; `apps/api/app/api/v1/routes/workspace.py`'s `get_workspace`
handler always returns `WorkspaceResponse(workspace=WorkspaceOut(id=...,
name=...))`, with no `stats` anywhere in the response. `ws.stats` is
therefore always `undefined` and `readyCount` is always `0`, for every
workspace, unconditionally -- the chat compose UI cannot be reached at
all through the real application today, regardless of how many Ready
documents exist.

**Why this was not previously observable.** This is a genuine regression
introduced silently during Milestone 8 ("Reactivate frontend chat UI"),
not a gap that was always present. `apps/web/lib/api.ts`'s own comment on
`WorkspaceStatsOut` (lines 88-98) states `stats` was declared optional
"only because the dormant Milestone 4 chat screen
(`app/_future/chat/page.tsx`) already reads it" and that the field exists
"to keep that type-check honest without reactivating or rewriting that
screen" -- but Milestone 8 *did* reactivate that exact screen (commit
`6da7073`, promoting `app/_future/chat/` to the live `app/chat/` route)
and carried its `ws.stats?.readyDocuments` read over unchanged, without
also building the backend `stats` field that read depends on. The
comment was never updated to reflect that the screen stopped being
dormant. No test caught this because this project's automated test suite
is entirely backend (`pytest`/`TestClient`) -- `apps/api/tests/
test_workspace.py`'s six tests assert only on `workspace.id`/
`workspace.name`, never `stats` -- and no prior milestone's manual
verification pass opened the real `/chat` page in a browser against a
real seeded workspace before this session. `chat.py`'s own
`POST /{conversation_id}/messages` route independently computes an
equivalent `ready_doc_count` for its own server-side gating (lines
87-91) and works correctly when called directly -- the bug is entirely
in what `GET /workspace` reports back, not in message-sending itself.

**Why a fix is required.** Chat (Explain/Search, provenance badges,
citations, sufficiency reasoning) is core, already-shipped
Milestone 8/9/11 functionality this milestone's own Items 4 and 5 are
required to demonstrate. Leaving this bug in place would mean the
project's own portfolio screenshots and demo script could not honestly
show chat working at all through the real application, even though the
underlying API behavior is correct and fully tested.

**Why this is a production-hardening bug fix, not scope expansion.** The
frontend has read `ws.stats.readyDocuments` since Milestone 4's original
design and carried that expectation into Milestone 8's live chat page;
`GET /workspace`'s own docstring already promised "the `stats` field is
added back in Milestone 3 alongside the Document model it depends on."
This fix makes an already-promised, already-consumed contract actually
true -- it adds no new entity, no new endpoint (reuses existing
`GET /workspace`), and no new intent or capability. The count logic
itself already exists verbatim in `chat.py`'s message-send route; this
fix only surfaces the same computation through a second, already-expected
read path.

### 13.1 Amended implementation plan for this fix

1. **Schema change:** add a `WorkspaceStatsOut` Pydantic model
   (`readyDocuments`, `processingDocuments`, `failedDocuments` --
   mirroring `apps/web/lib/api.ts`'s existing `WorkspaceStatsOut`
   TypeScript interface exactly, so no frontend type change is needed)
   to `apps/api/app/schemas/auth.py`; add an optional `stats` field to
   `WorkspaceResponse`.
2. **Route change:** in `apps/api/app/api/v1/routes/workspace.py`'s
   `get_workspace` handler, compute per-status `Resource` counts scoped
   to `workspace.id` (the same `.query(Resource).filter(...).count()`
   pattern `chat.py` lines 87-91 already uses for `READY`, extended to
   all three statuses relevant here) and populate `stats` in the
   response. `update_workspace` (PATCH) left unchanged -- no consumer
   reads `stats` from a rename response.
3. **Module docstring update:** revise `workspace.py`'s module docstring
   (which currently still says stats "doesn't exist right now" and "is
   added back in Milestone 3") to reflect that it is now implemented, and
   reference this addendum for why it landed in Milestone 12 instead.
4. **`api.ts` comment update:** correct the now-stale comment on
   `WorkspaceStatsOut` (lines 88-98) -- `app/chat/page.tsx` is the live
   route, not `app/_future/chat/page.tsx`, and `stats` is no longer
   optional-because-unimplemented; the `?` can stay (defensive against
   older cached responses) but the comment must stop describing a screen
   that no longer exists in `_future/`.
5. **Regression test:** a backend test seeding a workspace with a known
   mix of `READY`/`PROCESSING`/`FAILED` `Resource` rows, calling
   `GET /workspace`, and asserting `stats.readyDocuments`/
   `processingDocuments`/`failedDocuments` match exactly -- plus a test
   confirming a workspace with zero resources returns
   `readyDocuments: 0` (so the chat page's blocking screen still shows
   correctly when it should).

**Acceptance criteria:** `GET /workspace` returns accurate per-status
document counts for the calling workspace; a live `/chat` page opened
against the verified `demo2@example.com` workspace shows the compose UI
(not the blocker) and "8 ready documents in this workspace"; a
regression test fails against the pre-fix route and passes against the
fix; full existing regression suite continues passing unchanged;
Ruff/Black/`tsc --noEmit` clean.

**Status of this addendum: approved, implemented, and verified.** All
five steps implemented: `WorkspaceStatsOut` schema added, `get_workspace`
now computes and returns per-status counts, both stale docstring/comments
(`workspace.py`'s module docstring, `api.ts`'s `WorkspaceStatsOut` and
`getWorkspace()` comments) corrected, and three regression tests added
(`tests/test_workspace_stats.py`) -- confirmed to fail against the pre-fix
route and pass against the fix. Full 40-file backend suite passes
unchanged; Ruff, Black, and `tsc --noEmit` all clean. Re-verified live
against the rebuilt `docker compose` deployment: `GET /workspace` for the
`demo2@example.com` workspace returns
`stats: {readyDocuments: 8, processingDocuments: 0, failedDocuments: 0}`;
`/chat` renders the compose UI (not the blocker) and reports "8 ready
documents in this workspace"; Search mode, tested live, returns a real
answer with a provenance badge, confidence score, and a citation pill
back to the source document -- confirming the chat UI's provenance/
citation path is genuinely functional end to end, not just unblocked.

## 14. Final verification summary (Step 8)

**Final implementation state.** All five originally-scoped items (Section
4.1-4.5) and both discovered-in-flight amendments (Sections 12 and 13)
are implemented, tested, and verified against a real, running
`docker compose` deployment -- not inferred from design intent alone.
Nothing in Section 7's non-goals list was touched. No remaining TODO,
placeholder, or "not yet implemented" marker exists anywhere in this
milestone's own scope:

- **4.1 Stale-job reconciliation:** `app/services/job_reconciliation.py`
  (`reconcile_stale_jobs`), wired into `app/main.py`'s startup event,
  `STALE_JOB_THRESHOLD_MINUTES` config setting added. Covered by
  `tests/test_job_reconciliation.py` (orphaned-`RUNNING`-row-marked-
  `FAILED` case and recent-`RUNNING`-row-left-untouched case).
- **4.2 Embedding-version tagging + re-embed tooling:**
  `embedding_model_version` on every `VectorPoint` (both collections),
  `EmbeddingProvider.version` on both providers, payload-index handling
  for both fresh and pre-existing collections, and
  `app/services/reembed.py`. Covered by
  `tests/test_embedding_versioning.py`.
- **4.3 Multi-format seed data:** one fixture per remaining source type
  (`demo-data/data_retention_policy.{docx,pptx,md,py,png}`,
  `demo-data/YOUTUBE_REFERENCE.md`), `demo-data/seed.py` seeding script
  ingesting through the real `/api/v1/documents` upload path. Covered by
  `tests/test_seed_data_cross_format_concept.py`.
- **Section 12 (concept-resolution concurrency):** migration
  `0010_concept_dedup_unique_index`, `resolve_concept()`'s
  `IntegrityError`-recovery path (scoped to its own `SAVEPOINT` via
  `db.begin_nested()`, a refinement of Section 12.1's plan discovered
  during implementation to be necessary so a losing insert's rollback
  cannot disturb other uncommitted work earlier in the same ingestion
  transaction), and `app/models/concept.py`'s docstring update. Covered
  by `tests/test_concept_resolution_concurrency.py` (confirmed to fail
  against pre-fix code, pass against the fix).
- **Section 13 (workspace stats):** `WorkspaceStatsOut` schema,
  `_workspace_stats()` helper in `workspace.py`, and the corrected
  `workspace.py`/`api.ts` comments. Covered by
  `tests/test_workspace_stats.py` (confirmed to fail against pre-fix code,
  pass against the fix).
- **4.4/4.5 Documentation:** all four screenshots captured and checked in
  (`docs/assets/screenshots/`), `README.md` wired to embed them,
  `docs/DEMO_SCRIPT.md` written and corrected against two empirically
  observed quirks (`seed.py`'s `.local` email-validation rejection;
  Explain mode's honest fail-closed behavior under zero-config local
  embeddings).
- **ADR-0019** written, capturing all four architectural decisions plus
  the operational note, in the same style as ADR-0001 through ADR-0018.

**Live verification results (consolidated).** Re-verified against a
freshly rebuilt `docker compose` deployment seeded via
`python demo-data/seed.py --email demo2@example.com`:

- `/documents` shows all 8 seeded resources at `Ready`.
- `/concepts` shows exactly one "Data Retention Policy" concept with 5
  evidence links (one per source format) -- the concurrency fix holding
  under real concurrent `BackgroundTask` ingestion, not just serial test
  execution.
- `GET /workspace` returns
  `stats: {readyDocuments: 8, processingDocuments: 0, failedDocuments: 0}`.
- `/chat` renders the compose UI (not the "0 ready documents" blocker)
  and reports "8 ready documents in this workspace."
- Search mode returns a real answer badged "From your documents," with a
  confidence score and a citation pill linking back to the source
  document -- the full provenance/citation path functioning end to end
  through the live UI.

**Final test results.** Full backend suite: 228 tests collected, 228
passed, 0 failed, 0 errors (36 test files, including all new Milestone 12
test modules). Ruff (`ruff check app tests`, matching this project's CI
scope) and Black (`black --check app tests`) both clean. `tsc --noEmit`
clean on `apps/web`. No test was skipped, xfailed, or modified to make it
pass; the two amendment regression tests were independently confirmed to
fail against their respective pre-fix code before the fix landed.

**Implementation summary.** Real content changes (beyond new,
milestone-specific files) touched exactly eleven existing files:
`README.md`, `apps/api/app/api/v1/routes/workspace.py`,
`apps/api/app/core/config.py`, `apps/api/app/main.py`,
`apps/api/app/models/concept.py`, `apps/api/app/schemas/auth.py`,
`apps/api/app/services/concept_graph.py`,
`apps/api/app/services/embeddings.py`,
`apps/api/app/services/ingestion_service.py`,
`apps/api/app/services/vector_repo.py`, `apps/web/lib/api.ts`,
`demo-data/README.md`, and `docs/assets/screenshots/README.md`. Every one
of those changes traces directly to a specific approved section (4.1,
4.2, 12, or 13) of this document; none introduces an endpoint, schema
change, or frontend behavior outside what those sections describe. No
other tracked file in the repository was modified in content (a full
`git diff` review found only filesystem-mode changes -- 100644 to 100755
-- across the rest of the tree, a pre-existing artifact of this project's
Windows-hosted filesystem, not a Milestone 12 change).

**No remaining TODOs.** No `TODO`, `FIXME`, or "not yet implemented"
marker exists in any file this milestone added or touched, and no
acceptance criterion from Section 4.1-4.5, 12.1, or 13.1 remains
unchecked.
