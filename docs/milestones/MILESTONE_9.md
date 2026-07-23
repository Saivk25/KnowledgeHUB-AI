# Milestone 9: Intent Workflows (Explain, Compare, Summarize, Search)

**Status: Implemented and Verified.**

Design approved; all four intents (Explain, Search, Summarize, Compare)
implemented per the design below via the `IntentHandler` plugin registry,
tested, and verified against a real local environment (deps, Alembic,
pytest, Ruff, Black, Docker Compose, frontend build). See Section 8 for
verification results. Ready to freeze as `v0.9.0-intent-workflows`.

---

## 1. Scope

Per `KnowledgeOS_Architecture_PRD_Roadmap.md` Section 8, Milestone 9 is:

> **Intent Workflows** -- Explain, Compare, Summarize, Search as the first
> four (closest to plain retrieval); each with its own contract and prompt
> template.

FR-8 (PRD Section 7.5) specifies nine intents total; this milestone
builds the first four -- the more structurally complex five (Quiz me,
Flashcards, Viva mode, Revision mode, Study planner) are Milestone 10,
deliberately sequenced after because each of those has its own output
schema (front/back pairs, a schedule, scored questions) and shouldn't be
designed until the shared intent infrastructure this milestone builds is
proven on the simpler four.

## 2. Governing constraints reviewed

- **DRR Section 4 (Extensibility, Important)** -- explicit, load-bearing
  finding for this milestone: *"Define one common `IntentRequest`/
  `IntentResponse` envelope (shared fields: intent type, provenance,
  confidence; per-intent payload) before the first intent workflow (M9)
  is built, so all nine share it from the start rather than converging
  on it retroactively."* This is the single biggest structural decision
  in this design (Section 3.1 below) -- it is a requirement, not an
  option.
- **Architecture Section 6, decision 5** -- "Intent Router replaces 'the
  chat endpoint.'" Each intent is a distinct pipeline (different
  retrieval parameters, prompt template, output schema) sharing the same
  underlying retrieval layer -- explicitly *not* one generic endpoint
  with a mode flag.
- **FR-2/3/4/9/10 still apply per intent**: local-first retrieval,
  sufficiency-gating, structural provenance, surfaced confidence, and
  "no hallucinated local knowledge" are not Explain-specific -- every
  intent that touches the user's own workspace must honor them.
- **ADR-0003** (dense-only retrieval, no reranker) -- unchanged, still in
  force for every intent's underlying search.
- **ADR-0004** (provider fallback pattern: zero-config local default,
  opt-in OpenAI) -- extended again here, same shape as Milestone 8's
  `answer_general_knowledge()` addition.
- **ADR-0015** (provenance is structural, exactly `LOCAL`/`HYBRID`/
  `EXTERNAL`) -- this milestone is the first real stress test of that
  3-value contract, because Compare can have *some* evidence for one
  side and *none* for another. See Open Question 2 (Section 4).
- **DRR Section 8 (API Design)** -- "one contract, thin wrapper" applies
  here by the same logic it applied to `/documents` vs. `/capture`: the
  existing `/conversations/{id}/messages` endpoint must not become a
  second, divergent implementation once intent dispatch exists elsewhere.

## 3. Proposed design

### 3.1 Shared envelope (the DRR Section 4 mandate)

```python
class IntentType:
    EXPLAIN = "EXPLAIN"
    COMPARE = "COMPARE"
    SUMMARIZE = "SUMMARIZE"
    SEARCH = "SEARCH"
    # Reserved, not implemented this milestone: QUIZ, FLASHCARDS, VIVA,
    # REVISION, STUDY_PLAN (Milestone 10).

class IntentRequest(BaseModel):
    intent: Literal["EXPLAIN", "COMPARE", "SUMMARIZE", "SEARCH"]
    question: str | None = None          # EXPLAIN, SEARCH, freeform SUMMARIZE
    resourceId: str | None = None        # SUMMARIZE (single target)
    conceptId: str | None = None         # SUMMARIZE (single target)
    targets: list[CompareTarget] | None = None   # COMPARE (2+ targets)
    useExternalFallback: bool = False

class CompareTarget(BaseModel):
    label: str                            # user-facing name for this side
    resourceId: str | None = None
    conceptId: str | None = None
    question: str | None = None           # freeform phrase, if neither id given

class IntentResponse(BaseModel):
    intent: str
    status: str                # OK | INSUFFICIENT | ERROR
    provenance: str | None     # LOCAL | HYBRID | EXTERNAL | None
    sufficiencyScore: float
    retrievalConfidence: float
    canOfferExternalFallback: bool
    citations: list[CitationOut]
    result: ExplainResult | CompareResult | SummarizeResult | SearchResult
```

