# Contributing to KnowledgeHub AI

This is currently a solo-maintained portfolio project, but it's built
with real engineering discipline and outside contributions are welcome
-- bug reports, small fixes, and discussion of the roadmap especially.

## Before you start

Read [`README.md`](README.md) for the current state of the project and
[`docs/adr/`](docs/adr/) for why things are built the way they are.
Non-trivial decisions here go through an Architecture Decision Record
first; if you're proposing something that changes an existing decision,
a short discussion in an issue before a PR saves everyone time.

## Project workflow

Every milestone in this project follows the same sequence: **design ->
implementation -> verification -> freeze -> tag**. Frozen milestones
(everything with a `docs/milestones/MILESTONE_N.md` marked "Implemented
and Verified" and a matching git tag) are not retroactively modified --
if you find a real bug in frozen code, open an issue describing it rather
than sending a PR that changes frozen-milestone files directly; it'll be
addressed as a fix in the current or next milestone with its own tests.

## Development setup

```bash
# Backend
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload

# Frontend
cd apps/web
npm install
npm run dev
```

Or just `docker compose up --build` from the repo root -- see
[README.md](README.md#running-it-locally) for details.

## Before opening a PR

```bash
# Backend
cd apps/api
ruff check app tests
black --check app tests
pytest -q

# Frontend
cd apps/web
npx tsc --noEmit
npm run build
```

All four must pass. CI runs the same checks on every push and pull
request (`.github/workflows/ci.yml`).

## Code style and architecture conventions

- New source formats, classifiers, and concept-linking strategies are
  added as **plugin registries** (see `app/services/extraction.py`,
  `classification.py`, `concept_linking.py`), not if/elif chains keyed on
  file extension or type.
- External dependencies (storage, vector search, embeddings, LLM
  generation) sit behind a narrow interface with a swappable
  implementation, always with a zero-config local default (see ADR-0002,
  ADR-0004, ADR-0007).
- Schema changes are Alembic migrations, not `Base.metadata.create_all`
  (ADR-0010) -- add a new `NNNN_description.py` under
  `apps/api/alembic/versions/` and a matching `downgrade()`.
- Anything answer-provenance-related must keep provenance structural: an
  answer object should never be constructible without a provenance label
  (ADR-0015).

## Reporting bugs

Open a GitHub issue with: what you did, what you expected, what actually
happened, and (if backend-related) the relevant log output. If it's
security-sensitive, see [SECURITY.md](SECURITY.md) instead of opening a
public issue.

## Reporting security issues

Do not open a public issue -- see [SECURITY.md](SECURITY.md).
