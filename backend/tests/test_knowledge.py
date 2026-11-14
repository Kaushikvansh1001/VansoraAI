import uuid
import zipfile
from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.core.errors import AppError
from app.services.ai.exceptions import EmbeddingError
from app.models.enums import DocumentStatus
from app.models.knowledge import Document, DocumentChunk
from app.services.ai.embeddings import EmbeddingService
from app.services.ai.models import GenerationOutcome, ProviderResponse, TokenUsage
from app.services.knowledge.service import KnowledgeService
from app.services.knowledge.text import chunk_text, prepare_file
from app.repositories.knowledge import KnowledgeRepository


class FakeDb:
    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        return None

    def refresh(self, _obj) -> None:
        return None

    def scalar(self, _statement):
        return None


class MemoryStorage:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.paths: list[str] = []

    def upload(self, object_path: str, content: bytes, content_type: str) -> str:
        if self.fail:
            raise AppError("storage_failed", "The file could not be stored.", 502)
        self.paths.append(object_path)
        return object_path

    def delete(self, object_path: str) -> None:
        self.paths = [path for path in self.paths if path != object_path]


def embedder():
    return EmbeddingService(embedder=lambda texts: [[0.02] * 384 for _text in texts])


def test_text_file_is_accepted():
    name, mime, text, pages = prepare_file("notes.txt", b"Refunds take 30 days.")
    assert name == "notes.txt"
    assert mime == "text/plain"
    assert "30 days" in text
    assert pages is None


def test_wrong_type_and_oversize_are_rejected():
    with pytest.raises(AppError) as kind:
        prepare_file("program.exe", b"hello")
    assert kind.value.code == "unsupported_file"
    with pytest.raises(AppError) as size:
        prepare_file("notes.txt", b"x" * 2_000_001)
    assert size.value.code == "file_too_large"


def test_word_file_text_is_extracted():
    document = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>Refunds take 30 days.</w:t></w:r></w:p></w:body>
</w:document>"""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document)
    name, _mime, text, pages = prepare_file("cv.docx", buffer.getvalue())
    assert name == "cv.docx"
    assert "30 days" in text
    assert pages is None


def test_blank_pdf_is_rejected():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = BytesIO()
    writer.write(buffer)
    with pytest.raises(AppError) as exc:
        prepare_file("scan.pdf", buffer.getvalue())
    assert exc.value.code == "empty_document"


def test_chunks_overlap_and_stop_at_the_cap():
    chunks, truncated = chunk_text("word " * 20000)
    assert truncated is True
    assert len(chunks) == 40
    assert chunks[1][:20] in chunks[0]


def test_search_stays_inside_the_organization():
    statement = KnowledgeRepository.search_statement(uuid.uuid4(), [0.1] * 384, None, 4)
    compiled = str(statement.compile())
    assert "organization_id" in compiled
    assert "document_chunks" in compiled


def test_upload_stores_the_file_under_the_organization_and_indexes_it():
    db = FakeDb()
    storage = MemoryStorage()
    organization_id = uuid.uuid4()
    document = KnowledgeService(db, storage=storage, embeddings=embedder()).upload(
        organization_id=organization_id,
        user_id=uuid.uuid4(),
        filename="notes.txt",
        content=b"Refunds take 30 days.",
    )
    assert document.status == DocumentStatus.ready
    assert storage.paths[0].startswith(f"{organization_id}/{document.id}/")
    assert any(isinstance(row, DocumentChunk) and row.content.startswith("Refunds") for row in db.added)


def test_storage_failure_keeps_a_failed_document():
    db = FakeDb()
    document = KnowledgeService(db, storage=MemoryStorage(fail=True), embeddings=embedder()).upload(
        organization_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        filename="notes.txt",
        content=b"Refunds take 30 days.",
    )
    assert document.status == DocumentStatus.failed
    assert document.error_message == "The file could not be stored."


def test_index_failure_removes_the_stored_file():
    class Broken:
        def embed_texts(self, _texts):
            raise EmbeddingError("down")

    storage = MemoryStorage()
    document = KnowledgeService(FakeDb(), storage=storage, embeddings=Broken()).upload(
        organization_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        filename="notes.txt",
        content=b"Refunds take 30 days.",
    )
    assert document.status == DocumentStatus.failed
    assert storage.paths == []


def test_answer_uses_the_retrieved_passage_and_cites_it():
    seen = {}

    class Manager:
        def generate(self, request, **kwargs):
            seen["prompt"] = request.prompt
            seen["feature"] = kwargs["feature"]
            usage = TokenUsage(4, 6, "provider")
            response = ProviderResponse("gemini", "gemini-flash-lite-latest", "Refunds take 30 days.", usage, 12)
            return GenerationOutcome(response, None)

    chunk = Document(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        uploaded_by=uuid.uuid4(),
        filename="unused",
        storage_path="unused",
        mime_type="text/plain",
        size_bytes=1,
        status=DocumentStatus.ready,
    )
    passage = DocumentChunk(
        id=uuid.uuid4(),
        document_id=chunk.id,
        organization_id=chunk.organization_id,
        chunk_index=0,
        content="Refunds take 30 days.",
        token_count=4,
        embedding=[0.1] * 384,
    )

    def retrieve(_organization_id, _vector, _document_id):
        return [(passage, "policy.txt")]

    answer = KnowledgeService(FakeDb(), embeddings=embedder(), manager=Manager(), retriever=retrieve).ask(
        organization_id=chunk.organization_id,
        user_id=uuid.uuid4(),
        question="How long do refunds take?",
        document_id=None,
    )
    assert "policy.txt" in seen["prompt"]
    assert "Refunds take 30 days." in seen["prompt"]
    assert "cannot find it" in seen["prompt"]
    assert seen["feature"] == "knowledge"
    assert answer.answer == "Refunds take 30 days."
    assert answer.citations[0].filename == "policy.txt"
    assert answer.citations[0].document_id == chunk.id


def test_ask_without_a_document_does_not_call_the_model():
    class Manager:
        def generate(self, request, **kwargs):
            raise AssertionError("The model should not be called.")

    def retrieve(_organization_id, _vector, _document_id):
        return []

    with pytest.raises(AppError) as exc:
        KnowledgeService(FakeDb(), embeddings=embedder(), manager=Manager(), retriever=retrieve).ask(
            organization_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            question="What is the policy?",
            document_id=None,
        )
    assert exc.value.code == "no_documents"
