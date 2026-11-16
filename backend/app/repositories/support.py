import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.enums import AuthorType, TicketStatus
from app.models.support import SupportAssistant, SupportMessage, SupportTicket
from app.services.support.metrics import summarize

logger = logging.getLogger("vansoraai.support")


def ticket_lookup(organization_id: uuid.UUID, ticket_id: uuid.UUID):
    return select(SupportTicket).where(
        SupportTicket.organization_id == organization_id,
        SupportTicket.id == ticket_id,
    )


def assistant_lookup(organization_id: uuid.UUID, assistant_id: uuid.UUID):
    return select(SupportAssistant).where(
        SupportAssistant.organization_id == organization_id,
        SupportAssistant.id == assistant_id,
    )


def message_lookup(organization_id: uuid.UUID, ticket_id: uuid.UUID, message_id: uuid.UUID):
    return select(SupportMessage).where(
        SupportMessage.organization_id == organization_id,
        SupportMessage.ticket_id == ticket_id,
        SupportMessage.id == message_id,
    )


def conversations_statement(
    organization_id: uuid.UUID,
    *,
    q: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    escalated: bool | None = None,
):
    statement = select(SupportTicket).where(SupportTicket.organization_id == organization_id)
    if status:
        statement = statement.where(SupportTicket.status == TicketStatus(status))
    if priority:
        statement = statement.where(SupportTicket.priority == priority)
    if escalated is not None:
        statement = statement.where(SupportTicket.escalated.is_(escalated))
    if q and q.strip():
        like = _like(q)
        message_match = (
            select(SupportMessage.id)
            .where(
                SupportMessage.ticket_id == SupportTicket.id,
                SupportMessage.organization_id == organization_id,
                SupportMessage.internal.is_(False),
                SupportMessage.content.ilike(like, escape="\\"),
            )
            .exists()
        )
        statement = statement.where(
            or_(
                SupportTicket.subject.ilike(like, escape="\\"),
                SupportTicket.body.ilike(like, escape="\\"),
                message_match,
            )
        )
    return statement.order_by(SupportTicket.updated_at.desc()).limit(100)


class SupportRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def summary(self, organization_id: uuid.UUID) -> dict:
        tickets = list(
            self.db.scalars(select(SupportTicket).where(SupportTicket.organization_id == organization_id)).all()
        )
        messages = list(
            self.db.scalars(select(SupportMessage).where(SupportMessage.organization_id == organization_id)).all()
        )
        return summarize(tickets, messages)

    def list_assistants(self, organization_id: uuid.UUID) -> list[SupportAssistant]:
        return list(
            self.db.scalars(
                select(SupportAssistant)
                .where(SupportAssistant.organization_id == organization_id)
                .order_by(SupportAssistant.created_at.desc())
            ).all()
        )

    def get_assistant(self, organization_id: uuid.UUID, assistant_id: uuid.UUID) -> SupportAssistant | None:
        return self.db.scalar(assistant_lookup(organization_id, assistant_id))

    def add_assistant(self, organization_id: uuid.UUID, user_id: uuid.UUID, fields: dict) -> SupportAssistant:
        now = _now()
        assistant = SupportAssistant(
            id=uuid.uuid4(),
            organization_id=organization_id,
            created_by=user_id,
            created_at=now,
            updated_at=now,
            **fields,
        )
        self.db.add(assistant)
        self.db.flush()
        return assistant

    def touch_assistant(self, assistant: SupportAssistant) -> None:
        assistant.updated_at = _now()

    def list_tickets(self, organization_id: uuid.UUID, **filters) -> list[SupportTicket]:
        return list(self.db.scalars(conversations_statement(organization_id, **filters)).all())

    def get_ticket(self, organization_id: uuid.UUID, ticket_id: uuid.UUID) -> SupportTicket | None:
        return self.db.scalar(ticket_lookup(organization_id, ticket_id))

    def add_ticket(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        assistant_id: uuid.UUID,
        subject: str,
        body: str,
        priority: str,
    ) -> SupportTicket:
        now = _now()
        ticket = SupportTicket(
            id=uuid.uuid4(),
            organization_id=organization_id,
            created_by=user_id,
            assistant_id=assistant_id,
            subject=subject,
            body=body,
            status=TicketStatus.open,
            priority=priority,
            escalated=False,
            created_at=now,
            updated_at=now,
        )
        self.db.add(ticket)
        self.db.flush()
        return ticket

    def touch(self, ticket: SupportTicket) -> None:
        ticket.updated_at = _now()

    def messages(self, organization_id: uuid.UUID, ticket_id: uuid.UUID) -> list[SupportMessage]:
        return list(
            self.db.scalars(
                select(SupportMessage)
                .where(
                    SupportMessage.organization_id == organization_id,
                    SupportMessage.ticket_id == ticket_id,
                )
                .order_by(SupportMessage.created_at.asc())
            ).all()
        )

    def get_message(
        self, organization_id: uuid.UUID, ticket_id: uuid.UUID, message_id: uuid.UUID
    ) -> SupportMessage | None:
        return self.db.scalar(message_lookup(organization_id, ticket_id, message_id))

    def add_message(self, **fields) -> SupportMessage:
        ticket = fields.pop("ticket")
        message = SupportMessage(
            id=uuid.uuid4(),
            ticket_id=ticket.id,
            organization_id=ticket.organization_id,
            created_at=_now(),
            **fields,
        )
        self.db.add(message)
        self.db.flush()
        return message

    def member_exists(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        from app.repositories.organizations import OrganizationRepository

        return OrganizationRepository(self.db).get_member(organization_id, user_id) is not None

    def search_passages(self, organization_id: uuid.UUID, user_id: uuid.UUID, question: str) -> list[dict]:
        from app.core.config import get_settings
        from app.repositories.knowledge import KnowledgeRepository
        from app.services.knowledge.service import KnowledgeService

        if get_settings().knowledge_mode == "demo":
            KnowledgeService(self.db).ensure_sample(organization_id, user_id)
        try:
            rows = KnowledgeRepository(self.db).search_text(organization_id, question[:300], None, 4)
        except SQLAlchemyError as exc:
            logger.warning("support text search failed: %s", type(exc).__name__)
            return []
        passages = []
        for chunk, filename in rows:
            excerpt = (chunk.content or "")[:500]
            if excerpt.strip():
                passages.append({"filename": filename, "excerpt": excerpt})
        return passages


def _like(value: str) -> str:
    cleaned = value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{cleaned[:200]}%"


def _now() -> datetime:
    return datetime.now(timezone.utc)
