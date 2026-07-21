# System Architecture

## High-level components

```mermaid
flowchart LR
    U[Browser] --> WEB[Next.js Web App]
    WEB --> API[FastAPI]
    API --> PG[(PostgreSQL)]
    API --> STORE[(Local Storage Volume)]
    API --> QD[(Qdrant)]
    API --> LLM[LLM Provider\nOpenAI or Extractive Fallback]
    API --> EMB[Embedding Provider\nLocal Hash or OpenAI]
```

## Ingestion flow

```mermaid
flowchart LR
    A[POST /documents] --> B[Validate type/size/checksum]
    B --> C[Save to storage, create Document + IngestionJob]
    C --> D[Return 201 QUEUED immediately]
    D --> E[BackgroundTask: process_document]
    E --> F[PyMuPDF extract text per page]
    F --> G{Looks scanned?}
    G -- yes --> H[FAILED: SCANNED_PDF_UNSUPPORTED]
    G -- no --> I[Chunk pages ~500 tokens, overlap]
    I --> J[Embed chunks]
    J --> K[Upsert vectors to Qdrant\nworkspace_id + document_id payload]
    K --> L[Document READY]
```

## RAG + citation flow

```mermaid
flowchart LR
    Q[User question] --> R[Embed query]
    R --> S[Qdrant search\nfilter: workspace_id]
    S --> T[Filter to READY documents only]
    T --> U{Any evidence?}
    U -- no --> V[NO_EVIDENCE answer, no citations]
    U -- yes --> W[Build evidence-only prompt]
    W --> X[LLM generates answer with n bracket citations]
    X --> Y[Backend maps n to retrieved chunk metadata]
    Y --> Z[Persist Answer + Citations]
    Z --> AA[Return answer + citations to UI]
    AA --> AB[User clicks citation]
    AB --> AC[Source Viewer: PDF at cited page + excerpt]
```

## Why this shape

- **Every retrieval is workspace-scoped.** The Qdrant query filter and the
  `Document.status == READY` check both run before evidence reaches the
  LLM, so a user can never receive an answer built from another workspace's
  documents, or from a document that failed processing (see ADR-0002).
- **Citations are backend-verified, not LLM-generated.** The model is told
  to cite with `[n]`, but the document, page, and excerpt behind each `[n]`
  are read from what the backend actually retrieved (see
  `app/services/retrieval_service.py`). The model cannot invent a source.
- **Every external dependency is behind an interface.** Storage, vector
  search, embeddings, and generation are all narrow Python interfaces with
  a swappable implementation (see ADR-0002, ADR-0004, ADR-0007). Phase 2
  and enterprise upgrades are additive, not rewrites.

See `docs/adr/` for the full reasoning behind each individual decision, and
the product freeze conversation for the frozen database schema and API
contract this implementation follows exactly.
