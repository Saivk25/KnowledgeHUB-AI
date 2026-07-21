# ADR-0002: Qdrant as the vector database

**Status:** Accepted (MVP, carries to production architecture)

**Decision:** Use Qdrant for all semantic (dense vector) search, with a
single collection and a mandatory `workspace_id` payload filter on every
query.

**Alternatives considered:**
- **pgvector:** would avoid a second datastore, but retrieval-specific
  features (payload filtering, HNSW tuning, sparse/hybrid vectors) are
  bolted on rather than native, and it couples vector scale to the
  relational database's scaling story.
- **Chroma:** excellent for local prototyping, but has a weaker production
  operations story (clustering, payload indexing at scale).
- **Milvus:** more powerful at very large scale, but meaningfully higher
  operational overhead (multiple coordinating services) than justified here.
- **Pinecone/managed vector DB:** fastest to start, but introduces a paid,
  internet-dependent hosted service into a project whose explicit goal is a
  self-contained, recruiter-runnable Docker Compose stack.

**Why this wins:** Qdrant ships as one container, has first-class payload
filtering (used here to enforce the tenant boundary at the retrieval layer,
not just the API layer), and has a clear upgrade path to hybrid/sparse
vectors without switching engines later.

**MVP impact:** one collection (`document_chunks_v1`), cosine distance,
384-dim vectors (matches the default local embedding provider), keyword
index on `workspace_id` and `document_id`.

**Revisit when:** corpus size or hybrid lexical retrieval requirements
justify OpenSearch alongside Qdrant (Phase 2), or multi-region/managed
Qdrant Cloud is needed for enterprise deployments.
