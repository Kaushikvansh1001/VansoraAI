import uuid

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.errors import AppError
from app.core.security import generation_rate_limiter, support_rate_limiter
from app.db.session import get_db
from app.models.identity import Profile
from app.schemas.support import (
    ActivityItem,
    AssistantResponse,
    AssistantWrite,
    ConversationCard,
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
    DraftEdit,
    MessageCreate,
    MessageResponse,
    NoteCreate,
    ProviderCount,
    SupportSummary,
)
from app.services.organizations import OrganizationService
from app.services.support.service import SupportService

router = APIRouter(prefix="/support", tags=["support"])


def _organization_id(x_organization_id: str | None = Header(default=None)) -> uuid.UUID:
    if not x_organization_id:
        raise AppError("organization_required", "Choose an organization before continuing.", 400)
    try:
        return uuid.UUID(x_organization_id)
    except ValueError as exc:
        raise AppError("invalid_organization", "The organization id is not valid.", 400) from exc


def _member(
    organization_id: uuid.UUID = Depends(_organization_id),
    user: Profile = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> tuple[uuid.UUID, Profile, Session]:
    OrganizationService(db).require_context(user, organization_id)
    return organization_id, user, db


def _value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _message(message) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        author_type=_value(message.author_type),
        author_id=message.author_id,
        content=message.content,
        internal=bool(message.internal),
        requires_approval=bool(message.requires_approval),
        draft_status=message.draft_status,
        approved_by=message.approved_by,
        provider=message.provider,
        model=message.model,
        suggest_escalation=message.suggest_escalation,
        created_at=message.created_at,
    )


def _conversation(ticket, messages, draft_error) -> ConversationResponse:
    return ConversationResponse(
        id=ticket.id,
        assistant_id=ticket.assistant_id,
        subject=ticket.subject,
        body=ticket.body,
        status=_value(ticket.status),
        priority=ticket.priority,
        assigned_to=ticket.assigned_to,
        escalated=bool(ticket.escalated),
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        messages=[_message(message) for message in messages],
        draft_error=draft_error,
    )


def _card(ticket) -> ConversationCard:
    return ConversationCard(
        id=ticket.id,
        subject=ticket.subject,
        status=_value(ticket.status),
        priority=ticket.priority,
        assigned_to=ticket.assigned_to,
        escalated=bool(ticket.escalated),
        updated_at=ticket.updated_at,
    )


def _assistant(assistant) -> AssistantResponse:
    return AssistantResponse(
        id=assistant.id,
        name=assistant.name,
        description=assistant.description,
        welcome_message=assistant.welcome_message,
        instructions=assistant.instructions,
        tone=assistant.tone,
        language=assistant.language,
        enabled=assistant.enabled,
        created_at=assistant.created_at,
        updated_at=assistant.updated_at,
    )


@router.get("/summary", response_model=SupportSummary)
def summary(context: tuple = Depends(_member)) -> SupportSummary:
    organization_id, _user, db = context
    payload = SupportService(db).summary(organization_id)
    return SupportSummary(
        total=payload["total"],
        open=payload["open"],
        pending=payload["pending"],
        resolved=payload["resolved"],
        closed=payload["closed"],
        ai_drafts=payload["ai_drafts"],
        approved_replies=payload["approved_replies"],
        escalated=payload["escalated"],
        average_response_seconds=payload["average_response_seconds"],
        providers=[ProviderCount(**item) for item in payload["providers"]],
        recent=[
            ActivityItem(
                id=ticket.id,
                subject=ticket.subject,
                status=_value(ticket.status),
                escalated=bool(ticket.escalated),
                updated_at=ticket.updated_at,
            )
            for ticket in payload["recent"]
        ],
    )


@router.get("/assistants", response_model=list[AssistantResponse])
def list_assistants(context: tuple = Depends(_member)) -> list[AssistantResponse]:
    organization_id, _user, db = context
    return [_assistant(item) for item in SupportService(db).list_assistants(organization_id)]


@router.post("/assistants", response_model=AssistantResponse, status_code=201)
def create_assistant(body: AssistantWrite, context: tuple = Depends(_member)) -> AssistantResponse:
    organization_id, user, db = context
    assistant = SupportService(db).create_assistant(organization_id, user.id, body.model_dump())
    return _assistant(assistant)


@router.patch("/assistants/{assistant_id}", response_model=AssistantResponse)
def update_assistant(assistant_id: uuid.UUID, body: AssistantWrite, context: tuple = Depends(_member)) -> AssistantResponse:
    organization_id, user, db = context
    assistant = SupportService(db).update_assistant(organization_id, user.id, assistant_id, body.model_dump())
    return _assistant(assistant)


