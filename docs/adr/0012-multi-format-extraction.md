# ADR-0012: Multi-format ingestion via an Extractor registry

**Status:** Accepted (Milestone 5)

**Decision:** Generalize Milestone 3's single hardcoded PyMuPDF call
(`extract_text(pdf_path)`) into an `Extractor` registry
(`app/services/extraction.py`), matching the pluggable-provider pattern
already proven by `EmbeddingProvider` (`services/embeddings.py`) and
`VectorRepository` (`services/vector_repo.py`). One concrete class per
format (`PdfExtractor`, `DocxExtractor`, `PptxExtractor`, `TextExtractor`,
`CodeExtractor`, `ImageOcrExtractor`), all returning the same
`ExtractionResult` (a list of `ExtractedUnit`: text + sequential position +
confidence). `get_extractor_for(filename)` resolves the right one by
extension; `ingestion_service.py` never branches on format.

## Sub-decisions

**1. Keep `page_number` as the field name everywhere downstream**, rather
than renaming to something generic. For PDF it is a real page; for PPTX a
slide number; for every single-unit format (DOCX, TXT/MD, code, a fetched
YouTube transcript) it is always `1`. This avoids touching
`ResourcePage`/`ResourceChunk`, the dormant citation/retrieval modules, or
the frontend Source Viewer, none of which are in this milestone's scope --
the same "extend the meaning, keep the name" precedent Milestone 4 set for
`VectorPoint.document_id`.

**2. No per-format chunking strategy.** DOCX/TXT/MD/code all produce one
unit (the whole file); chunking still applies the existing word-window
chunker uniformly. A heading-aware Markdown chunker or a tree-sitter-based
code chunker would be real value, but the Architecture doc explicitly flags
"chunking heterogeneity complicates ranking" as something to *evaluate* at
Milestone 8 (Local-First Retrieval), not solve speculatively now. Building a
chunker registry ahead of that evaluation would be scope creep against a
problem that hasn't been measured yet.

**3. OCR engine: pytesseract + Tesseract, not EasyOCR.** Both were
considered. EasyOCR is pure-pip (no system binary) but pulls in PyTorch --
a large image-size and CPU-latency cost far beyond anything else this
project has added. pytesseract requires one new system package
(`tesseract-ocr`, added to the Dockerfile) but is fast, lightweight, and --
critically -- exposes a real per-word confidence score
(`pytesseract.image_to_data`), which is what `Resource.extraction_confidence`
actually needs to be honest (DRR Section 9: confidence must be the engine's
real reported number, never invented). This is the first system-level
(non-pip) dependency in the API image, landing exactly in the milestone that
needs it, matching the "new dependency in the milestone that needs it"
discipline already established for PyMuPDF (M3) and Alembic (M4).

**4. Code files: a fixed extension allowlist, no language-aware parsing.**
`.py .js .jsx .ts .tsx .java .c .h .cpp .hpp .go .rs .rb .php .cs .kt .sql
.sh` are read as plain text, one unit per file. Tree-sitter-based semantic
chunking (function/class boundaries) is real value for code specifically,
but is explicitly out of this milestone's approved scope -- code-aware
chunking is Vision v2 Phase 2 work, not MVP.

**5. YouTube transcripts are not a new "fileless" content type.** A video
has no uploaded file, but rather than building Vision v2's Capture
(fileless, `content_source=CAPTURE`) path a milestone early, the transcript
is fetched server-side (`app/services/youtube.py`), saved as a plain `.txt`
file through the existing `LocalStorage`, and ingested as an ordinary
`content_source=FILE` resource. This reuses 100% of the existing pipeline,
status machine, and retry/delete routes with zero new branches -- the
"Capture reuses the same pipeline" principle from Vision v2 Section 4,
applied one milestone early because it happens to require no new schema or
workflow to do so.

**6. YouTube URL validation is not a general URL fetcher.**
`extract_video_id` only accepts `youtube.com`/`youtu.be` URL shapes and
extracts an 11-character video ID via regex; the only outbound network call
is `youtube_transcript_api`'s own request to YouTube's caption endpoint for
that specific ID. This is narrower than the general "fetch this URL"
SSRF risk the DRR (Section 6) flags for a future Capture/article-fetch
feature -- there is no code path here that opens a socket to an arbitrary,
user-supplied host.

**7. `extraction_confidence` is a new nullable column (migration 0003),
not surfaced in the API yet.** It exists so the number is real and stored
from the moment OCR exists at all (DRR Section 9's auditability principle),
but the confidence UX itself (badges, correction flows) is Roadmap Milestone
10/11's job, not this one's.

**Alternatives considered:** A single growing if/elif chain keyed on file
extension inside `ingestion_service.py` -- rejected because it is exactly
the anti-pattern the existing plugin registries were built to avoid, and it
would make adding the next format (a later capture extractor) require
editing ingestion logic instead of adding one file.

**Revisit when:** a future milestone needs per-format chunking (M8's
retrieval-ranking evaluation may surface this), or Capture (Vision v2
Section 4) needs true fileless resources for input types that have no
sensible "save as a virtual file" representation (e.g. a live paste with no
stable content until the user finishes typing).
