# ADR-0017: Study workflows (Milestone 10)

**Status:** Accepted (Milestone 10)

**Decision:** Implement the remaining five FR-8 intents -- **Quiz me**,
**Flashcards**, **Viva mode**, **Revision mode**, **Study planner** --
completing the nine-intent set ADR-0016 started, via the same
`IntentHandler` plugin registry and the same DRR Section 4 shared
envelope, extended additively only. Two of these five (Quiz me, Viva
mode) are genuinely multi-turn and need server-side-only state (an answer
key, a grading rubric) that must never reach the client -- solved with
two new tables rather than by overloading `Answer.intent_payload`, which
mirrors exactly what the client already received.

See `docs/milestones/MILESTONE_10.md` for the full design record,
including the five decisions below (all resolved during design review,
before implementation began).

## Sub-decisions

**1. Statefulness: one route, two new tables, not a new route per
intent.** `QuizAttempt` and `VivaSession` (`app/models/study.py`,
migration `0008_study_workflows`) hold the private half of a two-turn or
N-turn flow -- `QuizAttempt.questions_payload` stores each question's
`correctChoice` index; `VivaSession.transcript_payload` stores each
turn's grading rubric and evidence. Neither field is ever serialized into
an `IntentResponse`; `app/services/intents/quiz.py` and `viva.py` project
a public-only view (`QuizQuestionOut`, no answer key) on the generation/
start turn, and reveal `correctChoice`/`previousEvaluation` only after
the fact, on the grading/continuation turn, for the specific question
just answered. `POST /conversations/{id}/intents` stays the single
dispatch route for all nine intents -- a generation turn omits `quizId`/
`sessionId`; a grading/continuation turn includes it. This was the
explicitly approved alternative to either a dedicated `/quiz` sub-router
or cramming the answer key into `intent_payload` (rejected: anything in
`intent_payload` is, by construction, already visible to the client that
received it).

**2. Quiz is multiple-choice only.** `QuizQuestionDraft.correct_choice`
is an index into `choices`, so grading is exact-match -- zero LLM calls
needed to grade, unlike generation. Free-text short-answer quiz questions
(which would need LLM-graded rubric matching, the same mechanism Viva
mode already uses) are an explicit non-goal for this milestone, deferred
alongside full spaced-repetition scoring.

**3. Revision mode's signal comes only from this milestone's own data,
never from retrofitting Explain/Search/Summarize/Compare.**
`app/services/study_signals.py`'s `assess_review_need()` looks at a
concept or resource's `QuizAttempt`/`VivaSession` history (never
reviewed / last quiz score / last viva outcome) plus the existing concept
graph's evidence density (how many `ResourceConcept` links exist) --
never at Milestone 9's frozen intents' own histories, which were never
designed to double as a study-tracking signal and would have required
touching frozen files well beyond the one approved exception below.
`RevisionIntent` and `StudyPlannerIntent` both call this same helper
rather than duplicating "what needs review" logic -- the same sharing
discipline `retrieval_service.py`'s `resolve_*` helpers established for
Milestone 9's four intents.

**4. Study planner combines deterministic scheduling with LLM-narrated
phrasing -- not one or the other.** Day/target assignment is always
computed by `StudyPlannerIntent._schedule()` (ceil-division spreading by
priority, in Python, never LLM-decided); a single batched
`LLMProvider.narrate_study_plan()` call then phrases the already-decided
schedule into a `note` per day. `ExtractiveFallbackProvider` returns the
plain deterministic reason unchanged when no LLM is configured, so the
schedule itself is identical and correct either way -- only its prose
differs. This was your explicit "both" override of the original
either/or framing, and is why `StudyDayDraft` exists as a distinct
dataclass from `StudyPlanDayOut`: the LLM only ever rephrases a `reason`
string it did not invent.

**5. One small, approved, additive touch to a frozen Milestone 9 file.**
`api/v1/routes/chat.py`'s two transcript-rendering helpers
(`_describe_intent_request`, `_extract_assistant_content`) gained five
new `if`/`isinstance` branches each, one per new intent, so a
conversation's transcript reads sensibly for Quiz/Flashcards/Viva/
Revision/Study-plan turns. This is cosmetic conversation-transcript text
only -- zero routing, persistence, or dispatch logic in this file
changed; every Milestone 9 branch is byte-for-byte unchanged. Approved as
an explicit, scoped exception to "don't touch frozen files," not a
precedent for touching frozen files generally.

**6. Schema additions, all additive.** `IntentType` gained
`QUIZ`/`FLASHCARDS`/`VIVA`/`REVISION`/`STUDY_PLAN`; `IntentRequest`
gained `questionCount`, `quizId`, `quizAnswers`, `sessionId`,
`vivaAnswer`, `targetDate`, `horizonDays` -- every Milestone 9 field's
meaning is unchanged. `IntentResult`'s discriminated union grew from four
members to nine. Two new tables (`quiz_attempts`, `viva_sessions`,
migration `0008_study_workflows`); no changes to `Resource`/`Concept`/
`ResourceConcept`/`ConceptRelationship`/`Answer`/`Citation` -- the five
new intents read existing evidence and concept-graph data, and write only
to their own two new tables.

**What stayed out of scope, deliberately:** full PLL-style mastery
scoring or real spaced-repetition intervals (Revision mode's signal is
deliberately simple: never-reviewed / low-score / thin-evidence, not a
scheduling algorithm in its own right -- that's the Study planner's job,
and even there the "algorithm" is ceil-division by priority, not SM-2 or
similar); free-text/short-answer quiz grading; any Event/milestone-marker
entity in the concept graph (deferred to Phase 3 per the Product Vision);
any change to the Extractor/Classifier/ConceptLinker/IntentHandler-M9
plugin registries beyond the one new registry entry per new intent.