`result` is a discriminated union -- each intent gets its own typed
payload (a compare breakdown, a ranked hit list, etc.) while the six
fields above it are identical across all four (and, per DRR Section 4,
all nine, eventually). This is the contract every intent shares from day
one, per the DRR finding, rather than four independently-shaped
responses that would need retrofitting when Milestone 10 arrives.

### 3.2 One new route, one thin existing wrapper

```
POST /api/v1/conversations/{id}/intents
```

Body: `IntentRequest`. Response: `IntentResponse`. This is the one real
implementation -- every intent's dispatch goes through it.

`POST /api/v1/conversations/{id}/messages` (existing, Milestone 8) is
kept **unchanged from the frontend's point of view**, but internally
becomes a thin wrapper: it constructs an `IntentRequest(intent="EXPLAIN",
question=payload.content, useExternalFallback=payload.useExternalFallback)`,
calls the same dispatch function `/intents` calls, and translates the
`IntentResponse` back into the existing `SendMessageResponse`/`AnswerOut`
shape. This is DRR Section 8's "one contract, thin wrapper" principle
applied here: the existing chat UI keeps working with zero frontend
changes, and there is exactly one code path computing an Explain answer,
not two.

### 3.3 New service layer: `app/services/intents/` (plugin registry, not a branching dispatcher)

**Amended per your review comment (approved along with the rest of this
design):** rather than one `dispatch_intent()` function with an
if/elif per intent, this mirrors the `Extractor`/`Classifier`/
`ConceptLinker` plugin-registry pattern already established in this
codebase (`app/services/extraction.py`, `classification.py`,
`concept_linking.py`) applied one layer later in the pipeline:

```python
# app/services/intents/base.py
class IntentHandler(ABC):
    intent_type: str

    @abstractmethod
    def handle(self, db: Session, workspace: Workspace, request: IntentRequest) -> IntentResult: ...

# app/services/intents/explain.py   -> class ExplainIntent(IntentHandler)
# app/services/intents/search.py    -> class SearchIntent(IntentHandler)
# app/services/intents/summarize.py -> class SummarizeIntent(IntentHandler)
# app/services/intents/compare.py   -> class CompareIntent(IntentHandler)

# app/services/intents/registry.py
_HANDLERS: dict[str, IntentHandler] = {
    IntentType.EXPLAIN: ExplainIntent(),
    IntentType.SEARCH: SearchIntent(),
    IntentType.SUMMARIZE: SummarizeIntent(),
    IntentType.COMPARE: CompareIntent(),
}

def get_intent_handler(intent_type: str) -> IntentHandler:
    handler = _HANDLERS.get(intent_type)
    if handler is None:
        raise ValueError(f"Unknown intent type: {intent_type}")
    return handler
```

Each `IntentHandler` is responsible for its own orchestration end to end
(which evidence-resolution helpers it calls, which `LLMProvider` method
it invokes, how it shapes its own `result` payload) while all four share
the same underlying retrieval primitives (Section 3.4's evidence-
resolution helpers, `compute_sufficiency`, `get_llm_provider`) -- adding
a fifth intent in Milestone 10 means adding one new file and one
registry entry, never touching the other four or a shared branching
function. The route (Section 3.2) and the `/messages` wrapper both call
`get_intent_handler(request.intent).handle(db, workspace, request)` and
nothing else -- routing logic lives in the registry, not in the route.

- **EXPLAIN** -- calls `retrieval_service.answer_question()` unchanged.
  No behavior change from Milestone 8; this is purely a routing wrapper.
