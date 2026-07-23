# ADR-0018: Confidence & correction UX (Milestone 11)

**Status:** Accepted (Milestone 11)

**Decision:** Surface confidence and correction signals that already
existed in the data model but never reached the API or UI
(`Resource.auto_*`, `Answer.sufficiency_reason`), add one new
correction-history table (`resource_corrections`) logging every manual
classification correction, and add one new re-extraction endpoint
(`POST /documents/{id}/reextract`) for low-confidence `READY` resources
-- all additive. No existing route's request/response contract changed,
and no existing table's columns changed. Scoped entirely from two
implementation audits of the live codebase, not from design-doc
assumptions -- see `docs/milestones/MILESTONE_11.md` for the full audit
trail and design record.

## Sub-decisions

**1. `resource_corrections` is a new, separate table -- not a column on
`Resource`, not reusing another table.** `PATCH
/documents/{id}/classification` (`documents.py`) overwrote
`content_category`/`subject` with no record of the prior value,
confidence, or when the change happened -- confirmed by audit to be true
of every existing table in `app/models/`. A single new column (e.g.
`Resource.last_corrected_at`) could only ever hold the *most recent*
correction, losing the change of a field corrected twice; `resource_corrections`
is a proper one-row-per-correction log (`resource_id`, `workspace_id`,
`field`, `previous_value`, `previous_confidence`, `new_value`,
`corrected_at`), matching this codebase's existing precedent of a
dedicated child table whenever a "history of changes to X," not just
"X's current value," is the actual requirement (e.g. `IngestionJob` vs.
`Resource.status`). `workspace_id` is stored directly on the row (not
resolved only via the `resource_id` join) for the same query-performance
reason `QuizAttempt`/`VivaSession` (ADR-0017) also store it redundantly.

**2. Correction history is persisted, not computed on demand or kept
client-side only.** The alternative -- deriving "what changed" by diffing
`auto_*` against the authoritative fields at read time -- cannot
reconstruct a full history: once a field is corrected a second time, the
first correction's before/after values are gone unless captured at the
moment of the second `PATCH`. `resource_corrections` rows are inserted
from inside `update_classification`'s existing route body, one per
changed field, capturing `resource.content_category`/
`resource.content_category_confidence` (etc.) as they stand *immediately
before* being overwritten -- the only point in the request lifecycle
where the prior value is still available. A new read-only route, `GET
/documents/{id}/corrections`, exposes the log newest-first; there is no
route to create, edit, or delete a correction row directly.

**3. `POST /documents/{id}/reextract` is a new, separate route --
`retry_document` and its route are byte-for-byte unchanged.**
`POST /documents/{id}/retry` is hard-gated to `status == FAILED`
(`documents.py`); there was no route allowing re-extraction on an
already-`READY` document with a low extraction confidence. The
alternative considered -- widening `/retry`'s existing guard to also
accept `READY` -- was rejected because it changes a frozen Milestone 3/5
route's accepted-state contract, which is a behavior change to existing
functionality, not an addition. `reextract_document` accepts only
`status == READY` (404/409 guards mirroring `retry_document`'s own
pattern for not-found/wrong-state), sets status back to `QUEUED`, clears
`error_message`, and re-enqueues the identical `_run_ingestion`
background task both `upload_document` and `retry_document` already use
-- no new extraction logic, no new job step. This does leave a small,
accepted amount of duplication: both routes share the same 3-line
requeue body (set `QUEUED`, clear `error_message`, enqueue
`_run_ingestion`), inlined separately in each rather than factored into
one shared helper, specifically so `retry_document`'s function body has
zero diff.

**4. Confidence metadata is exposed additively -- no new computation
anywhere.** `Resource.auto_content_category(_confidence)`/
`auto_subject(_confidence)` have existed since Milestone 6
(ADR-0013's "two parallel column layers"), written on every
classification run, but were never returned by `DocumentOut`.
`Answer.sufficiency_reason` has existed since Milestone 8, computed by
the unchanged `services/sufficiency.py`, but had no corresponding field
in `AnswerOut` or `IntentResponse`. Both are added as new optional
fields on their existing schemas -- `DocumentOut.autoContentCategory`/
`autoContentCategoryConfidence`/`autoSubject`/`autoSubjectConfidence`,
and `AnswerOut.sufficiencyReason`/`IntentResponse.sufficiencyReason` --
with zero change to how any of these values are computed or stored.
`IntentResponse.sufficiencyReason` is populated for none of the nine
intent handlers today (none was modified, matching the "every existing
`IntentResponse` construction continues to work unchanged" requirement);
it exists as additive schema plumbing for a future handler that resolves
a real sufficiency verdict, not as something wired end to end yet.
`LOW_CONFIDENCE_THRESHOLD` (one new config setting, `0.5`, shared across
extraction and classification triage) is the only genuinely new value
this milestone introduces, and it gates client-side UI decisions only --
no backend route enforces it.

**5. Chat-answer feedback (thumbs up/down, "flag this answer") is
intentionally out of scope, not deferred by omission.** The audit
confirmed the only chat interaction beyond passive display is the
pre-existing external-fallback confirmation button -- no partial
feedback mechanism exists to extend. Building one would be genuinely new
product surface, not an exposure of already-computed data, which is this
milestone's actual scope (per `KnowledgeOS_Architecture_PRD_Roadmap.md`
Section 8's "confidence... UI surfaces; correction flows feed back into
stored metadata"). This milestone's chat-facing change is limited to
rendering the already-returned `sufficiencyScore` (previously computed
but dropped by `chat/page.tsx`, now copied into state and displayed) and
the new `sufficiencyReason`-driven "Why?" affordance.

**Implementation consequences:** `DocumentOut`, `AnswerOut`, and
`IntentResponse` each gained optional fields only -- every existing
client of these schemas (including every Milestone 9/10 intent handler)
continues to work unchanged. `update_classification`'s externally
visible behavior (fields overwritten, confidence set to `1.0`,
`_confirmed` set to `True`) is unchanged; the only addition is one extra
`INSERT` per changed field alongside the existing `UPDATE`. Two new
routes add to the API surface; zero routes were removed or had their
contracts changed.

**Migration impact:** one new migration, `0009_confidence_correction_ux`
(`down_revision = 0008_study_workflows`), creating `resource_corrections`
plus its two indexes (`resource_id`, `workspace_id`). No column was
added, removed, or altered on `resources`, `answers`, or any other
existing table -- every field this milestone surfaces already existed on
`Resource`/`Answer` before this migration. No backfill: `resource_corrections`
starts empty; a resource's classification history before this milestone
is not retroactively reconstructed, since the prior values were never
recorded.

**Alternatives considered:** a query parameter on the existing `/retry`
route (`POST /documents/{id}/retry?allowReady=true`) was considered as
an alternative to a wholly new `reextract` route -- both are additive,
but a new route keeps `retry_document` at zero diff rather than adding a
conditional branch inside a frozen function. Deriving correction history
from a diff of `auto_*` against the authoritative fields (no new table)
was considered and rejected per sub-decision 2 -- it cannot represent
more than the single most recent correction.

**Revisit when:** ADR-0013 anticipated this exact gap ("Milestone
10/11's 'Confidence & Correction UX' may want a richer correction
history"); `resource_corrections` closes it for classification only. A
future milestone that wants chat-answer feedback, a `DISMISSED` outcome
for the reclassification-suggestion banner, or extraction-confidence
correction (as opposed to re-running extraction) would extend this
schema rather than replace it.
