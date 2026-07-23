# Milestone 10: Study Workflows (Quiz me, Flashcards, Viva mode, Revision mode, Study planner)

**Status: Implemented and Verified.**

Design approved; all five intents (Quiz me, Flashcards, Viva mode,
Revision mode, Study planner) implemented per the design below via the
`IntentHandler` plugin registry, tested, and verified against a real
local environment (deps, Alembic, pytest, Ruff, Black, Docker Compose,
frontend build). See Section 8 for verification results. Ready to freeze
as `v0.10.0-study-workflows` (see note at the end of Section 8.2 on tag
naming).

---

## 1. Scope

Per `KnowledgeOS_Architecture_PRD_Roadmap.md` Section 8, Milestone 10 is:

> **Study Workflows** -- Quiz me, Flashcards, Viva mode, Revision mode,
> Study planner -- the more structured, output-schema-heavy workflows,
> built once the retrieval+intent foundation is proven.

FR-8 names all nine intents; Milestone 9 built the four closest to plain
retrieval (Explain, Search, Summarize, Compare). This milestone builds
the remaining five, completing FR-8. Product Vision v2 Section 8's
capability classification confirms the sequencing: "Intent workflows:
Quiz me, Flashcards, Viva mode, Revision mode, Study planner --
**Phase 2** -- structurally heavier (each has its own output schema);
sequenced after core retrieval is proven" -- i.e. exactly now, directly
after Milestone 9.

## 2. Governing constraints reviewed

- **DRR Section 4 (Extensibility)** -- the shared `IntentRequest`/
  `IntentResponse` envelope was mandated so all nine intents would share
  it "rather than converging on it retroactively." This milestone is the
  test of that promise: every one of the five new intents must fit inside
  the existing envelope (Section 3.1 below), extended only additively.
- **Architecture Section 6, decision 5** -- "Intent Router replaces 'the
  chat endpoint.'" Milestone 9 built the plugin registry
  (`IntentHandler` ABC + one class per intent + `registry.py`) per your
  explicit review comment on that milestone. This milestone adds five
  more classes to that same registry -- it does not introduce a second
  dispatch mechanism.
- **FR-2/3/4/9/10 still apply**: local-first retrieval, sufficiency
  gating, structural provenance, surfaced confidence, and "no
  hallucinated local knowledge" apply to every intent that touches the
  user's own workspace, including these five.
- **Vision v2 Section 3 (Personal Learning Layer)** -- specifies an
  explicit, incremental build order: (1) exposure tracking, (2)
  self-reported confidence, (3) quiz/interaction performance -- *"needs
  Quiz/Flashcards workflows first"* --, (4) derived mastery score, (5)
  spaced-repetition scheduling, (6) streaks. Section 8's classification
  table places steps 3-5 in **Phase 2, dependent on this milestone**, but
  does not assign them their own milestone number. This is the single
  biggest scope question this design has to resolve -- see Section 4,
  Open Question 3.
- **DRR Section 12 (Learning Layer)** -- the mastery-score formula "needs
  to actually be written down and unit-tested before Phase 2
  implementation... not time-sensitive relative to Milestone 4... this is
  a Phase 2 gate, noted here for completeness." No such spec exists yet.
  This milestone does not write one (see Non-Goals, Section 6) -- writing
  a trust-sensitive numeric formula without its own dedicated design pass
  would repeat exactly the mistake DRR Section 9/12 warns against for
  confidence numbers in general.
- **Architecture risk #1 (Scope explosion)** -- explicitly warns against
  a milestone trying to do more than one axis of complexity at once. This
  milestone's biggest temptation is to also build the full Personal
  Learning Layer (mastery score, spaced repetition) since Quiz/Viva
  finally make it possible -- Section 4's open questions exist
  specifically to keep that temptation in check.
- **ADR-0015** (provenance is structural, exactly `LOCAL`/`HYBRID`/
  `EXTERNAL`) -- unchanged; every new intent's envelope still carries one
  of these three values (or `None` for insufficient/errors).
- **CONTRIBUTING.md's milestone workflow** -- design approval before
  implementation, verification loop before freeze, README refresh within
  15-20 minutes of freezing. Followed identically here.

## 3. Proposed design

### 3.1 What's genuinely new vs. what's a straightforward extension

Four of Milestone 9's four intents were **single-shot**: one request, one
response, done. Two of this milestone's five intents are not:

| Intent | Shape | Why |
|---|---|---|
| Flashcards | Single-shot (like Summarize) | Generate N front/back cards from resolved evidence, return them all at once. No follow-up call needed. |
| Revision mode | Single-shot (like Search) | A read over existing data (concept graph + this milestone's own quiz/viva history) -- no LLM call, no follow-up. |
| Study planner | Single-shot (like Compare) | A schedule computed once from prioritized targets, returned in full. |
| **Quiz me** | **Two-turn**: generate, then grade | Generating N questions and grading the user's answers are two separate moments in time -- the answer key must never reach the client between them. |
| **Viva mode** | **N-turn**: one question/answer/evaluation per turn | Genuinely adaptive/conversational -- each turn's next question depends on how the previous one went. |

The two-turn and N-turn intents are this milestone's real design
challenge (Section 3.3). Everything else follows Milestone 9's
established pattern directly.

### 3.2 Shared envelope: additive only, no breaking changes

Per DRR Section 4's mandate being tested here: `IntentType` gains five
new literals, `IntentRequest` gains new *optional* fields (every existing
field keeps its exact meaning), and `IntentResult`'s discriminated union
gains five new `kind` variants. No existing field changes meaning, no
existing intent's behavior changes.

```python
class IntentType:
    EXPLAIN = "EXPLAIN"
    SEARCH = "SEARCH"
    SUMMARIZE = "SUMMARIZE"
    COMPARE = "COMPARE"
    QUIZ = "QUIZ"
    FLASHCARDS = "FLASHCARDS"
    VIVA = "VIVA"
    REVISION = "REVISION"
    STUDY_PLAN = "STUDY_PLAN"

class IntentRequest(BaseModel):
    intent: Literal[...]                          # 9 values now
    question: str | None = None                    # unchanged meaning
    resourceId: str | None = None                  # unchanged meaning
    conceptId: str | None = None                   # unchanged meaning
    targets: list[CompareTarget] | None = None     # unchanged meaning
    useExternalFallback: bool = False              # unchanged meaning

    # -- New, Milestone 10 --
    questionCount: int | None = None                # QUIZ: how many questions to generate
    quizId: str | None = None                       # QUIZ: grading turn, references the generation turn
    quizAnswers: list[QuizAnswerIn] | None = None    # QUIZ: grading turn, the user's selections
    sessionId: str | None = None                     # VIVA: continuing an existing session
    vivaAnswer: str | None = None                    # VIVA: the user's answer to the current question
    targetDate: date | None = None                   # STUDY_PLAN: optional deadline
    horizonDays: int | None = None                   # STUDY_PLAN: fallback window if no targetDate
```

`resourceId`/`conceptId`/`question` are reused exactly as Summarize
already defined them (resource-target / concept-target / freeform) for
Flashcards, Quiz's generation turn, and Viva's session-start turn --
Section 3.3 details which intents accept which modes.

### 3.3 Statefulness: two new tables, zero new endpoints

**The central design decision of this milestone.** Both stateful
intents' turns continue to flow through the one existing
`POST /conversations/{id}/intents` route (DRR Section 8's "one contract"
principle, already established by Milestone 9 -- see Open Question 1 for
the alternative considered and rejected).

**Why not stash state in `Answer.intent_payload` like Compare/Search do?**
`chat.py`'s `create_intent` route persists `intent_payload =
intent_response.result.model_dump_json()` -- literally the same object
already returned to the caller. Anything in `intent_payload` is
necessarily visible to the client. Quiz's answer key and Viva's grading
rubric must **not** be visible to the client between turns (a client-side
answer key is trivially cheatable and, more importantly, means grading
never actually checks the evidence -- it would just be validating the
client's own claim). This is why Quiz and Viva need their own persistence,
not a reuse of the existing generic mechanism -- everything else in this
milestone (Flashcards, Revision, Study planner) needs no new table at all.

**`quiz_attempts`** (new table, migration `0008_study_workflows.py`):

```python
class QuizAttempt(Base, UUIDPK, TimestampMixin):
    __tablename__ = "quiz_attempts"
    workspace_id: str        # tenant boundary, every table's existing pattern
    resource_id: str | None  # exactly one of resource_id/concept_id/target_label-only is set,
    concept_id: str | None   # mirroring Summarize's three-mode resolution
    target_label: str
    status: str               # GENERATED | GRADED
    question_count: int
    correct_count: int | None
    score: float | None        # correct_count / question_count once graded
    # Server-side only: full question objects including the correct choice
    # index and the citation each question is grounded in. Never
    # serialized into any IntentResult the client receives -- see the
    # QuizResult schema below, which is deliberately a different shape.
    questions_payload: str     # Text/JSON, same convention as intent_payload
    graded_at: datetime | None
```

Flow: generation turn (`intent=QUIZ`, `resourceId`/`conceptId`/`question`
set, no `quizId`) creates a row, returns `QuizResult` with `quizId` +
questions **without** answer keys. Grading turn (`intent=QUIZ`, `quizId`
+ `quizAnswers` set) loads the row (workspace-checked), grades by exact
match against `questions_payload`'s stored correct-choice index (no LLM
call needed for grading -- see Section 3.1's format decision, Open
Question 2), marks `GRADED`, returns a `QuizResult` with per-question
correctness, an explanation, and the citation that grounds each question.

**`viva_sessions`** (same migration):

```python
class VivaSession(Base, UUIDPK, TimestampMixin):
    __tablename__ = "viva_sessions"
    workspace_id: str
    resource_id: str | None
    concept_id: str | None
    target_label: str
    status: str                 # IN_PROGRESS | COMPLETED
    turn_count: int
    max_turns: int               # VIVA_MAX_TURNS setting, snapshotted at session start
    # Server-side only, same reasoning as quiz's questions_payload: each
    # turn's question, the grading rubric the LLM used, the user's
    # answer once given, and the evaluation. The client only ever sees
    # the current turn's question and the *previous* turn's evaluation
    # (Section 3.6's VivaResult), never the rubric itself.
    transcript_payload: str      # Text/JSON list of turns
    completed_at: datetime | None
```

Flow: start turn (`intent=VIVA`, `resourceId`/`conceptId`/`question` set,
no `sessionId`) creates a session, asks question 1. Continuation turn
(`sessionId` + `vivaAnswer` set) grades the just-answered question
against its stored rubric, appends the turn, and either asks the next
question or marks `COMPLETED` (at `VIVA_MAX_TURNS`, or if the LLM signals
the topic is sufficiently covered). One LLM call per turn does both jobs
(grade the previous answer, propose the next question) -- see
`conduct_viva_turn()`, Section 3.5.

Both tables are workspace-scoped exactly like every existing table, and
neither is queryable by any route outside the owning workspace -- same
tenant-isolation discipline as `Answer`/`Citation`/`Concept`.

### 3.4 The other three intents: no new tables

- **Flashcards** -- identical three-mode resolution to Summarize
  (`resourceId` / `conceptId` / freeform `question`), reusing
  `resolve_resource_evidence` / `resolve_concept_evidence` /
  `resolve_freeform_evidence` unchanged. Bypasses the sufficiency gate for
  the two explicit-target modes exactly as Summarize does (evidence
  existing is true by construction); the freeform mode goes through the
  real gate, so FR-10 applies identically. Output: `count` (default
  `FLASHCARDS_COUNT_DEFAULT`, capped at `FLASHCARDS_MAX_COUNT`) front/back
  pairs, each citing the evidence chunk it was drawn from.
- **Revision mode** -- a pure read, **zero LLM calls**, **zero new
  frozen-file touches** (approved design decision 3, Section 4). Derives
  "needs attention" entirely from data this milestone itself produces or
  that already exists: concepts with no `QuizAttempt`/`VivaSession` at
  all ("never reviewed"), concepts whose most recent graded quiz scored
  below a threshold ("last quiz: 40%"), and concepts with thin evidence
  coverage from the existing concept graph ("only 1 source linked").
  Always `status="OK"`, `provenance="LOCAL"` (this never leaves the
  user's own workspace data), `sufficiencyScore` repurposed as the
  fraction of the workspace's active concepts that have *some* review
  signal at all.
- **Study planner** -- a deterministic scheduling algorithm (Python, not
  LLM-decided) for *what* goes on which day, plus **one LLM call for the
  whole plan** to *narrate* it -- approved design decision 4, Section 4
  (your answer combined both options: deterministic scheduling for
  reliability, an LLM-narrated blurb for polish, rather than choosing
  one). Accepts the same `targets: list[CompareTarget]` shape Compare
  already defined (2+ resources/concepts/freeform topics), resolves each
  one's evidence and review-history the same way Revision mode does,
  ranks them by the same priority signal (never-reviewed first,
  low-scoring next, thin-evidence flagged honestly rather than silently
  dropped -- consistent with Compare's approved "label the gap, never
  fill it" precedent from Milestone 9), and spreads them across either
  the days until `targetDate` or a default
  `STUDY_PLANNER_DEFAULT_HORIZON_DAYS`-day window (capped at
  `STUDY_PLANNER_MAX_HORIZON_DAYS`). That deterministic per-day
  assignment is then passed, in a single batched call, to
  `LLMProvider.narrate_study_plan()` (Section 3.5) to produce one short,
  grounded guidance blurb per day -- never inventing which concepts
  belong on which day, only phrasing what the scheduler already decided.
  `ExtractiveFallbackProvider`'s implementation returns the same plain,
  templated reason text the scheduler already computed (e.g. "Review
  (never studied)"), so the plan is fully usable with zero LLM calls if
  no provider is configured, and only the wording improves when one is.
  No `Event`/milestone-marker entity is introduced -- Vision v2 Section 8
  classifies that as **Phase 3**, and `targetDate` as a plain request
  field (not a persisted entity) is sufficient for this milestone's
  scope.

**Shared helper, avoiding duplication (your instruction, Section 6
below):** Revision mode and Study planner both need "how urgently does
this concept/resource need review" -- rather than each intent computing
that independently, both call one new function,
`app/services/study_signals.py`'s `assess_review_need(db, workspace,
resource_id=None, concept_id=None) -> ReviewAssessment` (never-reviewed /
last score / evidence count), mirroring how Compare and Summarize already
share `retrieval_service.py`'s `resolve_*` helpers rather than
duplicating evidence resolution.

### 3.5 LLM provider extension (`app/services/llm.py`)

Four new abstract methods:

```python
@abstractmethod
def generate_quiz(self, target_label: str, evidence: list[EvidenceChunk], count: int) -> list[QuizQuestionDraft]: ...

@abstractmethod
def generate_flashcards(self, target_label: str, evidence: list[EvidenceChunk], count: int) -> list[FlashcardDraft]: ...

@abstractmethod
def conduct_viva_turn(self, target_label: str, evidence: list[EvidenceChunk], transcript_so_far: list[VivaTurnRecord]) -> VivaTurnDraft: ...

@abstractmethod
def narrate_study_plan(self, days: list[StudyDayDraft]) -> list[str]:
    """
    Approved design decision 4 (Section 4): the day/target assignment
    itself is computed deterministically in study_planner.py, never by
    this method -- this call only phrases a short guidance blurb per day,
    grounded in that day's already-decided targets and reason. One
    batched call for the whole plan (not one per day) keeps this bounded
    even at STUDY_PLANNER_MAX_HORIZON_DAYS. Returns exactly one string
    per input StudyDayDraft, same order.
    """
    ...
```

`StudyDayDraft` (a new `llm.py` dataclass, alongside `EvidenceChunk`/
`ComparisonEvidence`): `day: int`, `targets: list[str]`, `reason: str`
(the scheduler's own deterministic note -- the input to be phrased, not
overridden).

- `OpenAIChatProvider`: four new prompt templates, same citation-by-`[n]`
  discipline as every existing method. `generate_quiz`'s prompt requires
  the model to return structured JSON (prompt, 4 choices, correct-choice
  index, grounding citation number) -- validated and rejected/retried
  once if malformed, same defensive posture as any external-model JSON
  contract. `narrate_study_plan`'s prompt is given the scheduler's own
  day/target/reason assignments and instructed to phrase, not
  re-prioritize.
- `ExtractiveFallbackProvider`: honest, not sophisticated, matching the
  existing fallback quality bar (ADR-0004). `generate_quiz` builds
  cloze-deletion questions (blank out a key term from an evidence
  sentence, offer it alongside distractor terms pulled from other
  evidence sentences as the four choices) -- mechanical, but never
  fabricates content outside the evidence, same honesty guarantee as its
  existing `answer()`/`summarize()`. `generate_flashcards` pairs each
  evidence sentence as a front with a fill-in-the-blank-style back, same
  spirit as `summarize()`'s "no synthesis model configured" disclosure.
  `conduct_viva_turn` asks the evidence's next unused sentence as a
  direct recall question and grades the previous answer via simple
  keyword overlap against that sentence -- explicitly weaker than the
  OpenAI path, disclosed the same way every other fallback method already
  discloses its limits. `narrate_study_plan` returns each day's `reason`
  string unchanged -- no fabricated narrative, the same "no synthesis
  model configured" honesty its `summarize()`/`compare()` siblings
  already practice.

### 3.6 New result schemas (the discriminated part of the envelope)

```python
class QuizAnswerIn(BaseModel):
    questionNumber: int
    selectedChoice: int

class QuizQuestionOut(BaseModel):          # generation turn: no answer key
    questionNumber: int
    prompt: str
    choices: list[str]

class QuizGradedQuestionOut(BaseModel):    # grading turn: correctness revealed
    questionNumber: int
    prompt: str
    choices: list[str]
    selectedChoice: int
    correctChoice: int
    isCorrect: bool
    citation: CitationOut

class QuizResult(BaseModel):
    kind: Literal["quiz"] = "quiz"
    quizId: str
    target: str
    status: Literal["AWAITING_ANSWERS", "GRADED"]
    questions: list[QuizQuestionOut] | None = None          # generation turn
    gradedQuestions: list[QuizGradedQuestionOut] | None = None  # grading turn
    score: float | None = None

class FlashcardOut(BaseModel):
    front: str
    back: str
    citation: CitationOut

class FlashcardsResult(BaseModel):
    kind: Literal["flashcards"] = "flashcards"
    target: str
    cards: list[FlashcardOut]

class VivaEvaluationOut(BaseModel):
    verdict: Literal["correct", "partial", "incorrect"]
    feedback: str

class VivaResult(BaseModel):
    kind: Literal["viva"] = "viva"
    sessionId: str
    target: str
    isComplete: bool
    previousEvaluation: VivaEvaluationOut | None = None   # null on the first turn
    nextQuestion: str | None = None                        # null once isComplete
    turnNumber: int

class RevisionItemOut(BaseModel):
    label: str
    resourceId: str | None = None
    conceptId: str | None = None
    reason: str            # "Never reviewed" | "Last quiz: 40%" | "Only 1 source linked"
    priority: int           # 1 = most urgent

class RevisionResult(BaseModel):
    kind: Literal["revision"] = "revision"
    items: list[RevisionItemOut]

class StudyPlanDayOut(BaseModel):
    day: int
    date: date | None
    targets: list[str]      # labels, not full CompareTarget echoes
    # Deterministic reason the scheduler assigned these targets to this
    # day (e.g. "Review (never studied)" | "Reinforce (scored 40% last
    # time)"), then passed through LLMProvider.narrate_study_plan() for
    # phrasing -- the *assignment* is never LLM-decided, only the wording
    # (approved design decision 4, Section 4). Identical to the
    # scheduler's own text when no LLM provider is configured.
    note: str

class StudyPlanResult(BaseModel):
    kind: Literal["study_plan"] = "study_plan"
    days: list[StudyPlanDayOut]

IntentResult = Union[
    ExplainResult, SearchResult, SummarizeResult, CompareResult,
    QuizResult, FlashcardsResult, VivaResult, RevisionResult, StudyPlanResult,
]
```

### 3.7 Config additions (`app/core/config.py`)

```python
# -- Milestone 10 (Study Workflows) --
QUIZ_QUESTION_COUNT_DEFAULT: int = 5
QUIZ_MAX_QUESTIONS: int = 10
QUIZ_MAX_EVIDENCE_CHUNKS: int = 20
FLASHCARDS_COUNT_DEFAULT: int = 10
FLASHCARDS_MAX_COUNT: int = 20
VIVA_MAX_TURNS: int = 6
VIVA_MAX_EVIDENCE_CHUNKS: int = 20
REVISION_MAX_ITEMS: int = 10
REVISION_LOW_SCORE_THRESHOLD: float = 0.5   # a graded quiz below this counts as "weak"
STUDY_PLANNER_DEFAULT_HORIZON_DAYS: int = 7
STUDY_PLANNER_MAX_HORIZON_DAYS: int = 60
```

### 3.8 API changes

One new route only, for symmetry with how `/messages` stayed alongside
`/intents` in Milestone 9 -- **not** five new routes:

```
POST /api/v1/conversations/{id}/intents   (existing route, unchanged signature)
```

`chat.py`'s route body needs **no logic changes** -- it already dispatches
generically via `get_intent_handler(payload.intent).handle(db, workspace,
payload)` and already persists whatever citations/status/provenance the
handler returns. This is Milestone 9's plugin registry paying for itself
exactly as designed.

**One small, additive touch to a frozen Milestone 9 file** (flagged
explicitly -- see Open Question 5): `_describe_intent_request()` and
`_extract_assistant_content()`, two helper functions in `chat.py` that
render a plain-text conversation-transcript line for each intent, need
one new `if` branch each for the five new intents (e.g. Quiz's assistant
line becomes `f"Quiz: {result.score:.0%}"` once graded, or `f"Quiz:
{len(result.questions)} questions"` on generation). This changes zero
routing/persistence logic and zero existing branches -- purely additive,
cosmetic, transcript-only.

### 3.9 Frontend changes

- **Resource detail page** (`/documents/[id]`) and **Concept detail
  page** (`/concepts/[id]`): alongside the existing Summarize button
  (Milestone 9), add three more: **Quiz me**, **Flashcards**, **Viva
  mode**. Each opens its own panel:
  - Quiz: renders `questions` as radio-button groups, a Submit button
    fires the grading turn, then re-renders as `gradedQuestions` with
    correct/incorrect styling, the citation, and the overall score.
  - Flashcards: a simple card deck (click/tap to flip front->back,
    next/previous navigation) -- reuses `CitationPill` for the grounding
    citation.
  - Viva: a chat-transcript-style panel scoped to this session --
    question, a free-text input, submit, see feedback + the next
    question, repeat until `isComplete`.
- **New page, `/revision`**: workspace-wide list of `RevisionResult`
  items, each with its reason and a "Quiz me on this" shortcut that
  launches the Quiz panel pre-targeted at that concept/resource.
- **New page, `/study-plan`**: reuses the existing multi-select control
  Compare already built on the concepts list page to pick 2+ targets,
  plus an optional date picker and horizon input, submitting to render
  the day-by-day `StudyPlanResult` as a simple table.
- Chat's existing Explain/Search toggle (Milestone 9) is **unchanged** --
  Quiz/Flashcards/Viva are structurally too different from a single
  freeform question-answer exchange to fit that toggle, and are surfaced
  as dedicated entry points instead, per FR-8's "each a distinct entry
  point with its own UI affordance."

## 4. Design decisions (approved)

**1. Statefulness mechanism -- APPROVED: one route, two tables.** Quiz's
generate-then-grade flow and Viva's multi-turn flow both dispatch through
the single existing `POST /intents` route, with new optional
`IntentRequest` fields (`quizId`/`quizAnswers`/`sessionId`/`vivaAnswer`)
and two new tables (`quiz_attempts`, `viva_sessions`) holding
server-side-only state (answer keys, grading rubrics). The alternative
considered and rejected: dedicated new endpoints per stateful intent
(e.g. `POST /quiz-attempts/{id}/grade`), which would repeat the exact
"second, divergent implementation" anti-pattern DRR Section 8 warned
against for `/documents` vs. `/capture`, applied here to `/intents` vs. a
new per-intent surface.

**2. Quiz format -- APPROVED: multiple-choice only.** Grading is
exact-match against a stored correct-choice index -- deterministic, no
LLM call needed to grade, works identically well with or without an
OpenAI key configured. Free-text short-answer questions would need an
LLM-graded rubric check (non-deterministic, another paid call, and no
honest zero-config fallback grading path); deferred to a later increment
once this shape is proven, the same sequencing logic that put Explain/
Search/Summarize/Compare before Quiz/Flashcards/Viva/Revision/Planner in
the first place.

**3. Revision mode's signal source -- APPROVED: quiz/viva history only,
no frozen-file instrumentation.** "Needs attention" is derived only from
this milestone's own `quiz_attempts`/`viva_sessions` history plus the
existing concept graph's evidence density -- not from retrofitting
Milestone 8/9's frozen Explain/Search/Summarize/Compare handlers to log
per-concept exposure (Vision v2 Section 3 Step 1), which would mean
editing five already-frozen, already-tagged files for a milestone that
isn't about them. Trade-off, accepted: a user who has only ever used
Explain/Search/Summarize/Compare will see Revision mode call every
concept "never reviewed" until they take at least one quiz or viva -- an
honest, visible limitation, not a silent inaccuracy, and one Vision v2
itself anticipates (full exposure tracking is Phase 2/3, sequenced
independently of this specific milestone).

**4. Study planner -- APPROVED: both deterministic scheduling and
LLM-narrated phrasing (your explicit direction, combining the two options
offered rather than picking one).** The day/target assignment itself --
which concepts go on which day, and why -- is computed deterministically
in Python (priority ranking + day-spreading over resolved evidence and
review history), never decided by an LLM. On top of that fixed schedule,
one batched `LLMProvider.narrate_study_plan()` call (Section 3.5) phrases
each day's already-decided reason into a short guidance blurb.
`ExtractiveFallbackProvider` returns the scheduler's own plain reason
text unchanged, so the plan is fully usable, and identically structured,
with zero LLM calls when no provider is configured -- only the wording
improves when one is. This keeps the schedule itself reliable and
testable (Architecture risk #1's scope discipline) while still getting
the requested narrative polish.

**5. Touching one frozen Milestone 9 file -- APPROVED.** `chat.py`'s
`_describe_intent_request()`/`_extract_assistant_content()` helpers get
one small, additive `if` branch each for the five new intents (pure
conversation-transcript text rendering, zero routing/persistence-logic
change, zero changes to the four existing branches) -- the only frozen
file this milestone touches at all, and only for that reason.

## 5. Testing strategy

- `test_quiz_intent.py` -- generation turn produces N questions with no
  answer key leaked in the response; grading turn scores correctly
  against a known answer key; grading with a foreign/nonexistent
  `quizId`, or one belonging to a different workspace, is rejected;
  freeform-target quiz on zero local coverage is `INSUFFICIENT`, never
  `LOCAL` (FR-10, same adversarial-case discipline as every prior
  milestone's freeform paths).
- `test_flashcards_intent.py` -- resource-target, concept-target, and
  freeform modes (mirrors `test_summarize_intent.py`'s exact structure);
  the freeform adversarial zero-coverage case.
- `test_viva_intent.py` -- session start returns turn 1 with no prior
  evaluation; a continuation turn grades the previous answer and returns
  turn 2; a session reaches `isComplete` at `VIVA_MAX_TURNS`; a
  continuation call with a foreign/nonexistent `sessionId` is rejected.
- `test_revision_intent.py` -- a concept with no quiz/viva history is
  flagged "never reviewed"; a concept with a low-scoring graded quiz is
  flagged with its score; a concept with strong recent performance is
  excluded or ranked last; result is always `LOCAL` provenance, never
  `INSUFFICIENT`/`ERROR`.
- `test_study_planner_intent.py` -- targets are spread across the
  requested horizon; a target with no resolvable evidence is labeled
  honestly, not silently dropped (mirrors Compare's Milestone 9
  precedent); `targetDate` in the past or `horizonDays` beyond the
  configured max is rejected with a clear error.
- Extend `test_intent_envelope.py` with one round-trip test per new
  intent through the real `POST /intents` route, asserting the shared
  envelope contract holds for all nine intents now.
- Extend `test_alembic_migrations.py`'s expected-table/column assertions
  for `quiz_attempts` and `viva_sessions` from
  `0008_study_workflows.py`.

## 6. Non-goals for this milestone (explicitly deferred)

- **The Personal Learning Layer's mastery score and spaced-repetition
  scheduling** (Vision v2 Section 3 steps 4-5) -- DRR Section 12
  explicitly requires a written, unit-tested formula spec *before* this
  work starts, and that spec doesn't exist yet; writing one inline here
  would repeat the exact "confidence number without a definition" mistake
  DRR Sections 9/12 warn against. Revision mode's simpler, deliberately
  cruder signal (Section 3.4, Open Question 3) is what this milestone
  ships instead.
- **Full exposure tracking across every intent** (Vision v2 Section 3
  Step 1) -- would require editing frozen Milestone 8/9 handler files;
  explicitly not done here (Open Question 3).
- **Event/milestone-marker entities** ("study for my exam on this date"
  as a persisted, reusable anchor) -- Vision v2 Section 8 classifies this
  as **Phase 3**. Study planner's `targetDate` is a plain request field,
  not a persisted entity.
- **Free-text short-answer quiz questions** -- Open Question 2;
  MCQ-only for this milestone.
- **Streaks, proactive surfacing, "concepts you haven't touched in 3
  weeks" without being asked** -- Vision v2 Section 7 (Proactive AI),
  explicitly the last capability in the entire roadmap, gated on
  infrastructure (including this milestone's own quiz/viva history) that
  needs to exist and accumulate real data first.
- **Confidence/correction UX beyond what Milestone 6 already exposes** --
  Milestone 11, unchanged from the existing roadmap.

## 7. Implementation plan (once this design is approved)

1. Add `QuizAttempt`/`VivaSession` models + Alembic migration
   `0008_study_workflows.py`.
2. Add the five new `IntentType` literals, `IntentRequest`'s new optional
   fields, and the five new result schemas (`QuizResult`/
   `FlashcardsResult`/`VivaResult`/`RevisionResult`/`StudyPlanResult`) to
   `app/schemas/intents.py`.
3. Add config settings (Section 3.7).
4. Build `app/services/study_signals.py`'s `assess_review_need()`,
   shared by Revision mode and Study planner.
5. Extend `LLMProvider` with `generate_quiz()`/`generate_flashcards()`/
   `conduct_viva_turn()`; implement on both providers.
6. Build the five new `IntentHandler` classes
   (`app/services/intents/{quiz,flashcards,viva,revision,study_planner}.py`)
   and register them in `registry.py`.
7. Add the two additive `if` branches to `chat.py`'s transcript-rendering
   helpers (Open Question 5) -- no other change to `chat.py`.
8. Frontend: Quiz/Flashcards/Viva panels on resource/concept detail
   pages; new `/revision` and `/study-plan` pages.
9. Write tests (Section 5).
10. Write ADR-0017 (Study Workflows) capturing this design's approved
    decisions.
11. Update this document to "Implemented and Verified" with real
    verification results, then run the same verification loop
    Milestones 4-9 used (deps, Alembic, pytest, Ruff, Black, Docker
    Compose, frontend build) before freezing as
    `v0.10.0-study-workflows`.
12. Per the standing process note (now in `CONTRIBUTING.md`): update
    `README.md`'s Part 2 and Roadmap table immediately after freezing.

## 8. Verification results

### 8.1 Self-verification (sandbox environment)

Run in an isolated sandbox before handing off to Sai's real environment,
the same discipline used since Milestone 9 -- catching real bugs early
rather than relying solely on the authoritative run below:

- **Dependencies** -- installed successfully this pass (fastapi,
  pydantic, sqlalchemy, httpx, python-jose, passlib, bcrypt,
  email-validator, alembic, pytest, PyMuPDF, python-docx, python-pptx,
  ruff, black), enabling real module-import-level testing, not just
  `py_compile` syntax checks.
- **A genuine bug caught this way, not by `py_compile`:** `StudyPlanDayOut.date: date | None` and
  `IntentRequest.targetDate: date | None` both raised
  `TypeError: unsupported operand type(s) for |: 'NoneType' and 'NoneType'`
  at import time under Pydantic v2 -- the field name `date` shadowed the
  imported `datetime.date` type during forward-ref evaluation. Fixed by
  aliasing the import (`from datetime import date as _date`) and
  updating both fields to reference `_date`.
- **Ruff** -- `ruff check app tests`: found 15 genuine `E501` (line too
  long, >110 chars) findings across the new/touched files
  (`intents/{flashcards,quiz,viva,study_planner}.py`, `llm.py`, and two
  new test files) plus 2 `I001` (import-unsorted) findings in
  `tests/conftest.py` and `tests/test_alembic_migrations.py` that predate
  this milestone's edits (neither file's import block was touched this
  milestone) and are most likely a Ruff-version difference between this
  sandbox and Sai's pinned environment -- left untouched per the standing
  "never fix pre-existing/frozen-file findings" discipline. All 15
  genuine findings fixed by wrapping long lines. Final run: only the 2
  known pre-existing `I001` findings remain.
- **Black** -- `black app tests`: reformatted 5 files (all this
  milestone's own new/touched files). One additional file,
  `services/embeddings.py` (untouched by this milestone), was flagged by
  `black --check` under this sandbox's Python 3.10 -- the project pins
  `target-version = ["py311"]`, and Black's own warning states py3.10
  cannot safely verify formatting written for py3.11; the proposed
  reformat was a real diff to a frozen file this milestone never touched,
  so it was reverted rather than applied. This is almost certainly a
  sandbox Python-version artifact, not a real formatting regression --
  worth a quick confirmation against Sai's pinned toolchain below. Final
  `black --check`: only that one pre-existing/frozen-file case remains
  flagged, for the reason above.
- **Pytest** -- full suite run in batches (192 tests total, including 28
  new Milestone 10 tests across `test_quiz_intent.py`,
  `test_flashcards_intent.py`, `test_viva_intent.py`,
  `test_revision_intent.py`, `test_study_planner_intent.py`, and 5 new
  round-trip cases in `test_intent_envelope.py`): **all 192 passed**, 0
  failures, both before and after Black's reformatting pass.
- **Frontend** -- `tsc --noEmit -p tsconfig.json`: **0 errors** across
  the extended `lib/api.ts` (9-member `IntentResultOut` union, Milestone
  10's request/result types), the new `components/StudyPanels.tsx`
  (`QuizPanel`/`FlashcardsPanel`/`VivaPanel`, shared between
  `documents/[id]` and `concepts/[id]`), and the two new pages
  (`app/revision/page.tsx`, `app/study-plan/page.tsx`). A full
  `npm run build` could not be completed in this sandbox (each shell
  call here is an independent, non-persistent execution context, and a
  production build's compile time exceeds one call's window) -- this is
  a sandbox tooling limitation, not a known issue with the code; it is
  the first item in Section 8.2 below.

No findings were invented and no pre-existing/frozen-file findings were
silently fixed, consistent with the verification discipline used in
Milestones 4 through 9.

### 8.2 Real-environment verification (Sai, Windows/PowerShell)

Run in Sai's real local environment, same loop used for Milestones 4-9:

- **Dependencies** -- `pip install -r requirements-dev.txt`: all already
  satisfied (no new runtime dependencies introduced by this milestone,
  consistent with the "only declare what's used" discipline).
- **Alembic** -- `python -m alembic upgrade head`:
  `0007_intent_workflows -> 0008_study_workflows` applied cleanly.
- **Ruff** -- `ruff check app tests`: **all checks passed**, confirming
  the sandbox's 15 genuine `E501` fixes carried over correctly and the
  2 `I001` findings were in fact pre-existing/sandbox-only (Sai's pinned
  Ruff reports the two files clean).
- **Black** -- `black app tests`: **99 files left unchanged** (0
  reformatted) -- confirms `app/services/embeddings.py` needed no
  reformatting under the project's actual pinned toolchain, so the
  sandbox's flag on that file was exactly the Python 3.10-vs-3.11
  artifact suspected in Section 8.1, not a real issue. `black --check
  app tests`: **99 files would be left unchanged**.
- **Pytest** -- `pytest -q`: **189 passed, 3 skipped**, 0 failures (189 +
  3 = 192, matching the sandbox's full-suite count exactly). Covers all
  28 new Milestone 10 tests (`test_quiz_intent.py`,
  `test_flashcards_intent.py`, `test_viva_intent.py`,
  `test_revision_intent.py`, `test_study_planner_intent.py`, and 5 new
  round-trip cases in `test_intent_envelope.py`) plus every Milestone
  1-9 test, unchanged.
- **Frontend** -- `npx tsc --noEmit`: no errors. `npm run build`:
  **succeeded**, all 14 routes compiled, including the two new
  `/revision` and `/study-plan` pages and the updated `/documents/[id]`
  and `/concepts/[id]` pages (now carrying the Quiz/Flashcards/Viva
  panels).
- **Docker Compose** -- `docker compose up --build -d`: all 4 containers
  (`postgres`, `qdrant`, `api`, `web`) built and became healthy/started.
  `GET /health` -> `200 {"status":"ok","app":"KnowledgeHub AI"}`.
  `GET /health/ready` -> `200`, both `database` and `vector_db`
  components reported `"status":"up"`. `docker compose down` -- clean
  teardown.

No findings were invented and no pre-existing/frozen-file findings were
touched, consistent with the verification discipline used in Milestones
4 through 9. This milestone is ready to freeze as
`v0.10.0-study-workflows`, matching the `v0.N.0-slug` convention every
prior tag used (e.g. `v0.9.0-intent-workflows`); happy to tag exactly
`v0.10.0` instead if you'd rather break the convention here -- awaiting
your explicit freeze approval either way.
