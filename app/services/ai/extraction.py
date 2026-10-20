"""Step 1 - document extraction: PDF -> plain text with page markers."""
from pathlib import Path

from pypdf import PdfReader

MAX_PAGES = 60
MAX_CHARS = 200_000


def extract_pdf_text(path: Path) -> tuple[str, int]:
    """Return ``(text, page_count)``; text contains ``[[Page N]]`` markers.

    Raises an exception if the PDF is unreadable or password protected.
    Scanned PDFs without a text layer return an almost empty string.
    """
    reader = PdfReader(str(path))
    if reader.is_encrypted and reader.decrypt("") == 0:
        raise ValueError("PDF is password protected")

    pages = []
    for number, page in enumerate(reader.pages[:MAX_PAGES], start=1):
        text = (page.extract_text() or "").strip()
        pages.append(f"[[Page {number}]]\n{text}")
    return "\n\n".join(pages)[:MAX_CHARS], len(reader.pages)
