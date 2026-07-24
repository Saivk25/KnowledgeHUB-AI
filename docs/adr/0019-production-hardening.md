# ADR-0019: Production Hardening & Portfolio Polish (Milestone 12)

**Status:** Accepted (Milestone 12)

**Decision:** Milestone 12 concludes the original 12-milestone roadmap as
a hardening pass, not a feature milestone. Four genuine architectural
decisions came out of it -- one a planned re-evaluation (BackgroundTask
vs. a task queue), one a planned design gap closed ahead of need
(embedding versioning), and two unplanned corrections discovered only by
running the real, seeded system against a live `docker compose`
deployment rather than through `pytest`/`TestClient` alone (a
concept-resolution concurrency race, and a backend/frontend contract
mismatch on workspace document counts). This ADR records the four
decisions and their rationale; implementation detail, verification
commands, and file-level changes live in
`docs/milestones/MILESTONE_12.md` (Sections 4, 12, and 13) and are not
repeated here.

## Sub-decisions

**1. BackgroundTask vs. a real task queue -- retain BackgroundTask, close
the crash-recovery gap with stale-job reconciliation, not a queue
migration.** ADR-0005 named its own revisit trigger explicitly: "the
product needs multi-instance workers, ingestion retries with backoff, or
ingestion volume high enough to need independent scaling from the API."
Milestone 12 evaluated all three against this project's actual, current
profile, not a hypothetical one, since Concept Graph (M7) is the
Architecture doc's own stated point to re-evaluate at (the first stage
whose cost scales with existing corpus size, not just new uploads).
Multi-instance workers: not needed -- `docker-compose.yml` runs one `api`
replica by design (ADR-0009), and this remains a personal, single-user
system. Retries with backoff: the real gap here is crash *detection*, not
retry *scheduling* -- a job stuck `RUNNING` forever isn't being retried
incorrectly, it's never being retried at all, which a queue's retry
policy wouldn't fix by itself. Independent scaling: concept-linking's
per-upload cost is bounded by `MAX_TRAVERSAL_DEPTH` and the existing
ANN-based dedup lookup, with no demonstrated need at this product's
"thousands of resources" scale (Architecture Section 5). None of the
three trigger conditions is met, so ADR-0005 is reconfirmed, not
superseded. The one concrete gap that *is* real -- a process crash
between any of the pipeline's now-six stages (it was four when ADR-0005
was written) leaves an `IngestionJob` row `RUNNING` forever, with no
detection or resumption -- is closed narrowly: a bounded, indexed query
(`status == 'RUNNING' AND started_at < cutoff`) run at API startup marks
orphaned jobs `FAILED` with a distinct `INTERRUPTED` error code, and
recovery happens through the existing, unchanged retry/reextract
endpoints (Milestone 3/11). No new service, no new dependency, and
`_run_ingestion`'s stage logic is untouched.

**Alternatives considered:** Celery + Redis and Temporal were both
re-evaluated on their merits (not merely re-rejected by inertia) and
rejected again for the same reason ADR-0005 gave initially -- both add an
operated service for a scaling/persistence benefit this project's actual
profile doesn't need. Doing nothing about the crash-recovery gap was
rejected because it is a genuine, narrow, low-cost-to-fix finding
distinct from the queue question.

**Revisit when:** unchanged from ADR-0005 -- multi-instance workers, real
retry/backoff needs, or corpus-size-driven independent scaling. The
stale-job threshold (`STALE_JOB_THRESHOLD_MINUTES`) is a config value, not
a hardcoded constant, precisely so a future, longer-running legitimate job
doesn't need a code change to avoid a false-positive reconciliation.

