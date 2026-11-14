import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import DocumentStatus
from app.models.knowledge import Document, DocumentChunk


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