- **SEARCH** -- new. Reuses `retrieval_service._build_candidates()` /
  `_score_candidates()` (made non-private or re-exported), and **always
  returns the ranked hit list** (top-`SEARCH_TOP_K` scored candidates as
  citations, no gating) -- an empty result set is itself the honest
  answer ("nothing in your workspace matches"), not an error. On top of
  that baseline, per your decision (Section 4), Search **conditionally**
  calls the LLM:
  - Compute `compute_sufficiency(scored).score` the same way Explain
    does, but only to decide whether to *additionally* synthesize --
    never to gate whether ranked hits are returned at all.
  - **Score >= `SEARCH_LLM_CONFIDENCE_THRESHOLD`** (confident match):
    return ranked hits only, `assistedSynthesis: None`. Zero LLM calls,
    zero added latency/cost -- this is the common case for a well-matched
    query.
  - **Score < `SEARCH_LLM_CONFIDENCE_THRESHOLD`** but at least one
    candidate exists (ambiguous/low-confidence match): additionally call
    `llm.answer()` (the same grounded, cite-by-`[n]` method Explain uses
    -- no new LLM method needed) and populate `assistedSynthesis` with a
    clearly-labeled "low-confidence, here's my best synthesis of what
    was found" note alongside the still-present raw ranked hits. This
    synthesis is grounded only in the same retrieved evidence -- it
    cannot introduce anything Search's own retrieval didn't find, so
    FR-10 still holds.
  - **No candidates at all**: `assistedSynthesis: None`, empty hits,
    `provenance: None` -- no LLM call, nothing to synthesize from.
  - `provenance` is always `"LOCAL"` whenever any results exist (with or
    without `assistedSynthesis`), `None` when there are none. External
    fallback never applies to Search -- the confidence-triggered
    synthesis above is still grounded entirely in the user's own
    workspace, not general knowledge, so it doesn't warrant `HYBRID`/
    `EXTERNAL`.
- **SUMMARIZE** -- new, three modes based on which field is set:
  - `resourceId` given: pulls that resource's chunks in page/chunk order
    (not similarity-ranked -- the point is completeness of one document,
    not relevance ranking), calls the new `llm.summarize()`. Sufficiency
    scoring is **bypassed**: the resource is explicitly the user's own
    (already `READY`, i.e. already extracted/chunked), so evidence
    existing is true by construction, not something to score. Always
    `provenance="LOCAL"`.
  - `conceptId` given: pulls all evidence chunks linked to that concept
    via `ResourceConcept.evidence_chunk_id` (capped at
    `SUMMARIZE_MAX_EVIDENCE_CHUNKS`, ordered by `ResourceConcept.confidence`
    descending), across every resource that evidences it. Same rationale
    for bypassing sufficiency: `concept_graph.py`'s own invariant is that
    a concept is never created without at least one evidence link (see
    `resolve_concept`), so a concept summarization target always has
    evidence to summarize. Always `provenance="LOCAL"`.
  - Neither given, `question` given: identical path to Explain's
    retrieval (hybrid vector + concept expansion), through the real
    sufficiency gate -- a freeform "summarize what I know about X" can
    genuinely have zero local coverage, so FR-10 fully applies here,
    unlike the two explicit-target modes above.
- **COMPARE** -- new. For each `CompareTarget` in `targets` (2-4, see
  `COMPARE_MAX_TARGETS`), independently resolves evidence using the same
  three resolution modes Summarize uses (resource / concept / freeform
  question) -- refactored into one shared helper both intents call, so
  there is one implementation of "resolve evidence for a named target,"
  not two. Calls the new `llm.compare()` with a per-target evidence
  bundle. See Open Questions 1 and 2 for how partial evidence gaps and
  the response's `provenance` value are meant to work -- these need your
  decision before implementation.

### 3.4 LLM provider extension (`app/services/llm.py`)

Two new abstract methods on `LLMProvider`, mirroring `answer_general_knowledge()`'s
Milestone 8 pattern (both providers implement both; the extractive
fallback is honest about its own limits, never fabricates synthesis):

```python
@abstractmethod
def summarize(self, target_label: str, evidence: list[EvidenceChunk]) -> str: ...

@abstractmethod
def compare(self, targets: list[ComparisonEvidence]) -> str: ...
```

- `OpenAIChatProvider`: two new prompt templates (`SUMMARIZE_SYSTEM_INSTRUCTIONS`,
  `COMPARE_SYSTEM_INSTRUCTIONS`), same citation-by-`[n]` discipline as
  the existing `answer()` prompt -- summarize/compare must cite evidence
  exactly like Explain does, not switch to an uncited "essay" style.