**2. Embedding versioning -- a per-point string tag in the vector store's
payload, not a per-collection versioning scheme, and not deferred until a
model upgrade is actually attempted.** Architecture Section 5 and Section
9 (item 6) both called for this ahead of need: "requires re-embedding the
entire corpus; this needs a documented migration path... not as an
afterthought when the first model upgrade is actually needed." The
alternative of a separate version-registry table (normalized,
foreign-keyed) was rejected as unnecessary structure for what is, today, a
two-provider (`local`/`openai`) system already configured via a single
string (`EMBEDDING_PROVIDER`) -- a plain `embedding_model_version` string
per point (e.g. `"local-hash-v1"`, `"openai:text-embedding-3-small"`) is
consistent with that existing convention and sufficient to detect a
mismatch. Waiting until a real model upgrade forced the issue was
rejected outright as the exact "afterthought" sequencing the Architecture
doc warns against -- retrofitting a version tag onto points that were
never tagged is strictly harder than tagging from day one. The re-embed
tooling reuses `VectorRepository`'s existing `upsert()`/`delete_by_concept()`
methods rather than adding new interface surface, is batched and
resumable (not a single unbounded transaction), and is selective where the
underlying store supports it (skips points already at the target
version) -- see `app/services/reembed.py`. This is a Qdrant-payload and
tooling change only: no Postgres schema changed, no Alembic migration
required.

**Alternatives considered:** a dedicated reindexing service/pipeline was
rejected as unnecessary process growth for a single-collection-pair,
personal-scale system.

**Revisit when:** a third embedding provider or a normalized
version-metadata need (e.g. per-version cost/quality tracking) makes a
plain string insufficient -- not anticipated at this system's scale.

**3. Concept-resolution concurrency -- enforce ACTIVE-name uniqueness with
a database-backed partial unique index, with `resolve_concept()`
recovering from the resulting `IntegrityError` rather than preventing it
by serializing resolution.** `resolve_concept()`'s dedup (Milestone 7) was
a plain exact-match `SELECT` followed by an `INSERT` -- correct for any
single request, but not atomic across two. This had never mattered
before Milestone 12, because every prior test exercised it through
`fastapi.testclient.TestClient`, which runs `BackgroundTask`s
synchronously, and no prior milestone's usage pattern uploaded multiple
same-stem resources against a real, concurrently-serving instance. It
surfaced for the first time when this milestone's own multi-format seed
data (`demo-data/seed.py`, five deliberately same-stem fixtures) was
uploaded against a real, running `docker compose` deployment for
screenshot capture: two overlapping `BackgroundTask`s could both pass the
`SELECT` before either committed, producing duplicate `ACTIVE` concepts
with the same `normalized_name`. A partial unique index --
`(workspace_id, normalized_name)` `WHERE status = 'ACTIVE'` -- is the
standard, minimal fix for exactly this shape of check-then-act race: it
costs nothing on the unaffected exact-match read path, leaves `MERGED`/
`UNUSED` rows free to share a name (matching `resolve_concept()`'s own
`status == ACTIVE` filter), and turns the race from "silently succeeds
twice" into a catchable `IntegrityError`. `resolve_concept()` catches
that specific exception, re-queries for the now-committed winner, and
returns it -- same `ConceptResolution` return shape, no caller-visible
change, and the losing caller's concept-vector `upsert()` is skipped
rather than run against a row that was never actually created.

**Why hardening, not new functionality:** concept deduplication is not
new behavior introduced here -- it is existing, frozen Milestone 7
behavior (`v0.7.0-concept-graph`) that this change makes actually hold
under a condition the real, running system can produce. `resolve_concept()`'s
external contract (inputs, return shape, three-zone resolution logic) is
unchanged; no new entity, endpoint, or intent is introduced. This is
squarely a correction to an existing guarantee's enforcement mechanism,
the same category of change Milestone 11's confidence/correction work
made to already-computed-but-unsurfaced data, not a scope expansion.

**Alternatives considered:** serializing all concept resolution (e.g. a
workspace-level lock around the check-then-act sequence) was rejected as
a throughput/latency cost with no benefit beyond what the index already
achieves for free. Leaving the race unaddressed and relying on the
existing manual-merge endpoint to clean up after the fact was rejected --
merge is the correct tool for a human-identified near-duplicate, not for
a mechanical race the system itself should prevent.

