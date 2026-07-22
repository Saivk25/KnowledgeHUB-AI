# KnowledgeHub AI

**Your Organization's Intelligence, Instantly Searchable.**

> **Status: Milestone 8 of 12 -- Local-First Retrieval & Provenance --
> frozen and tagged `v0.8.0-local-first-retrieval`.** Milestones 1-8 are
> implemented, verified, and frozen. This README has two parts: **Part 1**
> describes the finished product this project is building toward; **Part
> 2** describes exactly what exists in this repository right now. See
> [Roadmap](#roadmap) for everything still ahead.

---

## Part 1 -- The Vision: What This Becomes When Complete

KnowledgeHub AI is being built against one litmus test: *would someone
actually open it instead of Google Drive, Notion, Obsidian, or ChatGPT?*
Not "does it store files" or "can it answer questions" -- those are table
stakes. The test is whether it becomes the place someone goes first when
they need to think with what they already know.

Three consequences follow from that:

- **The unit of value is a concept understood, not a file stored.**
  Uploading a PDF isn't the point -- extracting what's *in* it, linking it
  to everything else the user already knows, and being able to explain
  it back is the point. The primary landing surface is meant to end up
  being a concept map / concept list ("here's what you know things
  about"), with the document library demoted to a secondary "Evidence"
  view for provenance auditing -- the same relationship Google Drive has
  to a well-organized Notion.
- **The system has to know things about the user, not just about their
  documents.** A personal learning layer tracks what's been exposed,
  self-reported, and tested -- building toward a real mastery signal per
  concept, not just "this file was uploaded once."
- **The system occasionally has to speak first.** Proactive surfacing --
  resurfacing a concept before a quiz, flagging a contradiction between
  two sources -- rather than only ever waiting to be asked.

**When finished, the product does the following:**

- **Ingests almost anything**, not just PDFs: DOCX, PPTX, plain text and
  Markdown, source code files, YouTube transcripts, and OCR'd handwritten
  notes or slide photos -- all through the same extractor/chunker/
  embedding pipeline, each format an additive plugin rather than a
  special case.
- **Classifies and organizes automatically** -- source type, subject, and
  topic suggestions with honest confidence scores, and a manual
  correction flow when the system gets it wrong.
- **Builds a real concept graph**, not just a flat document index --
  concepts and the relationships between them, linked back to the exact
  chunk of evidence that justified each link, so "why does the system
  think X relates to Y" is always answerable.
- **Answers questions from what it actually knows first.** Retrieval is
  local-first: dense vector search plus concept-graph expansion against
  the user's own workspace, with a fail-closed sufficiency scorer
  deciding whether the local evidence is actually enough before ever
  answering. Every answer carries a structural provenance label -- purely
  Local, Local+concept-graph (Hybrid), or External general knowledge --
  and falling outside the user's own documents always requires their
  explicit, revocable consent. Nothing invented is ever presented as if
  it came from the user's own material.
- **Supports real workflows, not just Q&A**: Explain, Compare, Summarize,
  and Search as first-class intents, followed by structured study
  workflows -- Quiz me, Flashcards, Viva mode, Revision mode, a study
  planner -- each with its own contract and prompt template, building on
  proven retrieval rather than bolting study features onto raw chat.
- **Makes capture as important as retrieval.** A universal capture
  surface -- quick notes, pasted text, copied code, screenshots -- reuses
  the same extraction and chunking pipeline documents use, so anything
  captured is immediately part of the same searchable, linkable
  knowledge base.
- **Surfaces its own confidence everywhere**, not just at answer time --
  OCR confidence, classification confidence, retrieval confidence -- each
  with a correction flow that actually feeds back into stored metadata.

Architecturally, the finished system stays deliberately small: Postgres
and Qdrant, not a dedicated graph database, for as long as recursive CTEs
and clean indexing can carry the concept graph; plugin registries for
extraction/classification/chunking instead of growing if/elif chains;
the sufficiency scorer as its own named, independently tested module,
never a magic threshold buried in a retrieval call; and provenance
enforced at the type level, so it's structurally impossible to construct
an answer without one. The full rationale for each of these lives in
[`docs/adr/`](docs/adr/) and in the governing architecture and roadmap
document this repository is built against.

---

## Part 2 -- What's Actually Built So Far (Through Milestone 8)

Everything below is real, implemented, tested, and frozen -- not a plan.

### Milestone-by-milestone

- **M1 -- Project Foundation** (`v0.1.0-foundation`): FastAPI + Next.js
  monorepo, Docker Compose, Postgres, Qdrant, health/readiness checks.
- **M2 -- Authentication & Workspace** (`v0.2.0-authentication`):
  registration, login, logout, session cookies, per-user workspace
  creation and isolation.
- **M3 -- Document Upload & Ingestion** (`v0.3.0-document-ingestion`): PDF
  upload, background extraction (PyMuPDF), page-aware chunking, pluggable
  embeddings, Qdrant indexing scoped per workspace.
- **M4 -- Resource Model** (`v0.4.0-resource-model`): `Document` replaced
  by a polymorphic `Resource` model; schema management moved from
  `create_all` to real Alembic migrations.
- **M5 -- Multi-Format Ingestion** (`v0.5.0-multi-format-ingestion`):
  DOCX, PPTX, TXT/Markdown, code files, YouTube transcripts, and
  image-OCR extractors added via an `Extractor` registry.
- **M6 -- Metadata, Classification & Confidence**
  (`v0.6.0-metadata-classification`): automatic source-type and
  subject/topic classification with stored confidence scores, plus a
  manual-correction workflow.
- **M7 -- Concept Graph** (`v0.7.0-concept-graph`): `concepts` /
  `resource_concepts` / `concept_relationships` schema, incremental
  concept-linking on ingestion, cycle-safe traversal, browse-by-concept
  UI.
- **M8 -- Local-First Retrieval & Provenance**
  (`v0.8.0-local-first-retrieval`, current):
  - Hybrid retrieval: dense vector search plus one-hop concept-graph
    expansion, merged and deduplicated by real chunk identity.
  - A standalone, independently tested sufficiency scorer
    (`app/services/sufficiency.py`) -- fail-closed by construction, so a
    query with zero relevant local content can never be labeled Local.
  - Structural provenance on every answer (`LOCAL` / `HYBRID` /
    `EXTERNAL`), with workspace-level and per-request consent gates
    before any external model call is ever made.
  - Chat reactivated end-to-end: `/api/v1/conversations` mounted, and
    `apps/web/app/chat/` live with a provenance badge, retrieval
    confidence, and an explicit external-fallback confirmation control.
  - Verified: 144 tests passing, 0 failing, 3 skipped (pending future
    milestones); Ruff and Black clean on every file this milestone
    touched. Full record in
    [`docs/milestones/MILESTONE_8.md`](docs/milestones/MILESTONE_8.md)
    and [`docs/adr/0015-retrieval-provenance.md`](docs/adr/0015-retrieval-provenance.md).

See [`CHANGELOG.md`](CHANGELOG.md) for the itemized Added/Changed/Fixed
list behind every tag above.

### What you can actually do with it today

- Register, log in, and get an isolated personal workspace.
- Upload PDFs, Word docs, PowerPoint decks, text/Markdown files, code
  files, YouTube URLs, and scanned/handwritten images -- all get
  extracted, chunked, embedded, classified, and concept-linked
  automatically.
- Browse your documents by concept, not just by filename.
- Ask questions in the chat UI and get answers that are honest about
  where they came from: answered from your own documents (Local),
  answered from your documents plus their linked concepts (Hybrid), or --
  only with your explicit consent -- answered from general knowledge
  when your own documents genuinely don't have enough (External).

### What's deliberately not built yet

- No Explain / Compare / Summarize / Search intent workflows (M9) -- chat
  today is plain question-answering with citations and provenance, not
  yet intent-routed.
- No study workflows -- quiz mode, flashcards, spaced repetition, a study
  planner (M10).
- No dedicated confidence/correction UI surfaces beyond what M6 already
  exposes for classification (M11).
- No production hardening pass -- queue-vs-BackgroundTask re-evaluation
  under real load, embedding-version migration tooling, full seed data,
  demo script (M12).

## Running it locally

### Docker Compose (recommended)

```bash
cd knowledgehub-ai
docker compose up --build
```

- Web: http://localhost:3000
- API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Liveness: http://localhost:8000/health
- Readiness: http://localhost:8000/health/ready

No `.env` file is required to run the Docker Compose stack locally.

### Running services individually

```bash
# Backend
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
# Falls back to SQLite automatically if DATABASE_URL is unset -- see
# app/core/config.py. Qdrant reachability will show as "down" in
# /health/ready unless a Qdrant instance is actually running -- retrieval
# still works in that case, falling back to an in-memory vector store
# (see app/services/vector_repo.get_vector_repository).

# Frontend (separate terminal)
cd apps/web
npm install
npm run dev
```

## Testing

```bash
cd apps/api
pip install -r requirements-dev.txt
pytest -q      # 144 passed, 3 skipped
ruff check app tests
black --check app tests
```

```bash
cd apps/web
npm install
npx tsc --noEmit
npm run build
```

## Repository layout

```
knowledgehub-ai/
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── README.md                       # module -> milestone map
│   │   │   ├── api/routes/health.py             # M1 -- live
│   │   │   ├── api/v1/routes/auth.py            # M2 -- live
│   │   │   ├── api/v1/routes/workspace.py       # M2 -- live
│   │   │   ├── api/v1/routes/documents.py       # M3/M5 -- live
│   │   │   ├── api/v1/routes/chat.py            # M8 -- live
│   │   │   ├── services/storage.py, extraction.py,
│   │   │   │   chunking.py, ingestion_service.py    # M3/M5 -- live
│   │   │   ├── services/embeddings.py, vector_repo.py  # M3/M8 -- live
│   │   │   ├── services/classification.py       # M6 -- live
│   │   │   ├── services/concept_linking.py, concept_graph.py  # M7 -- live
│   │   │   ├── services/llm.py, retrieval_service.py,
│   │   │   │   sufficiency.py                    # M8 -- live
│   │   │   ├── core/, db/, models/, schemas/
│   │   │   └── main.py
│   │   ├── alembic/versions/                     # M4-M8 migrations
│   │   └── tests/
│   └── web/
│       ├── app/
│       │   ├── page.tsx, layout.tsx              # M1 -- live
│       │   ├── login/, register/, workspace/, settings/  # M2
│       │   ├── documents/                        # M3/M5/M6 -- live
│       │   ├── concepts/                         # M7 -- live
│       │   └── chat/                             # M8 -- live
│       ├── components/, lib/
├── docs/
│   ├── adr/                # architecture decision records, 0001-0015
│   ├── milestones/          # per-milestone design/implementation/verification
│   └── architecture/
├── demo-data/                # sample source files across supported formats
├── CHANGELOG.md
├── docker-compose.yml
└── .github/workflows/ci.yml
```

## Roadmap

| # | Milestone | Scope | Status |
|---|---|---|---|
| 1 | Project Foundation | Monorepo, Docker Compose, Postgres, Qdrant, health checks | Frozen (`v0.1.0-foundation`) |
| 2 | Authentication & Workspace | Login, sessions, per-user workspace isolation | Frozen (`v0.2.0-authentication`) |
| 3 | Document Upload & Ingestion | PDF extraction, chunking, embedding, indexing | Frozen (`v0.3.0-document-ingestion`) |
| 4 | Resource Model | Polymorphic `Resource`, Alembic migrations | Frozen (`v0.4.0-resource-model`) |
| 5 | Multi-Format Ingestion | DOCX, PPTX, TXT/MD, code, YouTube, image OCR | Frozen (`v0.5.0-multi-format-ingestion`) |
| 6 | Metadata, Classification & Confidence | Auto-classification with confidence + correction UI | Frozen (`v0.6.0-metadata-classification`) |
| 7 | Concept Graph | Concepts, relationships, incremental linking, browse UI | Frozen (`v0.7.0-concept-graph`) |
| 8 | Local-First Retrieval & Provenance | Hybrid retrieval, sufficiency scorer, provenance, consent-gated fallback | **Frozen -- current** (`v0.8.0-local-first-retrieval`) |
| 9 | Intent Workflows | Explain, Compare, Summarize, Search as distinct intents | Not started |
| 10 | Study Workflows | Quiz me, Flashcards, Viva mode, Revision mode, study planner | Not started |
| 11 | Confidence & Correction UX | Dedicated UI for OCR/classification/retrieval confidence | Not started |
| 12 | Production Hardening & Portfolio Polish | Queue re-evaluation, embedding migrations, seed data, docs, demo | Not started |

Detailed architecture decisions for the whole system live in
[`docs/adr/`](docs/adr/); per-milestone design, implementation, and
verification records live in
[`docs/milestones/`](docs/milestones/).

## License

MIT -- see [LICENSE](LICENSE).
