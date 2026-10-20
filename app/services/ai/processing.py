"""Step 2 - document processing: build labelled chunks of official text.

Two kinds of trusted material are used:

* the structured event listing (venue, date, time, capacity, ...)
* text extracted from PDFs uploaded by the organizer

Nothing else is ever given to the assistant.
"""
import re
from dataclasses import dataclass

from app.utils import fmt_datetime, fmt_time

LISTING_SOURCE = "Official event listing"
_PAGE_MARKER = re.compile(r"\[\[Page (\d+)\]\]")
_UNIT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_ABBREV = re.compile(r"\b(Dr|Prof|Mr|Mrs|Ms|Mx|St|Sr|Jr|vs|etc|No|Fig|[A-Z])\.(?=\s)")
_DOT = "\u2024"  # one-dot leader: stands in for a dot that does not end a sentence


def split_units(text: str) -> list[str]:
    """Split text into sentences/lines without breaking after "Dr." and similar."""
    protected = _ABBREV.sub(lambda m: m.group(1) + _DOT, text)
    pieces = [p.strip().replace(_DOT, ".") for p in _UNIT_SPLIT.split(protected) if p.strip()]
    return pieces


MAX_CHUNK_CHARS = 450


@dataclass
class Chunk:
    source: str
    text: str

    @property
    def units(self) -> list[str]:
        """Sentence/line sized pieces, with broken lines stitched back together."""
        pieces = split_units(self.text)
        units: list[str] = []
        for piece in pieces:
            if units and not re.search(r"[.!?:]$", units[-1]):
                units[-1] = f"{units[-1]} {piece}"  # line wrapped mid-sentence
            else:
                units.append(piece)
        return units


def _group_units(text: str, source: str) -> list[Chunk]:
    """Split ``text`` into chunks of consecutive sentences up to a size limit."""
    pieces = split_units(text)
    chunks, current = [], ""
    for piece in pieces:
        if current and len(current) + len(piece) > MAX_CHUNK_CHARS:
            chunks.append(Chunk(source, current))
            current = ""
        current = f"{current}\n{piece}" if current else piece
    if current:
        chunks.append(Chunk(source, current))
    return chunks


def event_listing_chunks(event) -> list[Chunk]:
    """Facts taken directly from the approved event record."""
    facts = [
        f"Event title: {event.title}.",
        f"Category: {event.category}.",
        f"Venue and location: {event.venue}.",
        (
            f"Date and time: the event is on {event.event_date.strftime('%A, %d %B %Y')}, "
            f"starting at {fmt_time(event.start_time)} and ending at {fmt_time(event.end_time)}."
        ),
        f"Registration deadline: {fmt_datetime(event.registration_deadline)}.",
        (
            f"Capacity: {event.capacity} seats in total, "
            f"{event.seats_left} seats are currently available."
        ),
        f"Organiser and contact person: {event.organizer.name}.",
    ]
    if event.club:
        facts.append(f"Hosting club or community: {event.club.name}.")
    if event.department:
        facts.append(f"Department: {event.department}.")
    if event.faculty_coordinator:
        facts.append(f"Faculty coordinator: {event.faculty_coordinator}.")
    if event.eligibility:
        facts.append(f"Eligibility, who can attend: {event.eligibility}")
    if event.contact_info:
        facts.append(f"Contact information: {event.contact_info}.")
    chunks = [Chunk(LISTING_SOURCE, fact) for fact in facts]
    chunks.extend(_group_units(event.description or "", LISTING_SOURCE))
    for text in (event.schedule, event.rules):
        if text:
            chunks.extend(_group_units(text, LISTING_SOURCE))
    return chunks


def document_chunks(document) -> list[Chunk]:
    """Chunks from one uploaded PDF, labelled with file name and page."""
    text = document.extracted_text or ""
    parts = _PAGE_MARKER.split(text)
    # split() gives: [before, "1", page1_text, "2", page2_text, ...]
    chunks: list[Chunk] = []
    for index in range(1, len(parts) - 1, 2):
        page_no, page_text = parts[index], parts[index + 1]
        source = f"{document.original_filename}, page {page_no}"
        chunks.extend(_group_units(page_text, source))
    return chunks


def build_chunks(event) -> list[Chunk]:
    chunks = event_listing_chunks(event)
    for document in event.documents:
        chunks.extend(document_chunks(document))
    return chunks
