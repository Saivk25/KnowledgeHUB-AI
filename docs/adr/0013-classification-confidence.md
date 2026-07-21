# ADR-0013: Classification & confidence (Milestone 6)

**Status:** Accepted (Milestone 6)

**Decision:** Add a `Classifier` registry (`app/services/classification.py`)
mirroring `EmbeddingProvider`/`LLMProvider` exactly: a small interface, a
dependency-free `LocalHeuristicClassifier` default, and an
`OpenAIClassifier` auto-selected only when `CLASSIFICATION_PROVIDER=openai`
and `OPENAI_API_KEY` is set. Classification runs as a new `CLASSIFYING`
ingestion stage between extraction and chunking, using the same
`IngestionJob.step` tracking already built in Milestone 3.

## Sub-decisions

**1. Fixed, non-configurable 7-category taxonomy.** `LECTURE`,
`ASSIGNMENT`, `QUESTION_PAPER`, `LAB_MANUAL`, `RESEARCH_PAPER`,
`PERSONAL_NOTE`, `OTHER` -- taken directly from the original PRD's FR-1
list of content categories layered on top of file formats. Approved as
fixed for this milestone; expanding it or making it user-configurable is
explicitly out of scope.

**2. `LocalHeuristicClassifier` only attempts `content_category`, never
`subject`.** Category has real lexical signal (keyword/phrase rules like
"abstract"/"references" → `RESEARCH_PAPER`, "lab manual"/"procedure" →
`LAB_MANUAL`). Subject/topic detection from raw word frequency would be a
much weaker signal, and DRR Section 9 is explicit that a confidence number
attached to a guess that doesn't correlate with real accuracy is worse than
no number at all. So the local classifier honestly leaves
`subject`/`subject_confidence` as `(None, None)` -- real subject detection
only happens through the OpenAI-backed classifier, which has an actual
chance of being right.

**3. Confidence formula is a documented, deterministic function of matched
rules, not an invented number.** Each category has a table of `(pattern,
weight)` rules; a category's raw score is the sum of matched weights;
confidence is that score linearly mapped into `[0.35, 0.95]` against a
fixed `_MAX_EXPECTED_SCORE` constant (`classification.py`). A resource with
no matching rule at all gets `OTHER` at a flat `0.2` -- an honest "we
really don't know," not a fabricated mid-range number. `OpenAIClassifier`'s
confidence is literally the number the model reports in its JSON response,
unmodified.

**4. Classifier failure never fails the resource (approved design).**
Classification is enrichment metadata, not a prerequisite for a resource
being usable -- a resource is fully searchable without it. On any
exception from `get_classifier().classify(...)`,
`ingestion_service.py` logs a warning and substitutes
`Classification(category=OTHER, category_confidence=0.0)`, and the
pipeline proceeds to chunking/embedding/indexing exactly as if
classification had produced a low-confidence result. This is a deliberate
asymmetry with extraction failures (which do fail the resource, via
`ExtractionError`) -- extraction failing means there is no usable content
at all; classification failing means only the enrichment layer is
degraded.

**5. Two parallel column layers, not one, and not a lock.** The original
design proposed a `_confirmed` flag that would permanently stop automatic
reclassification once a user corrected a field. The approved revision is
different and more flexible: `content_category`/`subject` (+ confidences +
`_confirmed` flags) are the **authoritative, user-facing** values; a
second set, `auto_content_category`/`auto_subject` (+ confidences), always
reflects the **most recent automatic classifier run**, regardless of
confirmation state. `_apply_classification()` in `ingestion_service.py`
always writes the `auto_*` columns; it only writes the authoritative
columns when the corresponding `_confirmed` flag is `False`. This means:
automatic classification keeps running on every (re)ingestion and its
result is preserved for future evaluation/logging or a possible
"suggest an updated classification" workflow, but it can never silently
overwrite what a user has explicitly confirmed. The user-facing value
shown by the API and the UI is always the authoritative one.

**6. Manual correction via `PATCH /documents/{id}/classification`,
not a new resource or a bulk endpoint.** Body accepts `contentCategory`
and/or `subject`; at least one is required (422 `EMPTY_UPDATE`);
`contentCategory` is validated against the fixed taxonomy (422
`INVALID_CATEGORY`). Setting either field sets `confidence=1.0` and
`confirmed=True` for that field -- a user's correction is definitionally
certain. Same workspace-scoped auth as every other document route.

**7. `extraction_confidence` (Milestone 5's field) is finally surfaced**
in `DocumentOut`/the frontend, per the roadmap's explicit Milestone 6
requirement ("extraction-confidence surfaced for OCR'd content"). It was
stored but unexposed since M5.

**Alternatives considered:** An adaptive "try local first, escalate to the
LLM only when confidence is low" hybrid classifier was considered (per the
original PRD's cost/latency mitigation note) but not built this milestone
-- it adds real complexity (two-pass logic, a threshold to tune) beyond
what a static, config-selected provider (identical to how
`EMBEDDING_PROVIDER`/`LLM_PROVIDER` already work) delivers for the approved
scope. Revisit if classification cost/latency at scale ever makes the
static local-or-OpenAI split insufficient.

**Revisit when:** Milestone 7's concept graph work may want to consume
`subject` as a seed signal for concept matching; Milestone 10/11's
"Confidence & Correction UX" may want a richer correction history (this
milestone stores only the latest automatic result, not a full log of every
past automatic classification).
