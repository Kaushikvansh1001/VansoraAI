import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AssistantWrite(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    welcome_message: str = Field(min_length=1, max_length=500)
    instructions: str = Field(default="", max_length=2000)
    tone: str = "professional"
    language: str = Field(default="English", max_length=40)
    enabled: bool = True


class AssistantResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    welcome_message: str
    instructions: str
    tone: str
    language: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ConversationCreate(BaseModel):
    assistant_id: uuid.UUID
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=4000)
    priority: str = "normal"


class MessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class NoteCreate(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class DraftEdit(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ConversationUpdate(BaseModel):
    status: str | None = None
    priority: str | None = None
    assigned_to: uuid.UUID | None = None
    escalated: bool | None = None


class MessageResponse(BaseModel):
    id: uuid.UUID
    author_type: str
    author_id: uuid.UUID | None
    content: str
    internal: bool
    requires_approval: bool
    draft_status: str | None
    approved_by: uuid.UUID | None
    provider: str | None
    model: str | None
    suggest_escalation: bool | None
    created_at: datetime


class ConversationResponse(BaseModel):
    id: uuid.UUID
    assistant_id: uuid.UUID | None
    subject: str
    body: str
    status: str
    priority: str | None
    assigned_to: uuid.UUID | None
    escalated: bool
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse]
    draft_error: str | None = None


class ConversationCard(BaseModel):
    id: uuid.UUID
    subject: str
    status: str
    priority: str | None
    assigned_to: uuid.UUID | None
    escalated: bool
    updated_at: datetime


class ProviderCount(BaseModel):
    provider: str
    drafts: int


class ActivityItem(BaseModel):
    id: uuid.UUID
    subject: str
    status: str
    escalated: bool
    updated_at: datetime


class SupportSummary(BaseModel):
    total: int
    open: int
    pending: int
    resolved: int
    closed: int
    ai_drafts: int
    approved_replies: int
    escalated: int
    average_response_seconds: int | None
    providers: list[ProviderCount]
    recent: list[ActivityItem]
