# Demo Script

A guided, ~10-15 minute walkthrough of KnowledgeHub AI using the seeded
demo workspace from `demo-data/seed.py` (Milestone 12, Section 4.3). Every
step below references a route or page that exists in this codebase today
-- nothing hypothetical. Every "Expected outcome" was verified live
against a real, running `docker compose` deployment during Milestone 12
(not inferred from tests alone) -- including the concept-dedup
concurrency fix (Section 12) and the workspace-stats fix (Section 13)
that make Steps 4 and 5 below hold reliably. Screenshots in
`docs/assets/screenshots/` were captured from this exact walkthrough.

## Prerequisites

1. `docker compose up -d --build` (starts Postgres, Qdrant, the API, and
   the frontend -- see `docker-compose.yml`; `--build` ensures you have
   the latest code and migrations, including Milestone 12's fixes).
2. Seed the workspace:
   ```
   python demo-data/seed.py --email demo@example.com
   ```
   **Use a real-looking email, not the script's own `--email` default**
   (`demo@knowledgehub.local`) -- the `.local` TLD is rejected by the
   API's email validator with a `422`, a real, verified quirk of this
   deployment's validation rules, not a seeding bug. `demo@example.com`
   with the default password (`DemoPassword123`) works. This uploads the
   three original PDFs plus the five `data_retention_policy.*` fixtures
   through the real `/api/v1/documents` endpoint and waits for each to
   reach `READY` -- see `demo-data/README.md`.
3. Open the frontend (`http://localhost:3000`) and log in with the same
   email/password you passed to `seed.py`.

## 1. Documents library (`/documents`) -- ~2 min

Open the Documents page. You should see all eight seeded resources, each
with a status chip and a classification badge:

- `Expense_Policy.pdf`, `Employee_Handbook_Excerpt.pdf`,
  `Vendor_Contract_Summary.pdf` -- the three original demo PDFs.
- `data_retention_policy.docx`, `.pptx`, `.md`, `.py`, `.png` -- the
  Milestone 12 multi-format fixtures.

**Expected outcome:** every row shows a green "Ready" status chip (see
`components/StatusBadge.tsx`). Classification badges (`components/
CategoryBadge.tsx`) mostly read "Other" -- the zero-config
`LocalHeuristicClassifier` is a small keyword heuristic, not a real
model, so it doesn't confidently categorize generic policy prose. One
exception: `data_retention_policy.pptx` classifies as "Lecture" (its
slide-style bullet structure trips the heuristic's lecture keywords) --
worth calling out as an honest illustration of a zero-config local
classifier's limits, not a bug.

## 2. Upload flow (`/documents/upload`) -- ~2 min

Drag any supported file onto the upload page (or click to browse). The
accepted-extension list shown on the page matches the backend's real
Extractor registry (`app/services/extraction.py`): PDF, DOCX, PPTX,
TXT/Markdown, common source-code extensions, and PNG/JPG.

**Expected outcome:** after upload, you're taken to the new document's
detail page. If you switch back to `/documents` quickly, the row briefly
shows a "Processing" chip before flipping to "Ready" -- ingestion
(extract -> classify -> chunk -> embed -> index -> concept-link) runs as
a background task (ADR-0005), so the status chip genuinely updates live
rather than being pre-computed at upload time.

## 3. Document detail + study tools (`/documents/{id}`) -- ~3 min

Open `data_retention_policy.docx` from the library.

- **Classification & correction history:** the page shows the
  auto-classified category/subject and (Milestone 11) a correction
  history log plus a "Re-run extraction" button, wired to
  `POST /documents/{id}/reextract`.
- **Summarize this document:** click it (Milestone 9's on-demand
  Summarize intent). **Expected outcome:** a short summary grounded only
  in this document's own chunks, with a `LOCAL` provenance origin (no
  external knowledge involved).
- **Generate a quiz** / **Generate flashcards** (Milestone 10, shared
  `components/StudyPanels.tsx`, also used on the concept detail page).
  **Expected outcome:** a small set of questions/cards generated from
  this document's real content -- try answering one quiz question to see
  it graded against the actual source text, not a canned answer.

## 4. Concept graph (`/concepts` -> `/concepts/{id}`) -- ~3 min

Open `/concepts` and find **"Data Retention Policy."** This is the
Milestone 12 cross-format demonstration: five fixtures of five different
formats (DOCX, PPTX, Markdown, Python, PNG/OCR) were deliberately given
the same filename stem, so `LocalConceptLinker`'s filename-fallback
mechanism (`app/services/concept_linking.py`) and
`concept_graph.resolve_concept()`'s exact-name dedup (Milestone 7) fold
all five into one concept.

That dedup is now backed by more than an application-layer check: a
concurrency race discovered during this milestone's own screenshot
capture (five near-simultaneous uploads could, under real concurrent
`BackgroundTask` execution, each pass the dedup check before any
committed, producing duplicate concepts) is closed by a partial unique
database index plus an `IntegrityError`-recovery path in
`resolve_concept()` (Section 12 of `docs/milestones/MILESTONE_12.md`).
The outcome below is what a real, concurrent seeding run against a live
deployment produces today, not just what a serial test run produces.

**Expected outcome:** the concept detail page reports **5 evidence
links**, and the Evidence list shows all five source filenames
(`data_retention_policy.docx/.pptx/.md/.py/.png`) -- one concept, real
evidence spanning five distinct source types.

## 5. Chat with provenance (`/chat`) -- ~3 min

The page header reports "8 ready documents in this workspace" -- if it
ever reports 0 despite Ready documents existing, that's the exact
regression Milestone 12 Section 13 found and fixed (`GET /workspace` not
returning document-count stats); a rebuilt `api`/`web` image resolves it.

This deployment runs zero-config -- local hash-based embeddings, no
OpenAI key -- so the two chat modes behave differently, and both
behaviors are real and worth showing:

- **Search mode** (toggle at the bottom of the compose bar) is the
  reliable way to see the full provenance/citation UI. Ask e.g. *"data
  retention policy financial records"* or *"financial records retained
  seven years."* **Expected outcome:** an answer badged **"From your
  documents"** with a confidence percentage, a "Low confidence match --
  here is a best-effort synthesis" note (honest about the local
  embedding provider's approximate, non-semantic matching), and a
  citation pill linking back to the specific source page.
- **Explain mode** (the default) runs an LLM-based sufficiency check
  before answering. With no OpenAI key configured and local hash
  embeddings, many natural-language questions genuinely don't clear that
  bar -- **expected outcome** is often *"I could not find sufficient
  evidence in your authorized documents to answer that,"* with an
  **"Answer using general knowledge instead"** button. This is the
  system's fail-closed design (Milestone 8) working as intended, not a
  defect: it would rather admit insufficiency than fabricate an answer,
  and switching to Search mode (above) confirms the same underlying
  content is genuinely retrievable.

Configuring an OpenAI key (`EMBEDDING_PROVIDER=openai` plus an API key,
see `app/core/config.py`) gives Explain mode real semantic matching and
is the more typical way this mode is used; the zero-config behavior
above is what a reviewer running `docker compose up` with no keys will
actually see.

## 6. Optional: study workflows (`/revision`, `/study-plan`) -- ~2 min

Both pages operate over whatever quiz/flashcard/viva activity exists in
the seeded workspace's history (Milestone 10). If you completed a quiz
in Step 3, `/revision` will surface it as a recent signal; `/study-plan`
lets you pick two or more targets (documents or concepts) and generate a
day-by-day plan. Quick to click through but not essential to the core
cross-format-retrieval story above -- feel free to skip under time
pressure.

## Wrap-up

What this walkthrough demonstrates end to end: real multi-format
ingestion (five formats beyond the original PDF-only demo), real concept
deduplication across formats under genuine concurrent load (not a
scripted shortcut, and now backed by a database constraint after a real
race condition was found and fixed), and real retrieval with honest
provenance labeling -- including the honest cases (fail-closed Explain
answers, low-confidence Search matches) rather than only the flattering
ones. All of it runs through the same `/api/v1` surface a script or
another client could drive, and all of it was re-verified live against a
running deployment during Milestone 12, not just in `pytest`.
