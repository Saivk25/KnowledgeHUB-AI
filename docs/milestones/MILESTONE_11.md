# Milestone 11: Confidence & Correction UX

**Status: Implemented and Verified.**

Design approved; every item in Section 4 implemented exactly as
specified, tested, independently re-audited against the approved design
(four minor documentation/cleanup issues found and fixed, zero functional
or scope issues), and verified against a real environment (Alembic,
pytest, Ruff, Black, `tsc --noEmit`). See Section 12 for the full
verification results and Section 13 for the implementation-review
findings. Ready to freeze.

**Revision note:** this version supersedes the prior draft. Every
proposed change below is now traced directly to a specific finding from
the two implementation audits conducted against the live codebase (not
against ADRs, the roadmap, or prior design assumptions). Audit findings
are cited inline as **[Audit N.M]**, referencing:
- **Audit 1** -- the 10-point implementation audit of
  `resource.py`/`answer.py`/`documents.py`/`extraction.py`/
  `classification.py`/`documents/[id]/page.tsx`/`documents/page.tsx`/
  `chat/page.tsx`/`models/`/`ADR-0013`.
- **Audit 2** -- the follow-up schema/API-client audit of
  `schemas/document.py`/`schemas/chat.py`/`schemas/intents.py`/`lib/api.ts`.

