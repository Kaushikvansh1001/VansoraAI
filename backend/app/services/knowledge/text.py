import re
import zipfile
from io import BytesIO
from pathlib import PurePath
from xml.etree import ElementTree

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.errors import AppError

MAX_BYTES = 2_000_000
MAX_CHUNKS = 40
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200

_TEXT_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
}


def safe_filename(filename: str) -> str:
    name = PurePath(filename.replace("\\", "/")).name.strip()
    if name in {"", ".", ".."} or len(name) > 200:
        raise AppError("invalid_filename", "The file name is not valid.", 400)
    return name


def prepare_file(filename: str, content: bytes) -> tuple[str, str, str, int | None]:
    """Return the stored filename, mime type, extracted text, and PDF page count."""
    if len(content) > MAX_BYTES:
        raise AppError("file_too_large", "The file must be 2 MB or smaller.", 400)
    if not content:
        raise AppError("empty_document", "The file is empty.", 400)
    name = safe_filename(filename)
    suffix = PurePath(name).suffix.lower()
    if suffix in _TEXT_TYPES:
        text = content.decode("utf-8", errors="replace")
        return name, _TEXT_TYPES[suffix], _require_text(text), None
    if suffix == ".pdf":
        text, pages = _pdf_text(content)
        return name, "application/pdf", text, pages
    if suffix == ".docx":
        return name, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", _docx_text(content), None
    raise AppError("unsupported_file", "Upload a .txt, .md, .csv, .docx, or .pdf file.", 400)


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> tuple[list[str], bool]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return [], False
    if len(cleaned) <= size:
        return [cleaned], False
    chunks: list[str] = []
    start = 0
    truncated = False
    while start < len(cleaned):
        if len(chunks) >= MAX_CHUNKS:
            truncated = True
            break
        end = min(start + size, len(cleaned))
        chunks.append(cleaned[start:end])
        if end >= len(cleaned):
            break
        start = end - overlap
    return chunks, truncated


def _require_text(text: str) -> str:
    if not text.strip():
        raise AppError("empty_document", "This file has no readable text.", 400)
    return text


def _docx_text(content: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            xml = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise AppError("unreadable_document", "This Word file could not be read.", 400) from exc
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise AppError("unreadable_document", "This Word file could not be read.", 400) from exc
    parts = [node.text for node in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t") if node.text]
    return _require_text(" ".join(parts))


def _pdf_text(content: bytes) -> tuple[str, int]:
    try:
        reader = PdfReader(BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
    except PdfReadError as exc:
        raise AppError("unreadable_pdf", "This PDF could not be read.", 400) from exc
    text = "\n".join(pages)
    return _require_text(text), len(pages)
