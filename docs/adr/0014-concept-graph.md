# ADR-0014: Concept graph (Milestone 7)

**Status:** Accepted (Milestone 7)

**Decision:** Add three new tables (`concepts`, `resource_concepts`,
`concept_relationships`, migration `0005_concept_graph`) implementing the
Roadmap's Milestone 7 line item, plus the two DRR Section 11 critical
fixes (concept deduplication/entity resolution, cycle-safe graph
traversal) and Product Vision v2 Sections 2/5's two MVP-classified
refinements (a typed/asymmetric relationship model, and an evidence link
enriched with `contribution_type` rather than a bare confidence score).

## Sub-decisions

**1. Scope boundary, exactly as approved.** In scope: concept schema,
resource↔concept evidence links, typed relationships, concept linking,
deduplication, manual merge, browse UI, graph traversal. Explicitly out of
scope: concept synthesis/auto-summary, auto-generated concept pages,
Knowledge Timeline, Personal Learning Layer, Proactive AI, graph
visualization, a dedicated graph database. None of these were implemented,
scaffolded, or given dormant/placeholder code.

**2. Concept-linker design: reuse, don't add NLP.** `LocalConceptLinker`
(default, zero-config) reuses the resource's already-classified `subject`
(Milestone 6) as the candidate concept name -- no spaCy, no NER model, no
new dependency. `contribution_type` comes from a small, documented,
deterministic mapping off the resource's already-classified
`content_category` (`CATEGORY_TO_CONTRIBUTION` in
`app/services/concept_linking.py`), directly operationalizing Vision v2
Section 2's own examples ("a lecture PDF *defines* ... an assignment
*applies* it ... an MCQ set *tests* it ... a research paper *extends*
it"). `confidence` is the resource's real `subject_confidence`, never a
new invented number. The evidence chunk is chosen by real embedding
similarity between the candidate name and the resource's own chunks
(argmax), using whichever `EmbeddingProvider` is already configured.
`OpenAIConceptLinker` mirrors `OpenAIClassifier` exactly and is
retrieval-grounded (Architecture Section 9 item 5): it is only ever shown
chunks and existing concepts that actually exist, and every
`evidenceChunkId`/`conceptId`/`toConceptId` in its structured response is
validated against what was actually provided -- an id that doesn't appear
in what the model was shown is dropped, never trusted.

**2b. Zero-config fallback when `subject` is null.**
`LocalHeuristicClassifier` (Milestone 6) deliberately never guesses a
subject -- discovered during implementation: without a fallback, a fully
zero-config deployment (both provider settings left at `local`, the
actual defaults) would therefore never create a single concept, silently
contradicting this codebase's established "zero-config golden path"
precedent. Fix: when `subject` is `None`, `LocalConceptLinker` falls back
to a name derived from the resource's own filename (strip extension,
replace `_`/`-` with spaces, title-case) -- plain string manipulation,
not NLP, still within the approved "no new NLP dependency" constraint --
at a flat, honest, deliberately-low `_FILENAME_FALLBACK_CONFIDENCE`
(0.3), never dressed up as a real classification.

**3. The local linker never proposes relationships.** With no grounding
step and no NLP, there is no honest local signal for "concept A relates
to concept B" -- inventing one would be exactly the kind of manufactured
confidence badge DRR Section 9 warns against, and the same restraint
`LocalHeuristicClassifier` already applies to subject-guessing in
Milestone 6. A zero-config deployment therefore has concepts and evidence
but no typed edges until `CONCEPT_LINKER_PROVIDER=openai` and
`OPENAI_API_KEY` are set. This is an honest limitation, not a bug.

**4. Concept vectors reuse the existing Qdrant deployment via a second
collection**, not a new store or a dedicated similarity index (DRR
Section 3). `VectorPoint` gained one optional field (`concept_id`) and
its other fields gained defaults, rather than forking a parallel type --
the same "extend an existing field's meaning" precedent already used for
`page_number` and `document_id`. `get_concept_vector_repository()`
mirrors `get_vector_repository()`'s exact caching/fallback shape.

**5. Three-zone deduplication (DRR Section 11), never a silent auto-merge
in the ambiguous middle.** `resolve_concept()`
(`app/services/concept_graph.py`) checks an exact `normalized_name` match
within the workspace first (cheap, indexed), then an ANN search against
the workspace's concept vectors. Above `SIMILARITY_MERGE_THRESHOLD`
(0.85): treated as the same concept. Between that and
`POSSIBLE_DUPLICATE_THRESHOLD` (0.65): a new concept is still created, but
flagged `possible_duplicate_of_concept_id` for a human to resolve via
`POST /concepts/{id}/merge`. Below both: a genuinely new concept. These
two constants are named, documented, and tunable -- not magic numbers
buried in a conditional.

