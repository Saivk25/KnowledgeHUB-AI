## What does this change?

<!-- One or two sentences. Link the issue it addresses, if any. -->

## Why

<!-- What problem does this solve? If it touches an existing ADR or
introduces a new architectural decision, link it here. -->

## How was this tested?

<!-- Which of the following did you run, and what were the results? -->

- [ ] `ruff check app tests` (backend)
- [ ] `black --check app tests` (backend)
- [ ] `pytest -q` (backend)
- [ ] `npx tsc --noEmit` (frontend)
- [ ] `npm run build` (frontend)
- [ ] Manually verified in the running app

## Checklist

- [ ] This does not modify a file inside an already-frozen milestone
      (see `docs/milestones/`) without discussion first.
- [ ] New/changed behavior has test coverage.
- [ ] Docs (`README.md`, relevant ADR, or `docs/milestones/`) are updated
      if this changes user-facing behavior or an architectural decision.
