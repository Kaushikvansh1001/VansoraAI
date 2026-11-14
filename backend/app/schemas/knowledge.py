import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    status: str
    size_bytes: int
    error_message: str | None
    created_at: datetime


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    document_id: uuid.UUID | None = None


class CitationResponse(BaseModel):
    document_id: uuid.UUID
    filename: str
    chunk_index: int
    excerpt: str


class AnswerResponse(BaseModel):
    answer: str
    provider: str
    model: str
    citations: list[CitationResponse]