**Revisit when:** if concept resolution is ever distributed across
multiple database instances (not anticipated -- single Postgres instance
per ADR-0009's deployment model), a unique index alone would no longer be
sufficient and the resolution path would need a distributed-locking
strategy instead.

**4. Workspace stats -- fix `GET /workspace` to satisfy the contract the
frontend already expected, rather than changing the frontend to match the
backend's gap.** Opening `/chat` live against a freshly seeded, genuinely
Ready-document-populated workspace showed "0 ready documents in this
workspace" and a permanently hidden compose UI. `apps/web/lib/api.ts`'s
`getWorkspace()` and `app/chat/page.tsx` have expected a `stats.readyDocuments`
field back from `GET /workspace` since Milestone 4 (when the now-live chat
screen still lived, dormant, under `app/_future/`); `GET /workspace`
itself never returned one -- its own module docstring said the field
"doesn't exist right now" and would be "added back in Milestone 3," which
never happened. Milestone 8's "Reactivate frontend chat UI" step promoted
that dormant screen to the live route and carried its `stats` read over
unmodified, without also building the backend field that read depends on
-- a real, silent regression that went uncaught because this project's
test suite is entirely backend (`pytest`/`TestClient`); no prior
milestone's manual verification opened the live `/chat` page against a
real seeded workspace before this one. The fix populates `stats` in
`GET /workspace`'s existing response (per-status `Resource` counts,
reusing the identical `.query(Resource).filter(...).count()` pattern
`chat.py`'s own message-send route already used for its own gate) --
extending an existing response, not adding a new endpoint, and requiring
zero frontend changes beyond correcting two comments that had gone stale
describing the screen as still dormant.

**Why fix the backend, not the frontend:** the frontend's expectation was
the correct, load-bearing one -- it had shipped and been relied on since
Milestone 4, and rewriting `app/chat/page.tsx` to stop expecting `stats`
would mean permanently removing the ready-document gate rather than
making it work, a regression in the other direction. The backend was the
side that never delivered on an already-established contract.

**Alternatives considered:** none seriously -- once the mismatch was
identified, satisfying the pre-existing, already-consumed contract was
the only option that didn't remove existing frontend functionality.

**Revisit when:** not applicable -- this closes a gap in an existing
contract; no further evolution is anticipated unless a future milestone
wants additional workspace-level aggregates (e.g. concept counts),
which would extend `WorkspaceStatsOut` rather than replace this
mechanism.

**Operational notes:** Applying the concept-dedup partial unique index (sub-decision 3) to a
deployment that already contains duplicate `ACTIVE` concepts fails at
migration time -- `CREATE UNIQUE INDEX` cannot succeed over data that
already violates it, and this project's single-container deployment model
runs migrations as part of the same `api` image's startup command that
must succeed before the API (and therefore the merge endpoint that would
otherwise clean up those duplicates) becomes reachable. Any deployment
carrying real, pre-existing duplicate `ACTIVE` concepts must have them
resolved by a one-off maintenance step *before* the new image is deployed,
not via the running application afterward. For this project's own
demo/portfolio deployment, a full local reset was sufficient since no
real user data was at stake; see `docs/milestones/MILESTONE_12.md`
Section 12.1 for the full operational note.

**Consequences:** No existing route, model column, or intent contract changed as a result
of this milestone. One new Alembic migration
(`0010_concept_dedup_unique_index`) adds a partial index only; no other
migration was required by any of the four decisions above. Two files
(`apps/api/app/api/v1/routes/workspace.py`'s module docstring,
`apps/web/lib/api.ts`'s `WorkspaceStatsOut` comment) were corrected from
describing a state (a dormant chat screen, an unpopulated `stats` field)
that had already stopped being true since Milestone 8 -- a documentation
accuracy fix, not a design change. `apps/api/app/services/job_reconciliation.py`
and `apps/api/app/services/reembed.py` are the two new, additive service
modules this milestone introduces; neither is reachable via a new route.
