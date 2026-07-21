"""
Test helper for building real PDFs with PyMuPDF.

This module is only imported by test modules that guard the import with
`pytest.importorskip("fitz")` first, because PyMuPDF is not a Milestone 1
dependency (see requirements.txt) -- it belongs to the ingestion milestone.
Importing it unconditionally here would break test collection for anyone
running the Milestone 1 test suite without that package installed.
"""

import fitz  # PyMuPDF


def make_sample_pdf(path: str, page_texts: list[str]) -> None:
    """Builds a real, born-digital PDF with PyMuPDF so extraction tests hit
    the actual PyMuPDF text-extraction code path rather than a mock."""
    doc = fitz.open()
    for text in page_texts:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=11)
    doc.save(path)
    doc.close()
