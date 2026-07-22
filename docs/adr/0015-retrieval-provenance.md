# ADR-0015: Local-first retrieval, sufficiency scoring, and structural provenance

**Status:** Accepted (Milestone 8)

**Decision:** Extend the Milestone 4 dense-retrieval pipeline (ADR-0003) with
four additions, all scoped and approved before implementation:

1. **Hybrid candidates.** Every retrieval combines raw Qdrant vector-search
   hits with a one-hop concept expansion (Milestone 7's
   `find_nearby_concepts()`). No recursive graph traversal during retrieval
   -- `traverse_concept_graph()` stays reserved for the concepts UI, not the
   answer path. This keeps retrieval predictable, bounded, and fast.

2. **Additive ranking.** `final_score = vector_similarity +
   concept_match_boost + metadata_match_boost`. ADR-0003's "no BM25, no
   cross-encoder reranker, no learned ranking model" stays in force --
   this is a formula on top of dense similarity, not a new retrieval
   architecture. `metadata_match_boost` only applies when a resource's
   user-*confirmed* subject (Milestone 6) shares a token with the question
   -- an unconfirmed auto-classification never influences ranking.

3. **A standalone sufficiency scorer** (`app/services/sufficiency.py`).
   DRR Section 10 required this not be a threshold buried in the retrieval
   call. It is the single source of truth for the sufficiency verdict, the
   sufficiency score, and `retrieval_confidence` -- nothing else in the
   codebase computes confidence independently. Fail-closed by construction:
   every degenerate input (no candidates, thin evidence) resolves to
   `INSUFFICIENT`, never to an assumed-sufficient default. This is what
   makes DRR's adversarial test ("a query with zero relevant local content
   must never receive a Local label") a structural guarantee rather than a
   convention callers have to remember.

4. **Structural provenance.** Every `AnswerResult` carries `provenance`
   (`LOCAL` | `HYBRID` | `EXTERNAL` | `None`), `sufficiency_score`,
   `retrieval_confidence`, and `sufficiency_reason` as required fields, not
   optional ones bolted on after generation (Architecture Section 9 item 4).
   `HYBRID` only ever exists when the caller explicitly asks to supplement
   an already-sufficient local answer with general knowledge -- never a
   silent blend. `EXTERNAL` requires consent: either the workspace's
   `allow_external_fallback` setting (default `False`) or explicit
   per-request confirmation (`useExternalFallback`). An external model
   (`LLMProvider.answer_general_knowledge()`, new on the provider interface
   per ADR-0004's exact pattern) is never called without one of these two.

**The chunk-identity reconciliation this design depends on:** a
vector-search hit's `SearchResult.point.chunk_id` is not a
`ResourceChunk.id` -- it is the vector point's own generated id, which
`ingestion_service.py` also stores on the chunk row as
`ResourceChunk.vector_point_id`. A concept-expansion candidate's chunk
identity (`ResourceConcept.evidence_chunk_id`) *is* a real
`ResourceChunk.id` directly. `retrieval_service._build_candidates()`
resolves every vector hit to its real `ResourceChunk.id` up front (via
`vector_point_id`) so the merged/deduplicated/boosted candidate map is
keyed consistently by real chunk id throughout -- otherwise the same
physical chunk reached by both paths could be double-counted, or a
concept-match boost could silently fail to apply to a chunk that was also
a raw vector hit. Citations are built from the same resolved rows
regardless of origin, so the answer-generation layer never knows -- and is
never told -- whether a piece of evidence came from vector search or
concept expansion.

**Alternatives considered:**
- **Reranking with a cross-encoder or BM25 hybrid search:** real precision
  gains at scale, explicitly deferred by ADR-0003 ("Revisit when: real
  usage shows retrieval precision problems"); still true at this milestone.
- **Recursive concept-graph traversal during retrieval:** more recall, but
  unbounded latency risk and harder to reason about at answer time; the
  concepts UI already has the traversal-based "related concepts" view for
  exploration, which is a different use case than a synchronous answer.
- **A single blended confidence computed at the API/display layer:**
  rejected -- would duplicate what the sufficiency scorer already computes
  and risk drifting from it. `retrieval_confidence` is always exactly the
  sufficiency verdict's score.
- **Auto-fallback to external knowledge whenever local evidence is thin:**
  rejected outright -- violates FR-10 (no hallucinated local knowledge) and
  the product's local-first promise. Consent is structural, not a
  suggestion.

**Why this wins:** every answer this milestone produces is auditable --
its provenance, sufficiency score, and reason are persisted on the
`Answer` row (DRR Section 16), not recomputed differently by different
callers. The zero-config golden path (no `OPENAI_API_KEY`) still answers
honestly: `ExtractiveFallbackProvider.answer_general_knowledge()` never
fabricates a general-knowledge answer without a real model behind it.

**Revisit when:** real usage data suggests the sufficiency thresholds
(`SUFFICIENCY_MIN_SCORE`, `SUFFICIENCY_STRONG_SCORE`,
`SUFFICIENCY_SECONDARY_FLOOR`, `SUFFICIENCY_MIN_SUPPORTING_HITS`) need
tuning, or Milestone 9's Intent Workflows (Explain/Compare/Summarize/
Search) need a retrieval contract this module doesn't yet expose.