- `ExtractiveFallbackProvider`: `summarize()` concatenates the evidence
  excerpts with a explicit disclaimer that no synthesis model is
  configured (same honesty pattern as its existing `answer()` and
  `answer_general_knowledge()`); `compare()` lists each target's
  excerpts side by side under its label, again without claiming any
  synthesized comparison happened.

### 3.5 Schema/DB changes

- `Answer.intent: Mapped[str]` -- `String(20)`, `default="EXPLAIN"` (so
  every existing row remains valid with no backfill needed).
- `Answer.intent_payload: Mapped[str | None]` -- `Text`, nullable. Stores
  intent-specific structured extras that don't fit the `Citation` table
  (e.g. Compare's per-target sufficiency verdicts, Search's raw hit
  count before truncation) as a JSON string -- deliberately `Text`, not a
  new JSONB column type, to match this codebase's existing convention of
  using `Resource.type_metadata`-style JSON-in-Text/JSONB only where a
  real per-type schema exists (documented inline, same discipline as
  `type_metadata`).
- `Citation.target_label: Mapped[str | None]` -- `String(100)`, nullable.
  Lets Compare (and concept-targeted Summarize) attribute a citation to
  a specific side/source (e.g. `"Resource A"`, `"Gradient Descent"`)
  without a new table. `None` for Explain/Search/resource-Summarize,
  where there is only one side.
- New Alembic migration `0007_intent_workflows.py` adding these three
  columns, with a `downgrade()` that drops them.

No changes to `Resource`, `Concept`, `ResourceConcept`, or
`ConceptRelationship` -- Compare and Summarize read existing concept/
resource data, they don't need new graph structure.

### 3.6 Config additions (`app/core/config.py`)

Following the existing per-milestone grouping convention:

```python
# -- Milestone 9 (Intent Workflows) --
SEARCH_TOP_K: int = 10
# Below this sufficiency-style score, Search additionally calls the LLM
# for a grounded, clearly-labeled low-confidence synthesis on top of the
# always-returned ranked hits (approved design, Section 4 Q3). At or
# above it, Search never calls an LLM at all.
SEARCH_LLM_CONFIDENCE_THRESHOLD: float = 0.35  # == SUFFICIENCY_MIN_SCORE by default
SUMMARIZE_MAX_EVIDENCE_CHUNKS: int = 20
COMPARE_MAX_TARGETS: int = 4
COMPARE_MAX_EVIDENCE_PER_TARGET: int = 8
```

### 3.7 Frontend changes (more surface than Milestone 8 needed)

Milestone 8 only added a badge to existing chat; this milestone adds
real new UI entry points, per FR-8 ("each a distinct entry point with
its own UI affordance"):

- **Chat compose bar**: a small intent toggle -- Explain (default) /
  Search -- since both operate on a single freeform question and fit
  naturally into the existing chat flow.
- **Resource detail page** (`/documents/[id]`): a "Summarize this
  document" button opening a summary panel (calls `/intents` with
  `intent=SUMMARIZE, resourceId`).
- **Concept detail page** (`/concepts/[id]`): a "Summarize what I know
  about this" button (same intent, `conceptId` instead).
- **Concepts list page** (`/concepts`): multi-select 2-4 concepts ->
  "Compare" action, opening a comparison view with per-target citation
  grouping (reusing `target_label`).
- The existing `ProvenanceBadge` component (Milestone 8) is reused as-is
  for Explain/Search/Summarize; Compare's view renders one badge per
  target plus one overall badge (see Open Question 2).

## 4. Design decisions (approved)

**1. Compare and partial evidence -- APPROVED: proceed, label the gap.**
If one target has local evidence and another has none, the comparison
proceeds: the side with no local evidence is clearly labeled as such
(and can offer per-target external fallback), never silently filled.
"I have nothing on X, but here's what I know about Y" is itself useful
and honest -- refusing the entire comparison because one side is thin
would discard the side that does have real evidence.

**2. Provenance shape for Compare -- APPROVED: keep 3 values, nest
detail.** The top-level `provenance` stays a single value equal to the
"worst case" across targets (any target requiring external fallback
makes the whole answer `HYBRID`/`EXTERNAL`; all-local targets make it
`LOCAL`), with per-target granularity recorded in `intent_payload`
(Section 3.5) instead of widening the enum. ADR-0015's existing 3-value
contract is unchanged; the per-target detail is additive.

