import uuid

from app.core.errors import AppError
from app.models.enums import AuthorType, TicketStatus
from app.services.ai.exceptions import ProviderChainFailed
from app.services.ai.models import GenerationRequest
from app.services.support.drafting import (
    DRAFT_SCHEMA,
    build_prompt,
    clean_assistant,
    clean_message,
    clean_priority,
    clean_status,
    history_lines,
    insufficient_draft,
    parse_draft,
)


class SupportService:
    """Support conversations for one organization.

    AI replies are stored as drafts. Approving a draft keeps it in the
    conversation. This service does not email a customer.
    """

    def __init__(self, db, manager=None, repository=None, passages=None) -> None:
        self.db = db
        self.manager = manager
        self.repo = repository if repository is not None else _repository(db)
        self.passages = passages

    def summary(self, organization_id: uuid.UUID) -> dict:
        return self.repo.summary(organization_id)

    def list_assistants(self, organization_id: uuid.UUID):
        return self.repo.list_assistants(organization_id)

    def create_assistant(self, organization_id: uuid.UUID, user_id: uuid.UUID, fields: dict):
        assistant = self.repo.add_assistant(organization_id, user_id, clean_assistant(fields))
        self._audit("support.assistant_created", organization_id, user_id, assistant.id)
        return assistant

    def update_assistant(self, organization_id: uuid.UUID, user_id: uuid.UUID, assistant_id: uuid.UUID, fields: dict):
        assistant = self._assistant(organization_id, assistant_id)
        for key, value in clean_assistant(fields).items():
            setattr(assistant, key, value)
        self.repo.touch_assistant(assistant)
        self._audit("support.assistant_updated", organization_id, user_id, assistant.id)
        return assistant

    def list_conversations(self, organization_id: uuid.UUID, **filters):
        status = filters.get("status")
        priority = filters.get("priority")
        if status:
            filters["status"] = clean_status(status)
        if priority:
            filters["priority"] = clean_priority(priority)
        query = filters.get("q")
        if query is not None:
            filters["q"] = str(query)[:200]
        return self.repo.list_tickets(organization_id, **filters)

    def get_conversation(self, organization_id: uuid.UUID, ticket_id: uuid.UUID):
        ticket = self._ticket(organization_id, ticket_id)
        return ticket, self.repo.messages(organization_id, ticket.id), None

    def start_conversation(self, organization_id: uuid.UUID, user_id: uuid.UUID, fields: dict):
        assistant = self._assistant(organization_id, fields["assistant_id"])
        if not assistant.enabled:
            raise AppError("assistant_disabled", "Turn the assistant on before starting a conversation.", 409)
        subject = clean_message(fields.get("subject"), "subject", 200)
        body = clean_message(fields.get("message"), "message", 4000)
        priority = clean_priority(fields.get("priority") or "normal")
        ticket = self.repo.add_ticket(
            organization_id=organization_id,
            user_id=user_id,
            assistant_id=assistant.id,
            subject=subject,
            body=body,
            priority=priority,
        )
        self.repo.add_message(
            ticket=ticket,
            author_type=AuthorType.system,
            author_id=None,
            content=assistant.welcome_message,
            requires_approval=False,
            draft_status=None,
            internal=False,
            provider=None,
            model=None,
            suggest_escalation=None,
        )
        self.repo.add_message(
            ticket=ticket,
            author_type=AuthorType.customer,
            author_id=user_id,
            content=body,
            requires_approval=False,
            draft_status=None,
            internal=False,
            provider=None,
            model=None,
            suggest_escalation=None,
        )
        error = self._make_draft(ticket, assistant, user_id, body)
        self._audit("support.conversation_started", organization_id, user_id, ticket.id)
        return ticket, self.repo.messages(organization_id, ticket.id), error

    def add_customer_message(self, organization_id: uuid.UUID, user_id: uuid.UUID, ticket_id: uuid.UUID, text: str):
        ticket = self._ticket(organization_id, ticket_id)
        body = clean_message(text, "message", 4000)
        if ticket.status in {TicketStatus.resolved, TicketStatus.closed}:
            ticket.status = TicketStatus.open
        self.repo.add_message(
            ticket=ticket,
            author_type=AuthorType.customer,
            author_id=user_id,
            content=body,
            requires_approval=False,
            draft_status=None,
            internal=False,
            provider=None,
            model=None,
            suggest_escalation=None,
        )
        assistant = self._assistant_or_none(organization_id, ticket.assistant_id)
        if assistant is None or not assistant.enabled:
            self.repo.touch(ticket)
            return ticket, self.repo.messages(organization_id, ticket.id), "The assistant is turned off, so no draft was created."
        error = self._replace_draft(ticket, assistant, user_id, body)
        return ticket, self.repo.messages(organization_id, ticket.id), error

    def add_note(self, organization_id: uuid.UUID, user_id: uuid.UUID, ticket_id: uuid.UUID, text: str):
        ticket = self._ticket(organization_id, ticket_id)
        self.repo.add_message(
            ticket=ticket,
            author_type=AuthorType.agent,
            author_id=user_id,
            content=clean_message(text, "note", 4000),
            requires_approval=False,
            draft_status=None,
            internal=True,
            provider=None,
            model=None,
            suggest_escalation=None,
        )
        self.repo.touch(ticket)
        return ticket, self.repo.messages(organization_id, ticket.id), None

    def request_draft(self, organization_id: uuid.UUID, user_id: uuid.UUID, ticket_id: uuid.UUID):
        ticket = self._ticket(organization_id, ticket_id)
        assistant = self._assistant_or_none(organization_id, ticket.assistant_id)
        if assistant is None or not assistant.enabled:
            raise AppError("assistant_disabled", "Turn the assistant on before requesting a draft.", 409)
        messages = self.repo.messages(organization_id, ticket.id)
        question = _latest_customer(messages)
        if not question:
            raise AppError("message_required", "Add a customer message before requesting a draft.", 400)
        error = self._replace_draft(ticket, assistant, user_id, question)
        return ticket, self.repo.messages(organization_id, ticket.id), error

    def edit_draft(
        self, organization_id: uuid.UUID, user_id: uuid.UUID, ticket_id: uuid.UUID, message_id: uuid.UUID, text: str
    ):
        ticket, message = self._open_draft(organization_id, ticket_id, message_id)
        message.content = clean_message(text, "draft", 2000)
        self.repo.touch(ticket)
        self._audit("support.draft_edited", organization_id, user_id, message.id)
        return ticket, self.repo.messages(organization_id, ticket.id), None

    def approve_draft(self, organization_id: uuid.UUID, user_id: uuid.UUID, ticket_id: uuid.UUID, message_id: uuid.UUID):
        ticket, message = self._open_draft(organization_id, ticket_id, message_id)
        message.draft_status = "approved"
        message.approved_by = user_id
        self.repo.touch(ticket)
        self._audit("support.draft_approved", organization_id, user_id, message.id)
        return ticket, self.repo.messages(organization_id, ticket.id), None

    def reject_draft(self, organization_id: uuid.UUID, user_id: uuid.UUID, ticket_id: uuid.UUID, message_id: uuid.UUID):
        ticket, message = self._open_draft(organization_id, ticket_id, message_id)
        message.draft_status = "rejected"
        self.repo.touch(ticket)
        self._audit("support.draft_rejected", organization_id, user_id, message.id)
        return ticket, self.repo.messages(organization_id, ticket.id), None

    def update_conversation(self, organization_id: uuid.UUID, user_id: uuid.UUID, ticket_id: uuid.UUID, changes: dict):
        ticket = self._ticket(organization_id, ticket_id)
        if changes.get("status"):
            ticket.status = TicketStatus(clean_status(changes["status"]))
        if changes.get("priority"):
            ticket.priority = clean_priority(changes["priority"])
        if "assigned_to" in changes:
            assignee = changes["assigned_to"]
            if assignee is None:
                ticket.assigned_to = None
            elif self.repo.member_exists(organization_id, assignee):
                ticket.assigned_to = assignee
            else:
                raise AppError("invalid_assignee", "Choose a member of this organization.", 400)
        if changes.get("escalated") is True:
            ticket.escalated = True
            if not changes.get("status") and ticket.status != TicketStatus.resolved:
                ticket.status = TicketStatus.pending
        elif changes.get("escalated") is False:
            ticket.escalated = False
        self.repo.touch(ticket)
        self._audit("support.conversation_updated", organization_id, user_id, ticket.id)
        return ticket, self.repo.messages(organization_id, ticket.id), None

    def _make_draft(self, ticket, assistant, user_id: uuid.UUID, question: str) -> str | None:
        found = self._lookup_passages(ticket.organization_id, user_id, question)
        if not found:
            self._store_draft(ticket, insufficient_draft(), None, None)
            return None
        try:
            outcome = self._manager().generate(
                GenerationRequest(prompt=build_prompt(assistant, self._history(ticket), found, question), json_schema=DRAFT_SCHEMA),
                organization_id=ticket.organization_id,
                user_id=user_id,
                feature="support",
            )
        except ProviderChainFailed:
            self.repo.touch(ticket)
            return "Every configured provider failed, so no draft was stored."
        try:
            draft = parse_draft(outcome.response.text)
        except AppError:
            self.repo.touch(ticket)
            return "The model response did not match the expected fields, so no draft was stored."
        self._store_draft(ticket, draft, outcome.response.provider, outcome.response.model)
        return None

    def _store_draft(self, ticket, draft: dict, provider: str | None, model: str | None) -> None:
        self.repo.add_message(
            ticket=ticket,
            author_type=AuthorType.ai,
            author_id=None,
            content=draft["reply"],
            requires_approval=True,
            draft_status="draft",
            internal=False,
            provider=provider,
            model=model,
            suggest_escalation=bool(draft["escalate"]),
        )
        ticket.status = TicketStatus.pending
        self.repo.touch(ticket)

    def _history(self, ticket) -> list[str]:
        return history_lines(self.repo.messages(ticket.organization_id, ticket.id))

    def _lookup_passages(self, organization_id, user_id, question: str):
        if self.passages is not None:
            return self.passages(organization_id, question)
        return self.repo.search_passages(organization_id, user_id, question)

    def _manager(self):
        if self.manager is not None:
            return self.manager
        if self.db is None:
            raise AppError("ai_unavailable", "No AI provider is configured.", 503)
        from app.core.config import get_settings
        from app.services.ai.provider_manager import ProviderManager
        from app.services.ai.usage_tracker import UsageTracker

        self.manager = ProviderManager(get_settings(), sink=UsageTracker(self.db))
        return self.manager

    def _replace_draft(self, ticket, assistant, user_id: uuid.UUID, question: str) -> str | None:
        previous = [
            message
            for message in self.repo.messages(ticket.organization_id, ticket.id)
            if _author(message) == "ai" and message.draft_status == "draft"
        ]
        error = self._make_draft(ticket, assistant, user_id, question)
        if error:
            return error
        for message in previous:
            message.draft_status = "rejected"
        return None

    def _open_draft(self, organization_id, ticket_id, message_id):
        ticket = self._ticket(organization_id, ticket_id)
        message = self.repo.get_message(organization_id, ticket.id, message_id)
        if message is None or _author(message) != "ai":
            raise AppError("not_found", "That draft was not found.", 404)
        if message.draft_status != "draft":
            raise AppError("draft_closed", "Only an open draft can be changed.", 409)
        return ticket, message

    def _assistant(self, organization_id, assistant_id):
        assistant = self.repo.get_assistant(organization_id, assistant_id)
        if assistant is None:
            raise AppError("not_found", "That assistant was not found.", 404)
        return assistant

    def _assistant_or_none(self, organization_id, assistant_id):
        if assistant_id is None:
            return None
        return self.repo.get_assistant(organization_id, assistant_id)

    def _ticket(self, organization_id, ticket_id):
        ticket = self.repo.get_ticket(organization_id, ticket_id)
        if ticket is None:
            raise AppError("not_found", "That conversation was not found.", 404)
        return ticket

    def _audit(self, action: str, organization_id, user_id, resource_id) -> None:
        if self.db is None:
            return
        from app.services.audit import record_audit

        record_audit(
            self.db,
            action=action,
            resource_type="support",
            actor_id=user_id,
            organization_id=organization_id,
            resource_id=resource_id,
        )


def _repository(db):
    from app.repositories.support import SupportRepository

    return SupportRepository(db)


def _latest_customer(messages) -> str | None:
    for message in reversed(messages):
        if not message.internal and _author(message) == "customer" and message.content.strip():
            return message.content
    return None


def _author(message) -> str:
    value = message.author_type
    return value.value if hasattr(value, "value") else str(value)
