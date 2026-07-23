# ADR-0016: Intent workflows (Milestone 9)

**Status:** Accepted (Milestone 9)

**Decision:** Implement the first four of FR-8's nine intent workflows --
**Explain**, **Search**, **Summarize**, **Compare** -- behind one shared
request/response envelope (DRR Section 4's explicit mandate), dispatched
through a plugin registry of one handler class per intent
(`app/services/intents/`), rather than a single function branching on
intent type. The remaining five (Quiz me, Flashcards, Viva mode, Revision
mode, Study planner) are Milestone 10, per the roadmap's explicit
sequencing.

See `docs/milestones/MILESTONE_9.md` for the full design record,
including the four decisions below.

## Sub-decisions

**1. Shared envelope, discriminated result (DRR Section 4).** Every
intent's `IntentResponse` shares six fields (`intent`, `status`,
`provenance`, `sufficiencyScore`, `retrievalConfidence`,
`canOfferExternalFallback`, `citations`); each intent's own output shape
lives in a `result` field, a Pydantic discriminated union tagged by
`kind`. This was a hard requirement from the DRR, not a preference --
building four (eventually nine) independently-shaped contracts and
converging on a shared envelope retroactively was explicitly the failure
mode DRR Section 4 warned about.

**2. Plugin registry, not a branching dispatcher.** `IntentHandler` (ABC)
+ one class per intent (`ExplainIntent`, `SearchIntent`,
`SummarizeIntent`, `CompareIntent`) + `registry.get_intent_handler()`
mirrors the `Extractor`/`Classifier`/`ConceptLinker` pattern already
established in this codebase, applied one layer later in the pipeline.
Amended into the design after initial review specifically to keep
Milestone 10's five additional intents additive (one new file, one
registry entry) rather than growing a shared function's branching logic.

**3. Retrieval primitives are shared; sufficiency-gating is not.**
`retrieval_service.py` gained five new functions (`resolve_question_candidates`,
`resolve_citations_and_evidence`, `resolve_freeform_evidence`,
`resolve_resource_evidence`, `resolve_concept_evidence`) that Explain,
Search, Summarize, and Compare all call -- but each intent decides for
itself what an insufficient result means for its own response shape.
Explain and Summarize's freeform mode refuse to answer when
`compute_sufficiency()` says no; Search never refuses (a ranked list,
even an empty one, is itself an honest answer); Summarize/Compare's
explicit resource/concept-target modes bypass the sufficiency scorer
entirely, since a `READY` resource or an `ACTIVE` concept's evidence
existing is true by construction, not something to infer from a query.

**4. Three approved trade-offs, all decided during design review, not
during implementation:**
   - **Compare's partial evidence** (one target has local evidence,
     another doesn't) proceeds, with the gap clearly labeled -- never
     silently filled from general knowledge. Total insufficiency (every
     target empty) is treated as materially different and behaves like
     Explain's insufficient case, including honoring
     `useExternalFallback`/`allow_external_fallback` for a single
     combined general-knowledge comparison.
   - **`provenance` stays exactly `LOCAL`/`HYBRID`/`EXTERNAL`/`None`**
     (unchanged from ADR-0015) even for Compare's mixed-evidence case --
     per-target detail lives in `result.targets[*].hasEvidence`, not in a
     widened enum. This was an explicit choice to keep ADR-0015's
     contract untouched rather than grow a fourth value for one intent's
     edge case.
   - **Search conditionally calls the LLM** based on confidence (your
     explicit direction during design review, overriding the original
     "never call an LLM" recommendation): at or above
     `SEARCH_LLM_CONFIDENCE_THRESHOLD`, zero LLM calls, ranked hits only;
     below it, one additional grounded call producing `assistedSynthesis`
     on top of (never instead of) the ranked hits. The synthesis can only
     draw on evidence Search's own retrieval already surfaced, so FR-10
     holds and `provenance` stays `LOCAL` in both branches.

**5. `POST /conversations/{id}/intents` is the one real dispatch
endpoint; `POST /conversations/{id}/messages` (Milestone 8) is kept
unchanged as a separate, full-fidelity EXPLAIN-only path.** Both call
`retrieval_service.answer_question()` -- there is exactly one
implementation of the retrieval logic. `/messages` persists richer
per-answer detail (`model_name`, `retrieval_latency_ms`,
`generation_latency_ms`) that the generic `IntentResponse` envelope
deliberately doesn't carry (those fields are EXPLAIN/generation-specific
concerns, not something every intent needs); `/intents` persists the
envelope's fields plus the discriminated `result` as `Answer.intent_payload`
(JSON text). This is a refinement discovered during implementation, not a
deviation from the approved "thin wrapper" framing in
`docs/milestones/MILESTONE_9.md` Section 3.2 -- the framing's actual goal
(one implementation of the retrieval logic, no divergence) holds either
way.

**6. Schema additions, all additive.** `Answer.intent` (default
`"EXPLAIN"`, so every pre-Milestone-9 row is valid with no backfill),
`Answer.intent_payload` (nullable JSON text), `Citation.target_label`
(nullable, populated only by Compare). `CitationOut` gained `chunkId`
(previously internal-only, needed so a citation can be persisted
end-to-end from the generic envelope) and `targetLabel`. No new tables,
no changes to `Resource`/`Concept`/`ResourceConcept`/`ConceptRelationship`
-- Compare and Summarize read existing data, they don't need new graph
structure.

**What stayed out of scope, deliberately:** Quiz me, Flashcards, Viva
mode, Revision mode, Study planner (Milestone 10); concept auto-synthesis
-- a persisted, continuously-updated rolling summary on the `Concept` row
itself (Vision v2 Section 8's Phase 2 item, explicitly gated on Explain
existing first -- this milestone's Summarize is on-demand/interactive,
not persisted); any change to the Extractor/Classifier/ConceptLinker
plugin registries or the ingestion pipeline.