**3. Search and the LLM -- APPROVED (your explicit direction, not the
original recommendation): conditional, confidence-triggered.** Search
always returns its ranked hit list with zero gating. When the top
result's score is at or above `SEARCH_LLM_CONFIDENCE_THRESHOLD`, that's
the whole answer -- no LLM call. When it's below that threshold but at
least one candidate exists, Search *additionally* calls the LLM (reusing
the existing grounded `answer()` method, not a new one) to produce a
clearly-labeled, evidence-grounded `assistedSynthesis` alongside the
still-visible raw hits -- see the updated Section 3.3 and the new
`SEARCH_LLM_CONFIDENCE_THRESHOLD` setting (Section 3.6). This still
respects FR-10: the synthesis can only draw on evidence Search's own
retrieval already surfaced, never general knowledge, so `provenance`
stays `LOCAL` in both branches.

**4. Endpoint shape -- APPROVED: one discriminated endpoint.** You asked
for whichever is objectively better -- that's `POST /conversations/{id}/intents`
with the request body discriminated by `intent`, per the original
recommendation: it's what makes the DRR Section 4 shared envelope
enforceable at the type level (one `IntentResponse` model for all four,
eventually nine, intents) and avoids four parallel FastAPI route
implementations that could drift from each other the way the DRR
Section 8 finding warned about for `/documents` vs. `/capture`.

**5. Keep `/messages` indefinitely -- APPROVED (default, not
separately raised).** It remains a thin EXPLAIN-only convenience wrapper
(Section 3.2) -- no forcing function to migrate the existing chat UI in
this milestone; Section 3.7's new frontend surfaces are additive, not
replacements.

## 5. Testing plan

- `test_intent_envelope.py` -- asserts all four intents' responses
  satisfy the shared `IntentResponse` contract (every field present and
  correctly typed regardless of which `result` variant is returned).
