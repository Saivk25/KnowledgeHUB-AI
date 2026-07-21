"""
PDF text extraction.

Decision: PyMuPDF (fitz) native text extraction only for the MVP.
Why over immediately adding OCR (Tesseract/OCRmyPDF): PyMuPDF is fast,
dependency-light, and reliable for born-digital PDFs, which covers the
seeded demo corpus and the stated golden path. Scanned/image-only PDFs are
explicitly out of MVP scope (see ADR-0006) and are reported with a clear
status rather than silently producing empty/garbled text.
"""

from __future__ import annotations

import fitz  # PyMuPDF

MIN_CHARS_PER_DOCUMENT = 20


class ExtractionResult:
    def __init__(self, pages: list[tuple[int, str]]):
        self.pages = pages  # list of (page_number, text)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def total_chars(self) -> int:
        return sum(len(t) for _, t in self.pages)

    @property
    def looks_scanned(self) -> bool:
        return self.total_chars < MIN_CHARS_PER_DOCUMENT


def extract_text(pdf_path: str) -> ExtractionResult:
    doc = fitz.open(pdf_path)
    pages: list[tuple[int, str]] = []
    try:
        for index in range(doc.page_count):
            page = doc.load_page(index)
            text = page.get_text("text") or ""
            pages.append((index + 1, text.strip()))
    finally:
        doc.close()
    return ExtractionResult(pages)
