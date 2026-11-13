import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentStatusCounts(BaseModel):
    pending: int
    processing: int
    ready: int
    failed: int


class ActivityItem(BaseModel):
    action: str
    resource_type: str
    created_at: datetime


class ConversationItem(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime


class DashboardResponse(BaseModel):
    documents: int
    conversations: int
    queries: int
    workflows: int
    successful_executions: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: str
    document_status: DocumentStatusCounts
    recent_activity: list[ActivityItem]
    recent_conversations: list[ConversationItem]
