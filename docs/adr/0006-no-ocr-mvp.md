# ADR-0006: PyMuPDF-only text extraction, no OCR in MVP

**Status:** Accepted (MVP)

**Decision:** Extract text using PyMuPDF's native text layer only. If a PDF
has no meaningful extractable text (i.e. it is a scanned image), the
document is marked `FAILED` with a clear, honest error message rather than
silently indexing empty or garbled content.

**Alternatives considered:** Tesseract, PaddleOCR, and OCRmyPDF (all
recommended in the full enterprise SRS) would extend support to scanned
PDFs, at the cost of image rendering, preprocessing, and confidence-scoring
logic that materially increases the surface area of a 2-day build.

**Why this wins:** PyMuPDF is fast, has no system-level dependencies beyond
the Python wheel, and handles every born-digital PDF in the seeded demo
corpus reliably. Silently mishandling scanned PDFs would be worse than
refusing them outright — the UI states this limitation plainly instead of
implying OCR support that doesn't exist.

**MVP impact:** documents with `looks_scanned == True` (fewer than 20 total
extracted characters) fail fast with `SCANNED_PDF_UNSUPPORTED`.

**Revisit when:** Phase 2 adds an OCR fallback stage in the ingestion
pipeline for exactly this failure case.
