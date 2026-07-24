# Screenshots

This folder is where README screenshots live. All four are checked in
(Milestone 12 Item 4), captured from a real `docker compose` deployment
seeded with Milestone 12 Item 3's multi-format demo data
(`demo-data/seed.py`), against the actual running application -- not
mocked or staged. Referenced from the root `README.md`'s Screenshots
section.

Recommended shots (matches the order screenshots appear in the README):

1. **Documents library** (`/documents`) -- shows a few resources of
   different types (PDF, DOCX, code, YouTube) with status chips and
   classification badges.
2. **Concept graph / browse-by-concept** (`/concepts`) -- a concept list
   or detail view showing linked evidence.
3. **Chat with provenance** (`/chat`) -- an answer showing the
   provenance badge (Local/Hybrid/External), retrieval confidence, and
   citations.
4. **Upload flow** (`/documents/upload`) -- drag-and-drop screen, ideally
   mid-processing so a status chip is visible.

Suggested naming: `documents-library.png`, `concept-graph.png`,
`chat-provenance.png`, `upload-flow.png`. Keep each under ~500KB (PNG,
cropped to the relevant viewport) so the repo stays lightweight.
