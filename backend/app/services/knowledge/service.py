import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.models.enums import DocumentStatus, MessageRole
from app.models.knowledge import Conversation, Document, DocumentChunk, Message
from app.repositories.knowledge import KnowledgeRepository
from app.services.ai.exceptions import EmbeddingError, ProviderChainFailed
from app.services.ai.models import GenerationRequest
from app.services.ai.provider_manager import ProviderManager
from app.services.ai.usage_tracker import UsageTracker
from app.services.audit import record_audit
from app.services.knowledge.text import chunk_text, prepare_file
from app.services.storage import SupabaseStorage, build_object_path

@dataclass(frozen=True)
class Citation:
    document_id: uuid.UUID
    filename: str
    chunk_index: int
    excerpt: str


@dataclass(frozen=True)
class Answer:
    answer: str
    provider: str
    model: str
    citations: list[Citation]


class KnowledgeService:
    def __init__(
        self,
        db: Session,
        storage: SupabaseStorage | None = None,
        embeddings=None,
        manager: ProviderManager | None = None,
        settings: Settings | None = None,
        retriever=None,
    ) -> None:
        self.db = db
        self.storage = storage or SupabaseStorage()
        self.embeddings = embeddings
        self.manager = manager
        self.settings = settings
        self.retriever = retriever
        self.documents = KnowledgeRepository(db)

    def list_documents(self, organization_id: uuid.UUID) -> list[Document]:
        return self.documents.list_documents(organization_id)

    def upload(self, *, organization_id: uuid.UUID, user_id: uuid.UUID, filename: str, content: bytes) -> Document:
        name, mime_type, text, page_count = prepare_file(filename, content)
        pieces, truncated = chunk_text(text)
        if not pieces:
            raise AppError("empty_document", "This file has no readable text.", 400)
        document = Document(
            id=uuid.uuid4(),
            organization_id=organization_id,
            uploaded_by=user_id,
            filename=name,
            storage_path="",
            mime_type=mime_type,
            size_bytes=len(content),
            status=DocumentStatus.pending,
            page_count=page_count,
            file_metadata={"truncated": truncated},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.db.add(document)
        self.db.flush()
        document.storage_path = build_object_path(organization_id, document.id, name)
        try:
            self.storage.upload(document.storage_path, content, mime_type)
            self._index(document, pieces)
        except AppError as exc:
            document.status = DocumentStatus.failed
            document.error_message = exc.message
            self.db.flush()
            self.db.refresh(document)
            return document
        except EmbeddingError:
            document.status = DocumentStatus.failed
            document.error_message = "The document could not be indexed."
            self.db.flush()
            self.db.refresh(document)
            return document
        record_audit(
            self.db,
            action="document.upload",
            resource_type="document",
            actor_id=user_id,
            organization_id=organization_id,
            resource_id=document.id,
            details={"filename": name},
        )
        self.db.flush()
        self.db.refresh(document)
        return document

    def ask(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        question: str,
        document_id: uuid.UUID | None,
    ) -> Answer:
        question = question.strip()
        if document_id is not None and self.documents.get_document(organization_id, document_id) is None:
            raise AppError("not_found", "That document is not in this organization.", 404)
        vector = self._embedder().embed_text(question)
        rows = self._retrieve(organization_id, vector, document_id)
        if not rows:
            raise AppError(
                "no_documents",
                "Upload a document with readable text before asking a question.",
                400,
            )
        citations = [
            Citation(
                document_id=chunk.document_id,
                filename=filename,
                chunk_index=chunk.chunk_index,
                excerpt=chunk.content[:280],
            )
            for chunk, filename in rows
        ]
        prompt = _prompt(question, citations, [chunk.content for chunk, _filename in rows])
        try:
            outcome = self._provider().generate(
                GenerationRequest(prompt=prompt),
                organization_id=organization_id,
                user_id=user_id,
                feature="knowledge",
            )
        except ProviderChainFailed as exc:
            raise AppError("providers_unavailable", "No model could answer from this document.", 502) from exc
        result = outcome.response
        conversation = Conversation(
            id=uuid.uuid4(),
            organization_id=organization_id,
            user_id=user_id,
            title=question[:80],
        )
        self.db.add(conversation)
        self.db.flush()
        stored = [
            {
                "document_id": str(item.document_id),
                "filename": item.filename,
                "chunk_index": item.chunk_index,
                "excerpt": item.excerpt,
            }
            for item in citations
        ]
        self.db.add(
            Message(
                id=uuid.uuid4(),
                conversation_id=conversation.id,
                organization_id=organization_id,
                role=MessageRole.user,
                content=question,
                citations=[],
            )
        )
        self.db.add(
            Message(
                id=uuid.uuid4(),
                conversation_id=conversation.id,
                organization_id=organization_id,
                role=MessageRole.assistant,
                content=result.text,
                citations=stored,
                provider=result.provider,
                model=result.model,
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
            )
        )
        self.db.flush()
        return Answer(answer=result.text, provider=result.provider, model=result.model, citations=citations)

    def _index(self, document: Document, pieces: list[str]) -> None:
        vectors = self._embedder().embed_texts(pieces)
        for index, (piece, vector) in enumerate(zip(pieces, vectors, strict=True)):
            self.db.add(
                DocumentChunk(
                    id=uuid.uuid4(),
                    document_id=document.id,
                    organization_id=document.organization_id,
                    chunk_index=index,
                    content=piece,
                    token_count=max(1, len(piece) // 4),
                    embedding=vector,
                    chunk_metadata={},
                )
            )
        document.status = DocumentStatus.ready
        document.error_message = None

    def _retrieve(self, organization_id, vector, document_id):
        if self.retriever is not None:
            return self.retriever(organization_id, vector, document_id)
        return self.documents.search(organization_id, vector, document_id, limit=4)

    def _embedder(self):
        if self.embeddings is None:
            from app.services.ai.embeddings import EmbeddingService

            self.embeddings = EmbeddingService()
        return self.embeddings

    def _provider(self) -> ProviderManager:
        if self.manager is None:
            settings = self.settings or get_settings()
            self.manager = ProviderManager(settings, sink=UsageTracker(self.db))
        return self.manager


def _prompt(question: str, citations: list[Citation], passages: list[str]) -> str:
    blocks = []
    for number, (citation, passage) in enumerate(zip(citations, passages, strict=True), start=1):
        blocks.append(f"[{number}] {citation.filename}\n{passage}")
    joined = "\n\n".join(blocks)
    return (
        "Answer the question using only the passages below. "
        "Start with the direct answer in plain sentences. Do not use markdown or asterisks. "
        "If the passages do not contain the answer, say that you cannot find it in the uploaded documents. "
        "Do not add facts from outside these passages.\n\n"
        f"Passages:\n{joined}\n\nQuestion:\n{question}"
    )
