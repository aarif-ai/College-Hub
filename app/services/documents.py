"""Safe handling of uploaded event PDFs and cover images."""
import uuid
from pathlib import Path

from flask import current_app
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import EventDocument
from app.services.ai.extraction import extract_pdf_text
from app.services.errors import ServiceError

MAX_COVER_BYTES = 3 * 1024 * 1024


def _root() -> Path:
    root = Path(current_app.config["UPLOAD_FOLDER"])
    root.mkdir(parents=True, exist_ok=True)
    return root


def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _size(file_storage) -> int:
    stream = file_storage.stream
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(0)
    return size


def absolute_path(relative_path: str) -> Path:
    """Resolve a stored relative path, refusing anything outside uploads."""
    root = _root().resolve()
    path = (root / relative_path).resolve()
    if root not in path.parents:
        raise ServiceError("Invalid file path.", "invalid_path")
    return path


# ---------------------------------------------------------------------------
# PDF documents
# ---------------------------------------------------------------------------
def save_document(file_storage, event, uploader) -> EventDocument:
    """Validate and store an official event PDF, then extract its text."""
    if file_storage is None or not file_storage.filename:
        raise ServiceError("Choose a PDF file to upload.", "validation")

    original = file_storage.filename
    if _extension(original) not in current_app.config["ALLOWED_DOCUMENT_EXTENSIONS"]:
        raise ServiceError("Only PDF files are allowed.", "validation")

    size = _size(file_storage)
    max_bytes = current_app.config["MAX_UPLOAD_MB"] * 1024 * 1024
    if size == 0:
        raise ServiceError("The uploaded file is empty.", "validation")
    if size > max_bytes:
        raise ServiceError(
            f"The file is too large. Maximum size is {current_app.config['MAX_UPLOAD_MB']} MB.",
            "validation",
        )
    if file_storage.stream.read(5) != b"%PDF-":
        raise ServiceError("This file does not look like a real PDF.", "validation")
    file_storage.stream.seek(0)

    safe = secure_filename(original) or "document.pdf"
    stored = f"event{event.id}_{uuid.uuid4().hex[:10]}_{safe}"
    relative = f"documents/{stored}"
    target = absolute_path(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    file_storage.save(target)

    try:
        text, pages = extract_pdf_text(target)
    except Exception:  # unreadable or encrypted PDF
        target.unlink(missing_ok=True)
        raise ServiceError("The PDF could not be read. It may be damaged or password protected.",
                           "validation")

    document = EventDocument(
        event_id=event.id,
        uploader_id=uploader.id,
        original_filename=original[:255],
        stored_filename=stored,
        file_path=relative,
        size_bytes=size,
        page_count=pages,
        extracted_text=text,
    )
    db.session.add(document)
    db.session.commit()
    return document


def delete_document(document: EventDocument) -> None:
    try:
        absolute_path(document.file_path).unlink(missing_ok=True)
    except ServiceError:
        pass
    db.session.delete(document)
    db.session.commit()


# ---------------------------------------------------------------------------
# Cover images
# ---------------------------------------------------------------------------
def save_cover_image(file_storage) -> str:
    """Validate and store a cover image. Returns the stored filename."""
    if file_storage is None or not file_storage.filename:
        raise ServiceError("Choose an image to upload.", "validation")
    ext = _extension(file_storage.filename)
    if ext not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        raise ServiceError("Cover images must be PNG, JPG or WEBP.", "validation")
    if _size(file_storage) > MAX_COVER_BYTES:
        raise ServiceError("Cover image is too large (maximum 3 MB).", "validation")
    try:
        with Image.open(file_storage.stream) as img:
            img.verify()
    except (UnidentifiedImageError, OSError):
        raise ServiceError("That file is not a valid image.", "validation")
    file_storage.stream.seek(0)

    stored = f"{uuid.uuid4().hex}.{'jpg' if ext == 'jpeg' else ext}"
    target = _root() / "covers" / stored
    target.parent.mkdir(parents=True, exist_ok=True)
    file_storage.save(target)
    return stored


def cover_directory() -> Path:
    return _root() / "covers"


# ---------------------------------------------------------------------------
# Profile photos
# ---------------------------------------------------------------------------
AVATAR_PX = 400


def save_avatar(file_storage) -> str:
    """Validate a profile photo, crop it square and re-encode it as JPEG.

    Re-encoding with Pillow drops metadata (such as GPS) and anything that is
    not real pixel data. Returns the stored filename.
    """
    from PIL import ImageOps
    if file_storage is None or not file_storage.filename:
        raise ServiceError("Choose a photo to upload.", "validation")
    if _extension(file_storage.filename) not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        raise ServiceError("Profile photos must be PNG, JPG or WEBP.", "validation")
    limit = current_app.config["MAX_AVATAR_MB"] * 1024 * 1024
    if _size(file_storage) > limit:
        raise ServiceError(f"Photo is too large (maximum {current_app.config['MAX_AVATAR_MB']} MB).",
                           "validation")
    try:
        with Image.open(file_storage.stream) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            img = ImageOps.fit(img, (AVATAR_PX, AVATAR_PX))
            stored = f"{uuid.uuid4().hex}.jpg"
            target = _root() / "avatars" / stored
            target.parent.mkdir(parents=True, exist_ok=True)
            img.save(target, "JPEG", quality=88)
    except (UnidentifiedImageError, OSError, ValueError):
        raise ServiceError("That file is not a valid image.", "validation")
    return stored


def delete_avatar(filename: str | None) -> None:
    if filename:
        (_root() / "avatars" / Path(filename).name).unlink(missing_ok=True)


def avatar_directory() -> Path:
    return _root() / "avatars"
