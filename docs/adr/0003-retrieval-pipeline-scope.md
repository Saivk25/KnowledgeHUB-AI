# ADR-0003: Dense-only retrieval, no reranking or query rewriting in MVP

**Status:** Accepted (MVP)

**Decision:** The chat pipeline does exactly: embed the question, run a
top-k Qdrant similarity search filtered by `workspace_id`, and pass the
results directly to the LLM as evidence. No hybrid lexical search, no
cross-encoder reranking, no query rewriting/expansion.

**Alternatives considered:** hybrid dense+lexical fusion, cross-encoder
reranking of the top-N candidates, and LLM-based query rewriting all
measurably improve retrieval quality at scale (see the full enterprise SRS).

**Why simpler wins here:** each of those stages is a place a two-day build
can break under time pressure, and the MVP's demo corpus (a handful of
seeded PDFs) does not have enough scale or lexical ambiguity for reranking
to change the outcome. The retrieval call is isolated in
`app/services/retrieval_service.py` specifically so a reranker or hybrid
step can be inserted later without touching the chat route, the citation
pipeline, or the UI.

**MVP impact:** `TOP_K=6`, `MIN_SCORE_THRESHOLD=0.05`, no reranker
dependency, one round trip to the vector store per question.

**Revisit when:** real usage shows retrieval precision problems, or the
corpus grows past what a small workspace naturally holds (Phase 2).