**6. Every relationship and every evidence link requires a real evidence
pointer -- an explicit, stronger rule than the original design proposal.**
`resource_concepts.evidence_chunk_id` and
`concept_relationships.evidence_chunk_id` are both `NOT NULL`. A link or
edge that cannot point at the specific chunk that supports it is never
created. This is the direct implementation of Architecture Section 9 item
5 ("store the evidence pointer alongside every concept link, so 'why does
the system think X relates to Y' is always answerable") applied as a hard
constraint rather than a best-effort field.

**7. No orphan concepts.** A concept is never created without at least
one evidence link (`resolve_concept` is only ever called as part of
persisting a `ResourceConcept` row in the same transaction). If a
concept's last evidence link is later removed -- a resource evidencing it
is deleted, or a concept-linking re-run on retry replaces its evidence --
`recompute_concept_usage()` marks it `UNUSED` (reactivated back to
`ACTIVE` if evidence returns) rather than leaving it dangling or
hard-deleting it (a `ConceptRelationship` may still reference it). A
concept already `MERGED` is left alone -- that status already says where
its evidence went, more specifically than `UNUSED` would.

**8. Cycle-safe traversal is centralized in one function, implemented as
an application-level breadth-first walk, not a raw recursive SQL CTE.**
`traverse_concept_graph()` is the single function every current and
future recursive concept-graph query must go through. Safety comes from
an explicit `visited` node set (a concept is never re-added to the
frontier once reached, which is what actually breaks a cycle -- verified
directly in `tests/test_concept_graph_traversal.py` against a manually
constructed A→B→A relationship) plus an independent `MAX_TRAVERSAL_DEPTH`
bound (default 5) applied regardless of what a caller requests. A raw
`WITH RECURSIVE` CTE with a string-path cycle guard was considered and
would also satisfy DRR Section 11, but at the personal-archive scale this
product targets (DRR Section 3) a handful of indexed queries per hop is
simpler to reason about, easier to unit-test the exact cycle/depth
guarantee against, and consistent with this codebase's general preference
for explicit Python logic over intricate SQL (Architecture Section 9;
resource.py's own documented preference for application-layer invariants).
Revisit if per-hop query overhead ever becomes measurable at a corpus size
this product wasn't designed around.

**9. Uniqueness is application-layer, not a DB constraint** -- (workspace,
normalized_name) among ACTIVE concepts, and duplicate evidence/relationship
rows, are both prevented by check-then-write logic in
`concept_graph.py`/`ingestion_service.py`, matching this codebase's
existing convention (`resources.checksum` is indexed but not DB-unique,
for the documented reason that cross-field invariants live in Python here,
not SQL).

**10. `CONCEPT_LINKING` runs after `INDEXING`, before `DONE`; failure never
fails the resource; retried via the existing `/documents/{id}/retry`
route.** Same graceful-degradation pattern Milestone 6 established for
`CLASSIFYING`. `_link_concepts()` replaces (deletes and re-inserts) a
resource's `ResourceConcept` rows on every run so a retry never
accumulates duplicate evidence; `ConceptRelationship` rows are not scoped
to one resource, so they are instead deduplicated at write time
(`_upsert_relationship` skips if an identical from/to/type edge already
exists).

**11. Background processing re-evaluated at this milestone, per
Architecture Section 9 item 7, and left unchanged.** Concept-linking's
cost depends on the *existing* corpus (the ANN dedup search), not just the
new upload -- exactly the condition that item flagged as the point to
reconsider `BackgroundTask` vs. a real task queue. Decision: remain on
`BackgroundTask`. At the personal-archive scale this product targets (low
hundreds to low thousands of concepts), a per-request ANN search plus a
depth-capped BFS is not a meaningful latency concern, and introducing
Celery/Temporal/RabbitMQ/Kafka now would be new infrastructure the
"smallest necessary technology" discipline (already applied to Docker
Compose over Kubernetes, `BackgroundTask` over a queue in Milestones 1-3)
argues against pre-building. **Revisit trigger:** observed
`CONCEPT_LINKING` stage p95 duration in production logs exceeds a few
seconds, or a workspace's concept count exceeds roughly 5,000 -- whichever
comes first. This matches Vision v2 Section 8's own classification of this
migration as "Phase 3, revisit-trigger not a fixed date."

**12. Merge is one-way this milestone.** `POST /concepts/{id}/merge`
re-points evidence and relationships and marks the source `MERGED`
(preserved, not deleted, for audit via `merged_into_concept_id`). No
undo-merge API. Deferred to a future milestone if ever needed.

**Known limitation, documented rather than silently accepted:**
`resolve_concept()`'s exact-name and ANN checks only consider `ACTIVE`
concepts. A concept that went `UNUSED` (its evidence was removed) is not
rediscovered by a later exact-name match -- a fresh concept is created
instead, rather than reactivating the old row. This is a deliberate scope
limit, not an oversight: reviving old `UNUSED` concepts via name-matching
adds real complexity (should an `UNUSED` concept ever outrank a brand-new
match? by what rule?) that the approved design does not ask for. Revisit
if orphan-then-recreate churn is ever observed to matter in practice.

**Alternatives considered:** A dedicated graph database (Neo4j) was
considered and rejected per Architecture Section 9 item 1 and Vision v2
Section 8 ("Future Research, revisit trigger not planned") -- Postgres
recursive queries (or, as built here, an application-level bounded BFS)
are well within what a personal archive's concept graph needs.

**Revisit when:** Milestone 9's Explain workflow may want to consume
concept evidence for auto-synthesis (explicitly out of this milestone's
scope). Milestone 10/11's Confidence & Correction UX may want a richer
merge history / undo path. A future Personal Learning Layer milestone may
want to attach mastery/exposure data to `Concept` -- additive, no change
needed to anything built here.
