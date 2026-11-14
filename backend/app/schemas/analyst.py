import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DatasetResponse(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    row_count: int
    column_count: int
    error_message: str | None
    profile: dict
    created_at: datetime


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


class AnalysisResponse(BaseModel):
    id: uuid.UUID
    dataset_id: uuid.UUID
    question: str
    status: str
    error_message: str | None
    calculated: dict | None
    facts: list[str]
    interpretation: str | None
    insights: list[str]
    chart: dict | None
    created_at: datetime