Any proposal that Audit 1 or Audit 2 showed already exists has been
removed from this design. Every remaining backend change is additive
only (Section 4 restates, for each item, exactly what audit finding
justifies it and why it doesn't duplicate existing behavior).

---

## 1. Scope

Per `KnowledgeOS_Architecture_PRD_Roadmap.md` Section 8, Milestone 11 is:

> **Confidence & Correction UX** -- Dedicated UI surfaces for
> OCR/classification/retrieval confidence; correction flows feed back
> into stored metadata (and, if in scope, future classification tuning).

This design does not treat that roadmap line as a spec to infer behavior
from -- it is scoped entirely from what the two audits found missing in
the live code, listed exhaustively in Section 3. The roadmap line is
quoted here only to explain why this milestone exists at all in the
project's sequence.

## 2. Audit baseline (authoritative -- supersedes prior design-doc claims)

The prior version of this document was informed by a general review of
governing documents and a single research pass. That has since been
superseded by two rigorous, code-only audits, whose findings are now
this document's sole basis for scope. Nothing below is inferred from
`CONTRIBUTING.md`, the ADRs, the PRD, or the Vision document -- those are
cited only where explicitly relevant to *why* a gap matters, never as
evidence that something is or isn't implemented. All implementation
claims trace to Audit 1 or Audit 2 exclusively.

## 3. Confirmed implementation state (from Audit 1 + Audit 2)

| Signal / mechanism | Model field | API schema | Frontend | Audit citation |
|---|---|---|---|---|
| Extraction confidence | `Resource.extraction_confidence` | `DocumentOut.extractionConfidence` (`document.py:23`) | Rendered, `documents/[id]/page.tsx:202-206` | Audit 1 item 4, Audit 2 Part 1 |
| Classification confidence | `Resource.content_category_confidence` | `DocumentOut.contentCategoryConfidence` (`document.py:25`) | Rendered, `documents/[id]/page.tsx:191-195` | Audit 1 items 1, 6 |
| Classification confirmed flag | `Resource.content_category_confirmed` | `DocumentOut.contentCategoryConfirmed` (`document.py:26`) | Rendered, `documents/[id]/page.tsx:196-198` | Audit 1 items 1, 6 |
| **Subject confidence** | `Resource.subject_confidence` | `DocumentOut.subjectConfidence` (`document.py:28`) | **Declared in `api.ts:131`, never read in either page component** | Audit 2 Part 1 table row 6; Audit 1 item 6 |
| **Subject confirmed flag** | `Resource.subject_confirmed` | `DocumentOut.subjectConfirmed` (`document.py:29`) | **Declared in `api.ts:132`, never read anywhere** | Audit 2 Part 1 table row 7 |
| **Auto-reclassification shadow fields** | `Resource.auto_content_category(_confidence)` / `auto_subject(_confidence)` | **Absent from `DocumentOut` entirely** (`document.py:12-29`, only 8 fields exist) | N/A -- never reaches the client | Audit 1 items 1, 5, 9, 10; Audit 2 Part 1 (confirmed absent, re-verified) |
| Retrieval confidence | `Answer.retrieval_confidence` | `AnswerOut.retrievalConfidence` (`chat.py:47`) / `IntentResponse.retrievalConfidence` (`intents.py:260`) | Rendered, `chat/page.tsx:134, 194` | Audit 1 item 8, Audit 2 Part 1 |
| **Sufficiency score** | `Answer.sufficiency_score` | Present in both schemas (`chat.py:46`, `intents.py:259`) | **Declared in `api.ts`, present on the response object, never copied into `ChatMessage` state or rendered** | Audit 2 Part 1 + Part 2 table |
| **Sufficiency reason** | `Answer.sufficiency_reason` | **Absent from `AnswerOut` (`chat.py:39-50`, 8 fields) and `IntentResponse` (`intents.py:250-263`, 8 fields)** | **Absent from `api.ts`'s corresponding interfaces entirely** | Audit 1 item 8, Audit 2 Part 1 + Part 2 (both confirm absence at the schema level, not a frontend drop) |
| Manual classification correction | `PATCH /documents/{id}/classification` | Existing route, `documents.py:433-483` | Existing edit form, `documents/[id]/page.tsx:214-250` | Audit 1 item 3 |
| **Correction history (any field)** | **Does not exist anywhere in `apps/api/app/models/`** | N/A | N/A | Audit 1 item 9 (grep-confirmed, only 5 incidental comment hits, no table) |
| **Confidence-based triage (sort/filter) in document library** | N/A (would read existing fields) | N/A (existing fields already returned) | **Does not exist -- `documents/page.tsx` has only a filename-text search, no sort control, no confidence display in the table at all** | Audit 1 item 7 |
| **Re-extraction on a `READY` (non-`FAILED`) document** | N/A | **`POST /documents/{id}/retry` is hard-gated to `status == FAILED`, `documents.py:421-424`** | No such button rendered anywhere in the `READY` branch of `documents/[id]/page.tsx` | Audit 1 items 3, 6 |
| **Per-page/per-region OCR confidence** | `ResourcePage` has no confidence column at all | N/A | N/A | Audit 1 item 4 |

Bolded rows are the exact set of gaps this milestone addresses. Every
non-bolded row is confirmed **already implemented and already correctly
surfaced** -- this design makes no change to any of them.

## 4. Proposed design

Each item states: (a) the exact audit finding it closes, (b) which of
the three frontend categories it falls into where applicable --
**[Exposes existing API field]**, **[Exposes existing model field not
yet in API]**, or **[New functionality]** -- and (c) confirmation that
the backend portion, if any, is additive only.

### 4.1 New table: `resource_corrections` (the correction-history log)

**Audit basis:** Audit 1 item 9 confirmed, by grepping every file in
`apps/api/app/models/`, that no audit/history/correction table exists
anywhere in the codebase (only 5 incidental comment matches, none a
table). Audit 1 item 3 confirmed `PATCH /documents/{id}/classification`
(`documents.py:433-483`) overwrites `content_category`/`subject` with
no record of the prior value, timestamp, or what the automatic
classifier said at the time (`documents.py:472-480`, immediately
followed by `db.commit()` at line 482 with no intervening write to any
other table).

**Design (unchanged from prior draft, now grounded in the audit above):**

```
resource_corrections
  id                  UUID PK
  resource_id         FK -> resources.id, indexed
  workspace_id        FK -> workspaces.id, indexed
  field                enum: CONTENT_CATEGORY | SUBJECT
  previous_value       nullable string
  previous_confidence  nullable float
  new_value            string
  corrected_at         timestamp
```

One row inserted from inside the existing `update_classification` route
body, per changed field, immediately before or alongside the existing
`resource.content_category = ...` / `resource.subject = ...` assignments
(`documents.py:472-480`) -- capturing `resource.content_category`/
`resource.content_category_confidence` (etc.) **as they stand at that
moment, before being overwritten**. A new `GET
/documents/{id}/corrections` read-only route exposes this history.

**Additive-only confirmation:** this is a new table and a new read
route. The existing `PATCH` route's request shape, response shape, and
externally-visible behavior (fields overwritten, confidence set to
`1.0`, `_confirmed` set to `True`) are completely unchanged -- the audit
found nothing here to preserve differently than one extra `INSERT`
alongside the existing `UPDATE`.

### 4.2 Surfacing the `auto_*` reclassification signal

**Audit basis:** Audit 1 items 1, 5, 9, 10 and Audit 2 Part 1 all
independently confirm the same fact: `Resource.auto_content_category`,
`auto_content_category_confidence`, `auto_subject`,
`auto_subject_confidence` exist on the model (`resource.py:197-200`),
are written on every classification run
(`ingestion_service.py:101-104`, confirmed via direct grep in Audit 1
item 9's follow-up), and are **absent from `DocumentOut`** -- `document.py`'s
class body (lines 12-29) has exactly 8 fields, none of them `auto_*`.
Audit 2 Part 1 re-confirms this by direct read of the same 8-field
class. This is a model field that has never reached the API at all --
not a frontend gap.

**Backend [additive]:** `DocumentOut` gains four new optional fields:
`autoContentCategory`, `autoContentCategoryConfidence`, `autoSubject`,
`autoSubjectConfidence`. **[Exposes an existing model field not yet in
the API]** -- no new computation; `ingestion_service.py`'s classification
stage already produces these values every run.

**Frontend [New functionality]:** a banner on the document detail page
shown when `autoContentCategory` differs from the confirmed
`contentCategory`. This UI does not exist today in any form (Audit 1
item 6 confirmed the detail page has no reference to `auto_*` anywhere
in its 351 lines) -- this is new functionality, built on top of the
newly-exposed field above. "Use this" calls the existing
`updateClassification` client method (`api.ts:426-430`, unchanged) with
the auto value; "Keep mine" is a client-only dismissal (Open Question 3).

### 4.3 Surfacing `sufficiency_reason`

**Audit basis:** Audit 1 item 8 and Audit 2 Part 1 both confirm
`Answer.sufficiency_reason` (`answer.py:28`) has no corresponding field
in `AnswerOut` (`chat.py:39-50`, 8 fields, none named `sufficiencyReason`
or similar) or in `IntentResponse` (`intents.py:250-263`, 8 fields, same
absence). Audit 2 Part 2 additionally confirms `api.ts`'s own
`AnswerOut`/`IntentResponse` interfaces (lines 205-214, 374-383) also
lack the field -- so there is no frontend "drop" happening; the value
never leaves the backend schema layer today.

Separately, Audit 2 confirmed `sufficiencyScore` **is** already present
in both backend schemas and both `api.ts` interfaces, but is not copied
into `ChatMessage` state anywhere in `chat/page.tsx`'s `send()` function
(confirmed by reading all object-literal constructions at lines
106-123 and 126-139) and therefore never rendered. This is a distinct
finding from the `sufficiencyReason` absence and is addressed separately
below.

**Backend [additive]:** `AnswerOut` and `IntentResponse` each gain one
new optional field, `sufficiencyReason`. **[Exposes an existing model
field not yet in the API]** -- `Answer.sufficiency_reason` already
exists and is already populated by the unchanged sufficiency scorer; no
new computation.

**Frontend [New functionality + exposes an existing API field]:** two
distinct, independently addressable items, kept separate because the
audit found two distinct gaps:
1. Copy the *already-returned* `sufficiencyScore` into `ChatMessage`
   state and render it where currently dropped. **[Exposes an existing
   API field]** -- zero backend change, this field has been available
   in the response since Milestone 8.
2. A "Why?" affordance next to the confidence percentage, mapping the
   newly-exposed `sufficiencyReason` code to one of five fixed
   human-readable sentences. **[New functionality]**, dependent on 4.3's
   backend addition above.

### 4.4 Confidence-based triage view in the document library

**Audit basis:** Audit 1 item 7 confirmed, by reading the full 149-line
`documents/page.tsx`, that the only filter is a filename-text search
(lines 32-36), there is no sort control anywhere in the file, and no
confidence indicator of any kind appears in the table (columns are
Title, Category, Pages, Uploaded, Status -- lines 98-103). Audit 1 item
7 also confirmed `GET /documents` (via `listDocuments`, `api.ts:407`)
already returns `extractionConfidence`, `contentCategoryConfidence`, and
`contentCategoryConfirmed` for every document in the response.

**Frontend only, no backend change [New functionality, built entirely
on already-exposed API fields]:** a "Needs review" toggle filter and a
confidence sort control, computed client-side over the already-fetched
list (same pattern as the existing filename filter at lines 32-36), plus
a small per-row confidence indicator. Every field this reads
(`extractionConfidence`, `contentCategoryConfidence`,
`contentCategoryConfirmed`) is already present in `DocumentOut` and
already fetched by the existing `listDocuments()` call -- confirmed by
Audit 2 Part 1's table, which shows all three already flow from model to
API to the `api.ts` `DocumentOut` interface. No new query parameter, no
new route.

### 4.5 `subjectConfidence` / `subjectConfirmed` display fix

**Audit basis:** Audit 2 Part 1's table, row 6-7, is the direct source
of this item: `subjectConfidence` and `subjectConfirmed` are both
already present in `DocumentOut` (`document.py:28-29`) and already
declared in `api.ts`'s `DocumentOut` interface (lines 131-132) -- Audit
2 explicitly concluded these are "returned by the API but ignored by the
frontend," not missing from any schema.

**Frontend only, no backend change [Exposes an existing API field]:**
render `subjectConfidence` next to `subject`, exactly the way
`contentCategoryConfidence` is already rendered next to
`contentCategory` (`documents/[id]/page.tsx:191-195`). This is the one
item in this design that is purely "read a field that was already being
sent and simply display it" -- confirmed to be exactly that by Audit 2,
not partially built or ambiguous in any way.

### 4.6 Re-extraction affordance for low-confidence resources

**Audit basis:** Audit 1 items 3 and 6 confirmed: `POST
/documents/{id}/retry` exists but is hard-gated --

```python
# documents.py:421-424
if resource.status != ResourceStatus.FAILED:
    raise AppError(
        status.HTTP_409_CONFLICT, "DOCUMENT_NOT_FAILED", "Only failed documents can be retried."
    )
```

-- and there is no route anywhere in `documents.py` (all 484 lines read
in full during Audit 1) that allows re-running extraction on a `READY`
document. Audit 1 item 6 confirmed the document detail page's
extraction-confidence badge (`documents/[id]/page.tsx:202-206`) has no
associated action -- the only retry-adjacent button on that page
(`onRetry`, lines 79-89) is rendered exclusively inside the
`status === "FAILED"` branch (line 156), never alongside the
extraction-confidence badge in the `READY` branch.

**Revision from the prior draft:** the prior version of this design
proposed loosening `/retry`'s existing `FAILED`-only guard to also
accept `READY`. Per the requirement that every backend change in this
milestone be additive only, that approach is dropped -- widening an
existing endpoint's accepted-state contract is a behavior change to a
frozen Milestone 3/5 route, not an addition. Instead:

**Backend [additive]:** a new route, `POST
/documents/{id}/reextract`, accepting only `status == READY`
(`404`/`409`-style guards mirroring `retry_document`'s existing pattern
for the `FAILED`/not-found cases, but never touching `retry_document`
itself). Sets status back to `QUEUED` and re-runs the identical
`_run_ingestion` background task already used by both `upload_document`
and `retry_document` (`documents.py:264-271`) -- no new extraction logic,
no new job step, and zero lines changed in the existing `retry_document`
function or its route.

**Frontend [New functionality]:** a "Re-run extraction" button next to
the extraction-confidence badge, calling the new endpoint. This did not
exist in any form before (Audit 1 item 6).

### 4.7 Config additions (`app/core/config.py`)

```
# -- Milestone 11 (Confidence & Correction UX) --
LOW_CONFIDENCE_THRESHOLD: float = 0.5  # shared triage/badge threshold
```

Not tied to a specific audit finding beyond Section 3's general
observation that no such threshold exists anywhere today (`grep`-level
absence, not a cited line, since there's nothing to cite for something
that doesn't exist).

### 4.8 API changes summary (all additive)

- `PATCH /documents/{id}/classification` (existing route,
  `documents.py:433-483`): unchanged request/response; additionally
  inserts `resource_corrections` row(s). [Audit 1 items 3, 9]
- `GET /documents/{id}/corrections` (new route). [Audit 1 item 9]
- `POST /documents/{id}/reextract` (new route, `retry_document` and its
  route are completely untouched). [Audit 1 items 3, 6]
- `DocumentOut` (existing schema, `document.py:12-29`): four new
  optional fields. [Audit 1 items 1, 9, 10; Audit 2 Part 1]
- `AnswerOut` (`chat.py:39-50`) / `IntentResponse` (`intents.py:250-263`):
  one new optional field each, `sufficiencyReason`. [Audit 1 item 8;
  Audit 2 Part 1 + Part 2]

### 4.9 Database/schema changes summary

- One new table: `resource_corrections` (migration
  `0009_confidence_correction_ux.py`). [Audit 1 item 9]
- No changes to `Resource`, `Answer`, `Concept`, or any other existing
  table or column -- every field this milestone surfaces already exists
  (Section 3).

### 4.10 Frontend changes summary (classified per Section 4's labels)

| Change | Classification | Backend dependency |
|---|---|---|
| Correction-history list on document detail page | New functionality | 4.1 (new `GET` route) |
| Reclassification-suggestion banner | New functionality | 4.2 (new `DocumentOut` fields) |
| `sufficiencyScore` rendered in chat (currently dropped) | Exposes an existing API field | None |
| "Why?" sufficiency-reason affordance in chat | New functionality | 4.3 (new schema field) |
| "Needs review" filter + sort + indicator in document library | New functionality | None -- built on already-exposed fields |
| `subjectConfidence`/`subjectConfirmed` display | Exposes an existing API field | None |
| "Re-run extraction" button | New functionality | 4.6 (new route) |

### 4.11 Interaction with retrieval, intent, and study systems

- **Retrieval (M8):** read-only consumer of `Answer.sufficiency_reason`,
  confirmed by Audit 1 item 8 to already exist and already be computed
  by the unchanged `services/sufficiency.py`. No change to
  `retrieval_service.py`, the sufficiency formula, or provenance logic.
- **Intent workflows (M9/M10):** `IntentResponse` gains
  `sufficiencyReason` as a new optional field; every existing intent
  handler's construction of an `IntentResponse` continues to work
  unchanged (Pydantic optional-field defaults), matching the same
  pattern Milestone 10 used adding its own optional envelope fields.
- **Study workflows (M10):** no interaction. Quiz/Viva grading doesn't
  go through `compute_sufficiency()`; Revision mode's
  `assess_review_need()` is a separate, already-existing signal this
  milestone does not touch or extend.
- **Concept graph (M7):** no interaction. `resource_corrections` is
  scoped to `Resource.content_category`/`subject` only, not concepts;
  `Concept.merged_into_concept_id` (a pre-existing, unrelated
  single-FK audit mechanism) is untouched.

## 5. UI/UX flow (confidence & correction, end to end)

1. A resource finishes ingestion with automatic classification and, if
   OCR'd, an extraction confidence -- both unchanged, pre-existing
   behavior (Section 3).
2. **Library view:** the user opens `/documents` and can filter to
   "Needs review" or sort by lowest confidence (Section 4.4) -- built
   entirely on fields the API already returns today.
3. **Detail view:** the user sees `subjectConfidence` for the first time
   (Section 4.5, a pure display fix), a new banner if the ongoing
   automatic reclassification disagrees with the saved value (Section
   4.2), and a correction-history list (Section 4.1).
4. The user corrects a field via the existing, unchanged `PATCH` flow --
   this now additionally appends a `resource_corrections` row.
5. If extraction confidence is low, the user can trigger a fresh
   extraction pass via the new `POST /documents/{id}/reextract` endpoint
   without touching the existing `/retry` route at all (Section 4.6).
6. **Chat:** the user sees the previously-dropped `sufficiencyScore`
   rendered, and can expand "Why?" to see the newly-exposed
   `sufficiencyReason` mapped to a plain-language sentence (Section 4.3).

## 6. Design decisions (approved)

These were genuine product/scope decisions the audit could not answer on
its own; all five were approved exactly as proposed, no changes.

**1. Low-confidence threshold value -- APPROVED: `0.5`, one shared
setting.** `LOW_CONFIDENCE_THRESHOLD: float = 0.5` in `app/core/config.py`,
used identically for extraction and classification triage (Section 4.7),
mirrored client-side as `LOW_CONFIDENCE_THRESHOLD` in `lib/api.ts` since
there is no config-exposing endpoint.

**2. Endpoint shape for re-extraction -- APPROVED: a wholly new,
additive `POST /documents/{id}/reextract` route**, rather than a query
parameter on the existing `/retry` route. Implemented exactly as
specified: `retry_document` and its route have zero lines changed (see
Section 13, review finding on the resulting minor code duplication and
why it was kept this way).

**3. "Keep mine" persistence -- APPROVED: no persistence.** Implemented
as a client-only dismissal (`suggestionDismissed` state in
`documents/[id]/page.tsx`), reset on page reload. `resource_corrections`
still gives a natural place to add a `DISMISSED` outcome later if this
proves annoying in practice, without any schema change.

**4. Scope of `resource_corrections` -- APPROVED: classification only.**
`CorrectionField` is `CONTENT_CATEGORY | SUBJECT` only, matching the
approved schema exactly (Section 4.1).

**5. Chat-answer feedback mechanism -- APPROVED: out of scope, not
built.** No thumbs-up/down or "flag this answer" affordance exists
anywhere in the implementation -- this milestone's chat-facing surface is
exactly `sufficiencyScore` (now rendered) and `sufficiencyReason` (new,
via the "Why?" affordance), nothing more.

## 7. Non-goals for this milestone (explicitly deferred)

- Any new confidence *computation* -- confirmed by both audits that
  every confidence number already used by this milestone (extraction,
  classification, sufficiency) is real and pre-existing; nothing new is
  computed anywhere in this design.
- Active-learning classification (corrections improving the classifier
  automatically) -- no such mechanism exists today (Audit 1 items 5, 10)
  and none is proposed.
- Per-page/per-region OCR confidence -- Audit 1 item 4 confirmed
  `ImageOcrExtractor` only ever produces one `ExtractedUnit`, and
  `ResourcePage` has no confidence column at all; changing this is out
  of scope.
- Chat-answer feedback/flagging (Open Question 5).
- Correcting extracted text content itself -- only a re-run action is
  proposed (4.6), not an in-place editor; confirmed nothing like this
  exists today.
- Bulk/multi-select correction across documents -- every correction flow
  here remains one document at a time, matching the existing `PATCH`
  route's scope (Audit 1 item 3).

## 8. Trade-offs

- **A wholly new `reextract` route instead of widening `/retry`**
  (Section 4.6, revised) costs one more route/test surface but keeps
  `retry_document` (a frozen Milestone 3/5 function) at zero diff --
  chosen specifically to satisfy the "additive only" backend
  requirement rather than debate a contract change.
- **One shared `LOW_CONFIDENCE_THRESHOLD`** for both extraction and
  classification triage is simpler than two independently tunable
  numbers, at the cost of coupling what "low" means across two
  different signal types.
- **Client-side filtering/sorting in the document library** (4.4) avoids
  any backend change, at the cost of only ever operating on the
  currently-loaded page of `GET /documents` results (an existing
  limitation of that endpoint, not introduced here).

## 9. Risks

- **A correction-history table that's never read anywhere except one
  new endpoint** risks becoming another write-only hook, the same
  failure mode Audit 1 found with the pre-existing `auto_*` columns
  (items 1, 9, 10). Mitigated by scoping it to the one concrete consumer
  identified (the document detail page) rather than building further
  ahead of need.
- **The reclassification-suggestion banner** could be noisy if `auto_*`
  values fluctuate slightly without the user wanting to change their
  confirmed answer. Mitigated by Open Question 3's no-persistence
  default, revisited only if it proves annoying in practice.
- **A new `reextract` endpoint duplicating `retry_document`'s shape**
  is a real risk of near-duplicate code (both set `QUEUED`, clear
  `error_message`, call `_run_ingestion`). Mitigated by extracting the
  shared body into one internal helper both routes call, so the
  duplication is in route declarations/guards only, not in logic.

## 10. Testing strategy

- **`resource_corrections`**: migration/model test; a test that `PATCH
  .../classification` inserts one row per changed field with the
  correct pre-write `previous_value`/`previous_confidence`; a test that
  changing both fields in one request inserts two rows; a
  workspace-scoping test for `GET .../corrections` (404 cross-workspace,
  matching every other document sub-resource route).
- **`auto_*` exposure**: a test that `DocumentOut` includes the four new
  fields and reflects the latest classification run independent of
  `_confirmed` state.
- **`sufficiencyReason`**: a test that `AnswerOut`/`IntentResponse`
  include the field with one of the five known reason codes.
- **`POST /documents/{id}/reextract`**: success case on `READY`;
  rejection on `FAILED`/`QUEUED`/`PROCESSING`; **full regression of every
  existing `/retry` test unchanged** (this route is not touched by this
  milestone at all, so its tests must show zero diff in behavior).
- **Frontend**: `tsc --noEmit` clean; manual verification of the triage
  filter/sort, correction-history list, suggestion banner, "Re-run
  extraction" button, and chat "Why?"/`sufficiencyScore` display.
- Full existing suite (all M1-M10 tests) must continue passing
  unchanged.

## 11. Implementation plan (once this design is approved)

1. Add `resource_corrections` model + `CorrectionField` enum + Alembic
   migration `0009_confidence_correction_ux.py`.
2. Extend `PATCH /documents/{id}/classification` to insert a correction
   row per changed field; add `GET /documents/{id}/corrections`.
3. Add the four `auto_*` fields to `DocumentOut`.
4. Add `sufficiencyReason` to `AnswerOut` and `IntentResponse`.
5. Add `LOW_CONFIDENCE_THRESHOLD` to `app/core/config.py`.
6. Add `POST /documents/{id}/reextract` (new route; `retry_document`
   untouched), factoring the shared requeue logic into one internal
   helper both routes call.
7. Frontend: correction-history list + suggestion banner +
   `subjectConfidence`/`subjectConfirmed` display + "Re-run extraction"
   button on the document detail page.
8. Frontend: render the already-returned `sufficiencyScore` in chat
   (currently dropped) + "Needs review" filter + confidence sort + per-
   row indicator on the document library page.
9. Frontend: "Why?" affordance on the chat provenance badge.
10. Write tests (Section 10).
11. Write ADR-0018 (Confidence & Correction UX) capturing this design's
    approved decisions and the audit findings that justified each one.
12. Update this document to "Implemented and Verified" with real
    verification results, then run the same verification loop
    Milestones 4-10 used before freezing.
13. Per the standing process note (`CONTRIBUTING.md`): update
    `README.md`'s Part 2 and Roadmap table immediately after freezing.

**Status of this plan:** steps 1-10 and 12 complete (see Sections 12-13
below). Step 11 (ADR-0018) has **not** been written yet -- flagged as an
open item to resolve before the tag/commit, consistent with every prior
milestone (4-10) having its own ADR. Step 13 (README/CHANGELOG refresh)
is explicitly deferred to its own follow-up turn, per standing process.

## 12. Verification results

Run directly against this repository (not a separate copy) under this
session's toolchain: Python 3.10.12 / Linux, Ruff 0.15.22, Black 26.5.1.
The project pins `target-version = ["py311"]` for both Ruff and Black,
so this is a known cross-version execution environment, not Sai's exact
pinned Windows/Python 3.11 toolchain -- the same caveat Milestones 4-10
documented for their own sandbox passes, and why the pre-existing
`I001`/formatting artifacts noted below (on files this milestone never
touched) are treated as environment noise rather than real findings.

- **Alembic** -- `alembic upgrade head` from a fresh schema: applies
  cleanly through `0009_confidence_correction_ux` (down_revision
  `0008_study_workflows`). `test_alembic_migrations.py`'s three schema-
  chain tests (fresh upgrade, downgrade/upgrade round-trip, stamp-then-
  upgrade) all pass with `resource_corrections` added to
  `EXPECTED_TABLES`.
- **Ruff** (`ruff check app tests alembic`) -- every new/changed file
  (`models/correction.py`, `alembic/versions/0009_...py`,
  `schemas/{document,chat,intents}.py`, `api/v1/routes/{documents,chat}.py`,
  `core/config.py`, `tests/test_confidence_correction_ux.py`,
  `tests/test_alembic_migrations.py`) is clean. The only findings
  anywhere in `app`/`tests`/`alembic` are `I001` on migrations
  `0001`-`0008`, `env.py`, `conftest.py`, and `test_alembic_migrations.py`
  (none touched this milestone, all pre-existing from Milestones 4-10's
  own sandbox passes) plus pre-existing `E501`s in
  `0002_resource_content_model.py` -- unchanged from before this
  milestone.
- **Black** (`black --check app tests alembic`) -- every new/changed
  file unchanged/clean. The only files Black would reformat are
  `0002_resource_content_model.py` and `services/embeddings.py`, both
  pre-existing, both flagged only because of the Python 3.10-vs-3.11
  safety-check warning noted above (the same artifact Milestone 10's
  Section 8.1/8.2 already traced to this exact cause and confirmed
  clean under the real pinned toolchain).
- **Pytest** -- full suite run in batches (this sandbox's per-call time
  limit requires batching, not a code issue): every batch passed, 0
  failures, across all M1-M10 tests plus this milestone's 18 new tests
  in `test_confidence_correction_ux.py` (correction-history insert/read/
  workspace-isolation, `auto_*` field exposure surviving reclassification,
  `reextract` success/rejection cases, `sufficiencyReason` presence on
  both `AnswerOut` and `IntentResponse`) and the two explicit `/retry`
  regression tests in `test_ingestion.py` (`test_retry_still_rejects_...`
  and `test_retry_still_reprocesses_...`, both passing unchanged).
- **Frontend** -- `tsc --noEmit`: 0 errors across `lib/api.ts`'s
  extensions and the three edited pages (`documents/[id]/page.tsx`,
  `documents/page.tsx`, `chat/page.tsx`). `npm run build` could not be
  completed within this environment's per-call time limit (the same
  sandbox-tooling limitation Milestone 10's Section 8.1 documented, not
  a known code issue) -- **outstanding**, should be run once for real
  confirmation before or alongside the actual commit/tag.

No findings were invented and no pre-existing/frozen-file findings were
silently fixed, consistent with the verification discipline used in
Milestones 4 through 10.

## 13. Implementation review findings (pre-freeze audit)

Before approving the freeze, every changed file was re-read fresh
against this document and checked for: scope creep, additive-only
compliance, unintended changes to frozen milestone behavior, dead code/
duplication/TODOs/debug logging, docstring consistency on new endpoints,
whether every new schema field is actually populated and consumed,
model/migration/test completeness for the new DB object, cross-
workspace leakage on the correction history, and anything in the git
diff that shouldn't be committed. Findings:

- **No scope additions, no additive-only violations, no frozen-behavior
  regressions.** Every backend/frontend change traces to a specific
  Section 4 item; `retry_document` and its route have zero lines
  changed (confirmed by diff and by the two regression tests above).
- **Workspace isolation confirmed safe.** `GET /documents/{id}/corrections`
  filters by `resource_id` only, not `workspace_id` directly -- safe by
  construction, since the route's upfront `resource.workspace_id !=
  workspace.id -> 404` check (identical to every other document sub-
  resource route) guarantees any `resource_id` reaching the query already
  belongs to the caller's workspace. `resource_corrections.workspace_id`
  is still stored (matching the approved schema) and is set correctly
  from `resource.workspace_id` at insert time. Exercised directly by
  `test_corrections_route_respects_workspace_isolation`.
- **Two inaccurate code comments, fixed.** `schemas/intents.py` and
  `lib/api.ts` both had a comment on `IntentResponse.sufficiencyReason`
  incorrectly claiming it was already populated for EXPLAIN/SEARCH/
  SUMMARIZE/COMPARE's freeform paths. In reality no intent handler was
  modified (per the approved design), so the field is unconditionally
  `None`/`undefined` for every intent today -- confirmed accurate by
  `test_intent_response_includes_sufficiency_reason_key`, which
  documents exactly this. Both comments corrected to state the field is
  additive, forward-compatible schema plumbing, not live end to end yet.
- **One unreachable defensive branch, simplified.** `routes/chat.py`'s
  `AnswerOut(...)` construction had
  `sufficiencyReason=answer.sufficiency_reason or None` -- `answer.
  sufficiency_reason` is always freshly set to one of the five non-empty
  reason codes by `retrieval_service.answer_question()` in this exact
  call path, so the `or None` fallback could never trigger. Simplified
  to a direct assignment.
- **One missing documentation paragraph, added.** `routes/documents.py`'s
  module docstring has accumulated one short paragraph per milestone
  that touched it (Milestones 4-7); this milestone's changes (four route
  edits/additions) didn't get one. Added.
- **Minor accepted trade-off, not changed:** `reextract_document` and
  `retry_document` share a near-identical 3-line requeue body (set
  `QUEUED`, clear `error_message`, enqueue `_run_ingestion`), duplicated
  rather than factored into one shared helper both call. This was a
  deliberate choice: the approved design's Section 4.6 and Design
  Decision 2 explicitly and repeatedly require `retry_document`'s
  function body to have zero diff, which takes precedence over the
  Implementation Plan's own step 6 wording ("factoring... into one
  internal helper both routes call"). A helper only `reextract_document`
  calls wouldn't reduce cross-route duplication anyway, so the 3-line
  body was left inline rather than introduced as an unused abstraction.
- **Pre-existing, out of scope, left untouched:** an unused
  `const router = useRouter()` in `documents/[id]/page.tsx` predates this
  milestone.
- **Git hygiene:** the entire repository initially appeared modified,
  but every file outside this milestone's actual changes was a file-
  mode-only change (100644->100755, zero content diff, confirmed file-
  by-file including binaries) -- not a real change, not staged. Three
  untracked build artifacts from running `tsc`/`npm install` during
  verification (`apps/web/next-env.d.ts`, `apps/web/tsconfig.tsbuildinfo`,
  `apps/web/package-lock.json`) are not gitignored by this repo's minimal
  `apps/web/.gitignore` and were not staged either.

All four fixes were re-verified (Ruff, Black, the full
`test_confidence_correction_ux.py` suite, `test_chat_citations.py`,
`test_intent_envelope.py`, and `tsc --noEmit`) after being applied --
all clean/passing.
