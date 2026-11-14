import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import DocumentStatus
from app.models.knowledge import Document, DocumentChunk
from app.services.knowledge.sample import SAMPLE_FILENAME


class KnowledgeRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_documents(self, organization_id: uuid.UUID) -> list[Document]:
        return list(
            self.db.scalars(
                select(Document)
                .where(Document.organization_id == organization_id)
                .order_by(Document.created_at.desc())
            ).all()
        )

    def get_document(self, organization_id: uuid.UUID, document_id: uuid.UUID) -> Document | None:
        return self.db.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.organization_id == organization_id,
            )
        )

    def search(
        self,
        organization_id: uuid.UUID,
        vector: list[float],
        document_id: uuid.UUID | None,
        limit: int,
    ) -> list[tuple[DocumentChunk, str]]:
        statement = self.search_statement(organization_id, vector, document_id, limit)
        return list(self.db.execute(statement).all())

    @staticmethod
    def search_statement(organization_id: uuid.UUID, vector: list[float], document_id: uuid.UUID | None, limit: int):
        distance = DocumentChunk.embedding.cosine_distance(vector)
        statement = (
            select(DocumentChunk, Document.filename)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                DocumentChunk.organization_id == organization_id,
                Document.organization_id == organization_id,
                Document.status == DocumentStatus.ready,
                DocumentChunk.embedding.is_not(None),
            )
            .order_by(distance)
            .limit(limit)
        )
        if document_id is not None:
            statement = statement.where(DocumentChunk.document_id == document_id)
        return statement

    def find_demo_sample(self, organization_id: uuid.UUID) -> Document | None:
        return self.db.scalar(
            select(Document).where(
                Document.organization_id == organization_id,
                Document.filename == SAMPLE_FILENAME,
            )
        )

    def search_text(
        self,
        organization_id: uuid.UUID,
        question: str,
        document_id: uuid.UUID | None,
        limit: int,
    ) -> list[tuple[DocumentChunk, str]]:
        statement = self.search_text_statement(organization_id, question, document_id, limit)
        return list(self.db.execute(statement).all())

    @staticmethod
    def search_text_statement(organization_id: uuid.UUID, question: str, document_id: uuid.UUID | None, limit: int):
        """Lexical match. This statement does not read or write the vector column."""
        vector = func.to_tsvector("english", DocumentChunk.content)
        query = func.plainto_tsquery("english", question)
        statement = (
            select(DocumentChunk, Document.filename)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                DocumentChunk.organization_id == organization_id,
                Document.organization_id == organization_id,
                Document.status == DocumentStatus.ready,
                vector.bool_op("@@")(query),
            )
            .order_by(func.ts_rank(vector, query).desc())
            .limit(limit)
        )
        if document_id is not None:
            statement = statement.where(DocumentChunk.document_id == document_id)
        return statement