@router.get("/conversations", response_model=list[ConversationCard])
def list_conversations(
    q: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    escalated: bool | None = None,
    context: tuple = Depends(_member),
) -> list[ConversationCard]:
    organization_id, _user, db = context
    tickets = SupportService(db).list_conversations(
        organization_id, q=q, status=status, priority=priority, escalated=escalated
    )
    return [_card(ticket) for ticket in tickets]


@router.post("/conversations", response_model=ConversationResponse, status_code=201)
def start_conversation(body: ConversationCreate, context: tuple = Depends(_member)) -> ConversationResponse:
    organization_id, user, db = context
    support_rate_limiter.check(str(user.id))
    generation_rate_limiter.check(str(user.id))
    ticket, messages, draft_error = SupportService(db).start_conversation(organization_id, user.id, body.model_dump())
    return _conversation(ticket, messages, draft_error)


@router.get("/conversations/{ticket_id}", response_model=ConversationResponse)
def get_conversation(ticket_id: uuid.UUID, context: tuple = Depends(_member)) -> ConversationResponse:
    organization_id, _user, db = context
    ticket, messages, draft_error = SupportService(db).get_conversation(organization_id, ticket_id)
    return _conversation(ticket, messages, draft_error)


@router.patch("/conversations/{ticket_id}", response_model=ConversationResponse)
def update_conversation(
    ticket_id: uuid.UUID, body: ConversationUpdate, context: tuple = Depends(_member)
) -> ConversationResponse:
    organization_id, user, db = context
    changes = body.model_dump(exclude_unset=True)
    ticket, messages, draft_error = SupportService(db).update_conversation(organization_id, user.id, ticket_id, changes)
    return _conversation(ticket, messages, draft_error)


@router.post("/conversations/{ticket_id}/messages", response_model=ConversationResponse)
def add_message(ticket_id: uuid.UUID, body: MessageCreate, context: tuple = Depends(_member)) -> ConversationResponse:
    organization_id, user, db = context
    support_rate_limiter.check(str(user.id))
    generation_rate_limiter.check(str(user.id))
    ticket, messages, draft_error = SupportService(db).add_customer_message(
        organization_id, user.id, ticket_id, body.message
    )
    return _conversation(ticket, messages, draft_error)


@router.post("/conversations/{ticket_id}/notes", response_model=ConversationResponse)
def add_note(ticket_id: uuid.UUID, body: NoteCreate, context: tuple = Depends(_member)) -> ConversationResponse:
    organization_id, user, db = context
    support_rate_limiter.check(str(user.id))
    ticket, messages, draft_error = SupportService(db).add_note(organization_id, user.id, ticket_id, body.message)
    return _conversation(ticket, messages, draft_error)


@router.post("/conversations/{ticket_id}/drafts", response_model=ConversationResponse)
def request_draft(ticket_id: uuid.UUID, context: tuple = Depends(_member)) -> ConversationResponse:
    organization_id, user, db = context
    support_rate_limiter.check(str(user.id))
    generation_rate_limiter.check(str(user.id))
    ticket, messages, draft_error = SupportService(db).request_draft(organization_id, user.id, ticket_id)
    return _conversation(ticket, messages, draft_error)


@router.patch("/conversations/{ticket_id}/drafts/{message_id}", response_model=ConversationResponse)
def edit_draft(
    ticket_id: uuid.UUID, message_id: uuid.UUID, body: DraftEdit, context: tuple = Depends(_member)
) -> ConversationResponse:
    organization_id, user, db = context
    ticket, messages, draft_error = SupportService(db).edit_draft(
        organization_id, user.id, ticket_id, message_id, body.message
    )
    return _conversation(ticket, messages, draft_error)


@router.post("/conversations/{ticket_id}/drafts/{message_id}/approve", response_model=ConversationResponse)
def approve_draft(
    ticket_id: uuid.UUID, message_id: uuid.UUID, context: tuple = Depends(_member)
) -> ConversationResponse:
    organization_id, user, db = context
    ticket, messages, draft_error = SupportService(db).approve_draft(organization_id, user.id, ticket_id, message_id)
    return _conversation(ticket, messages, draft_error)


@router.post("/conversations/{ticket_id}/drafts/{message_id}/reject", response_model=ConversationResponse)
def reject_draft(
    ticket_id: uuid.UUID, message_id: uuid.UUID, context: tuple = Depends(_member)
) -> ConversationResponse:
    organization_id, user, db = context
    ticket, messages, draft_error = SupportService(db).reject_draft(organization_id, user.id, ticket_id, message_id)
    return _conversation(ticket, messages, draft_error)