- `test_search_intent.py` -- ranked results are returned unmodified by
  any sufficiency gate; zero-match query returns an honest empty result,
  never an error; a high-confidence match (score >=
  `SEARCH_LLM_CONFIDENCE_THRESHOLD`) confirms zero LLM provider calls
  (mock/spy the provider and assert it's never invoked) and
  `assistedSynthesis is None`; a low-confidence match (score below the
  threshold, but at least one candidate) confirms exactly one LLM call
  is made and `assistedSynthesis` is populated and cites real evidence;
  a zero-candidate query confirms no LLM call and `assistedSynthesis is
  None` even though it's below-threshold by definition.
- `test_summarize_intent.py` -- resource-target, concept-target, and
  freeform-query paths; the freeform path gets its own FR-10-style
  adversarial case (a freeform summarize query with zero local coverage
  must never be labeled Local), matching `test_chat_citations.py`'s
  existing adversarial test for Explain.
- `test_compare_intent.py` -- two concepts, two resources, and a mixed
  resource+concept comparison; a total-insufficiency case (neither side
  has evidence, behaves like Explain's insufficient case); a
  partial-insufficiency case exercising whichever Open Question 1/2
  decision is approved.
- Extend `test_alembic_migrations.py`'s expected-columns sets for the
  three new columns from `0007_intent_workflows.py`.

## 6. Non-goals for this milestone (explicitly deferred)

- Quiz me, Flashcards, Viva mode, Revision mode, Study planner --
  Milestone 10, per the roadmap's explicit sequencing (structurally
  heavier, own output schemas, needs the intent-routing pattern proven
  here first).
- Concept auto-synthesis (a rolling, auto-generated summary stored
  *on* the `Concept` row itself, updated as evidence accrues) -- Vision
  v2 Section 8 classifies this as **Phase 2**, explicitly gated on "the
  Explain workflow existing first." This milestone's Summarize is
  interactive/on-demand (computed at request time, not persisted back
  onto the concept), which is a materially smaller feature than that
  Phase 2 item and is all FR-8 requires for MVP.
- Any change to the Extractor/Classifier/ConceptLinker plugin registries
  or the ingestion pipeline -- this milestone is retrieval/answer-layer
  only, same layering discipline Milestone 8 followed.
- Dedicated confidence/correction UI beyond what Milestone 6 already
  exposes -- Milestone 11.

## 7. Implementation plan (once this design is approved)

1. Add `IntentType`/`IntentRequest`/`IntentResponse`/`CompareTarget` and
   the four per-intent result schemas to `app/schemas/`.
2. Add `Answer.intent`, `Answer.intent_payload`, `Citation.target_label`
   + Alembic migration `0007_intent_workflows.py`.
3. Refactor `retrieval_service.py`: extract the resource-target and
   concept-target evidence-resolution helpers Summarize and Compare both
   need; keep `answer_question()` behaviorally unchanged.
4. Build `app/services/intent_service.py` (`dispatch_intent` + one
   function per intent).
5. Extend `LLMProvider` with `summarize()`/`compare()`; implement on both
   providers.
6. Add config settings (Section 3.6).
7. Add `POST /conversations/{id}/intents` route; refactor `/messages`
   into a thin wrapper over the same dispatcher.
8. Frontend: intent toggle in chat, Summarize buttons on resource/concept
   detail pages, Compare flow from the concepts list.
9. Write tests (Section 5).
10. Write ADR-0016 (Intent Workflows) capturing this design's approved
    decisions, especially the Open Questions' resolutions.
11. Update this document to "Implemented, Not Verified," then run the
    same verification loop Milestones 4-8 used (deps, Alembic, pytest,
    Ruff, Black, Docker Compose, frontend build) before freezing as
    `v0.9.0-intent-workflows`.
12. Per Sai's standing process note: spend the 15-20 minutes updating
    `README.md`'s Part 2 and Roadmap table for the new milestone
    immediately after freezing -- folded into `CONTRIBUTING.md`'s
    milestone workflow checklist (see that file) so it isn't skipped.

## 8. Verification results

Run in Sai's real local environment (Windows, PowerShell), same loop used
for Milestones 4-8:

- **Dependencies** -- `pip install -r requirements-dev.txt`: all
  satisfied, 7 packages newly installed to the venv (already project
  dependencies, not new to this milestone).
- **Alembic** -- `python -m alembic upgrade head` (bare `alembic.exe` was
  blocked by a local Windows Application Control policy, same class of
  issue seen in earlier milestones; `python -m alembic` sidesteps it):
  `0006_retrieval_provenance -> 0007_intent_workflows` applied cleanly.
- **Ruff** -- `ruff check app tests`: initially found 14 issues (8 E501
  long-line, 3 I001 unsorted-import blocks across new files). All fixed
  by wrapping long lines and correcting import order (no findings in
  frozen/pre-existing files touched or invented). Final run: **all
  checks passed**.
- **Black** -- `black --check app tests` initially flagged 8 files for
  reformatting; `black app tests` applied its formatting (3 files
  reformatted after the manual Ruff fixes: `intents/summarize.py`,
  `intents/compare.py`, `routes/chat.py`). Final `black --check`: **87
  files would be left unchanged**.
- **Pytest** -- `pytest -q`: **161 passed, 3 skipped**, 0 failures.
  Covers `test_intent_envelope.py` (shared-envelope contract across all
  four intents plus the unchanged `/messages` path), `test_search_intent.py`
  (confidence-triggered LLM branch), `test_summarize_intent.py` (all
  three modes plus the freeform FR-10 adversarial case),
  `test_compare_intent.py` (full evidence, partial-evidence gap-labeling,
  total insufficiency with/without external-fallback consent), and the
  extended `test_alembic_migrations.py` column assertions.
- **Frontend** -- `npx tsc --noEmit`: no errors. `npm run build`:
  succeeded, all 12 routes compiled (including the updated `/chat`,
  `/documents/[id]`, `/concepts/[id]`, and `/concepts` pages).
- **Docker Compose** -- `docker compose up --build -d`: all 4 containers
  (`postgres`, `qdrant`, `api`, `web`) built and became healthy/started.
  `GET /health` -> `200 {"status":"ok","app":"KnowledgeHub AI"}`.
  `GET /health/ready` -> `200`, both `database` and `vector_db` components
  reported `"status":"up"`. `docker compose down` -- clean teardown.

No findings were invented and no pre-existing/frozen-file findings were
touched, consistent with the verification discipline used in Milestones
4 through 8.
