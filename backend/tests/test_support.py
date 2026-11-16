import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql

from app.core.errors import AppError
from app.models.enums import AuthorType, TicketStatus
from app.models.support import SupportAssistant, SupportMessage, SupportTicket
from app.repositories.support import assistant_lookup, conversations_statement, message_lookup, ticket_lookup
from app.services.ai.exceptions import ProviderChainFailed
from app.services.ai.models import GenerationOutcome, ProviderResponse, TokenUsage
from app.services.support.drafting import INSUFFICIENT_REPLY, build_prompt
from app.services.support.metrics import summarize
from app.services.support.service import SupportService


def test_assistant_configuration_rejects_an_unknown_tone():
    support, repo = _support()
    created = support.create_assistant(_id(), _id(), _assistant())
    assert created.name == "Northwind desk"
    assert created.enabled is True
    with pytest.raises(AppError) as caught:
        support.create_assistant(_id(), _id(), {**_assistant(), "tone": "casual"})
    assert caught.value.code == "invalid_tone"
    assert repo.assistants[0].tone == "friendly"


def test_conversation_without_passages_does_not_call_the_model():
    support, _repo = _support(passages=_empty, manager=_ExplodingManager())
    org, user = _id(), _id()
    assistant = support.create_assistant(org, user, _assistant())
    ticket, messages, error = support.start_conversation(org, user, _start(assistant.id))
    assert error is None
    assert ticket.status == TicketStatus.pending
    assert [message.author_type for message in messages] == [AuthorType.system, AuthorType.customer, AuthorType.ai]
    draft = messages[-1]
    assert draft.content == INSUFFICIENT_REPLY
    assert draft.draft_status == "draft"
    assert draft.requires_approval is True
    assert draft.suggest_escalation is True
    assert draft.provider is None
    assert messages[1].content == "When will my order ship?"


def test_draft_uses_passages_and_refuses_to_invent_facts():
    manager = _Manager()
    support, _repo = _support(manager=manager)
    org, user = _id(), _id()
    assistant = support.create_assistant(org, user, _assistant())
    _ticket, messages, error = support.start_conversation(org, user, _start(assistant.id))
    assert error is None
    assert messages[-1].content == "Ships in 5 business days."
    assert messages[-1].provider == "gemini"
    assert messages[-1].draft_status == "draft"
    prompt = manager.calls[0][0].prompt
    assert "Do not invent policies" in prompt
    assert "text search" in prompt
    assert manager.calls[0][1]["feature"] == "support"


def test_provider_fallback_result_is_stored_as_the_draft_provider():
    manager = _Manager(provider="groq")
    support, _repo = _support(manager=manager)
    org, user = _id(), _id()
    assistant = support.create_assistant(org, user, _assistant())
    _ticket, messages, error = support.start_conversation(org, user, _start(assistant.id))
    assert error is None
    assert messages[-1].provider == "groq"
    assert manager.calls[0][1]["feature"] == "support"


def test_invalid_model_json_does_not_store_a_reply():
    support, repo = _support(manager=_Manager(text="Here is a policy I made up."))
    org, user = _id(), _id()
    assistant = support.create_assistant(org, user, _assistant())
    ticket, messages, error = support.start_conversation(org, user, _start(assistant.id))
    assert error
    assert "no draft was stored" in error
    assert ticket.status == TicketStatus.open
    assert [message.author_type for message in messages] == [AuthorType.system, AuthorType.customer]
    assert "made up" not in " ".join(message.content for message in repo.message_rows)


def test_provider_failure_does_not_invent_a_reply():
    support, _repo = _support(manager=_Manager(fail=True))
    org, user = _id(), _id()
    assistant = support.create_assistant(org, user, _assistant())
    ticket, messages, error = support.start_conversation(org, user, _start(assistant.id))
    assert "no draft was stored" in error
    assert ticket.status == TicketStatus.open
    assert all(message.author_type != AuthorType.ai for message in messages)


def test_draft_review_edit_approve_reject_and_another_draft():
    support, _repo = _support()
    org, user = _id(), _id()
    assistant = support.create_assistant(org, user, _assistant())
    ticket, messages, _error = support.start_conversation(org, user, _start(assistant.id))
    draft = messages[-1]
    ticket, messages, error = support.edit_draft(org, user, ticket.id, draft.id, "Ships in 5 business days after review.")
    assert error is None
    assert messages[-1].content == "Ships in 5 business days after review."
    assert messages[-1].draft_status == "draft"
    ticket, messages, _error = support.approve_draft(org, user, ticket.id, draft.id)
    assert messages[-1].draft_status == "approved"
    assert messages[-1].approved_by == user
    with pytest.raises(AppError) as caught:
        support.edit_draft(org, user, ticket.id, draft.id, "Changed after approval.")
    assert caught.value.code == "draft_closed"
    ticket, messages, error = support.request_draft(org, user, ticket.id)
    assert error is None
    drafts = [message for message in messages if message.author_type == AuthorType.ai]
    assert [message.draft_status for message in drafts] == ["approved", "draft"]
    ticket, messages, _error = support.reject_draft(org, user, ticket.id, drafts[-1].id)
    assert messages[-1].draft_status == "rejected"
    counts = support.summary(org)
    assert counts["ai_drafts"] == 2
    assert counts["approved_replies"] == 1


def test_escalation_assignment_and_resolution():
    support, repo = _support()
    org, user, teammate, outsider = _id(), _id(), _id(), _id()
    repo.members.add((org, teammate))
    assistant = support.create_assistant(org, user, _assistant())
    ticket, _messages, _error = support.start_conversation(org, user, _start(assistant.id))
    ticket, _messages, _error = support.update_conversation(org, user, ticket.id, {"escalated": True})
    assert ticket.escalated is True
    assert ticket.status == TicketStatus.pending
    ticket, _messages, _error = support.update_conversation(org, user, ticket.id, {"assigned_to": teammate})
    assert ticket.assigned_to == teammate
    with pytest.raises(AppError) as caught:
        support.update_conversation(org, user, ticket.id, {"assigned_to": outsider})
    assert caught.value.code == "invalid_assignee"
    ticket, _messages, _error = support.update_conversation(org, user, ticket.id, {"status": "resolved"})
    assert ticket.status == TicketStatus.resolved
    assert ticket.escalated is True
    assert support.summary(org)["escalated"] == 1
    assert support.summary(org)["resolved"] == 1


def test_internal_notes_stay_out_of_the_prompt_and_history_is_kept():
    manager = _Manager()
    support, _repo = _support(manager=manager)
    org, user = _id(), _id()
    assistant = support.create_assistant(org, user, _assistant())
    ticket, messages, _error = support.start_conversation(org, user, _start(assistant.id))
    support.add_note(org, user, ticket.id, "The warehouse lead should check this.")
    ticket, messages, error = support.add_customer_message(org, user, ticket.id, "Can a person call me?")
    assert error is None
    assert [message.content for message in messages if message.author_type == AuthorType.customer] == [
        "When will my order ship?",
        "Can a person call me?",
    ]
    assert any(message.internal for message in messages)
    prompt = manager.calls[-1][0].prompt
    assert "warehouse lead" not in prompt
    assert "Can a person call me?" in prompt


def test_other_organization_cannot_read_or_change_a_conversation():
    manager = _ExplodingManager()
    support, _repo = _support(passages=_empty, manager=manager)
    org, other, user = _id(), _id(), _id()
    assistant = support.create_assistant(org, user, _assistant())
    ticket, messages, _error = support.start_conversation(org, user, _start(assistant.id))
    with pytest.raises(AppError) as caught:
        support.get_conversation(other, ticket.id)
    assert caught.value.code == "not_found"
    with pytest.raises(AppError):
        support.approve_draft(other, user, ticket.id, messages[-1].id)
    with pytest.raises(AppError):
        support.update_conversation(other, user, ticket.id, {"status": "resolved"})
    assert support.get_conversation(org, ticket.id)[0].status == TicketStatus.pending
    assert support.list_conversations(other) == []


def test_average_response_uses_the_first_approved_reply():
    support, repo = _support()
    org, user = _id(), _id()
    assistant = support.create_assistant(org, user, _assistant())
    ticket, messages, _error = support.start_conversation(org, user, _start(assistant.id))
    customer = next(message for message in messages if message.author_type == AuthorType.customer)
    draft = messages[-1]
    started = datetime(2026, 11, 16, 9, 0, tzinfo=timezone.utc)
    customer.created_at = started
    support.approve_draft(org, user, ticket.id, draft.id)
    draft.created_at = started + timedelta(seconds=90)
    assert support.summary(org)["average_response_seconds"] == 90
    assert summarize(repo.tickets, repo.message_rows)["ai_drafts"] == 1


def test_message_length_and_disabled_assistant_are_rejected():
    support, repo = _support()
    org, user = _id(), _id()
    assistant = support.create_assistant(org, user, {**_assistant(), "enabled": False})
    with pytest.raises(AppError) as caught:
        support.start_conversation(org, user, _start(assistant.id))
    assert caught.value.code == "assistant_disabled"
    support.update_assistant(org, user, assistant.id, _assistant())
    with pytest.raises(AppError) as caught:
        support.start_conversation(org, user, {**_start(assistant.id), "message": "x" * 4001})
    assert caught.value.code == "invalid_message"
    assert repo.tickets == []


def test_instructions_cannot_carry_a_provider_key_into_the_prompt():
    assistant = SupportAssistant(
        name="Desk",
        welcome_message="Hello",
        instructions="The key is gsk_abcdefghijklmnopqrstuvwxyz and it must not be repeated.",
        tone="formal",
        language="English",
    )
    prompt = build_prompt(assistant, ["Customer: When will it ship?"], [{"filename": "note.txt", "excerpt": "Five days."}], "When will it ship?")
    assert "gsk_" not in prompt
    assert "[redacted]" in prompt
    assert "Do not invent policies" in prompt


def test_queries_are_limited_to_the_organization():
    org = _id()
    statements = [
        ticket_lookup(org, _id()),
        assistant_lookup(org, _id()),
        message_lookup(org, _id(), _id()),
        conversations_statement(org, q="shipping", status="open", priority="high", escalated=True),
    ]
    for statement in statements:
        sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})).lower()
        assert "organization_id" in sql
        assert str(org) in sql


def test_support_does_not_load_the_embedding_model():
    import sys

    sys.modules.pop("fastembed", None)
    import app.repositories.support  # noqa: F401
    import app.services.support.service  # noqa: F401

    assert "fastembed" not in sys.modules
    root = Path(__file__).resolve().parents[1] / "app"
    for relative in ("services/support/service.py", "services/support/drafting.py", "repositories/support.py"):
        text = (root / relative).read_text(encoding="utf-8").lower()
        assert "fastembed" not in text
        assert "embeddings" not in text
    repository = (root / "repositories" / "support.py").read_text(encoding="utf-8")
    assert "search_text" in repository
    service = (root / "services" / "support" / "service.py").read_text(encoding="utf-8").lower()
    assert "outbox" not in service
    assert "send_email" not in service


def test_support_routes_are_registered():
    from app.main import app

    paths = app.openapi()["paths"]
    assert "/api/v1/support/summary" in paths
    assert "/api/v1/support/assistants" in paths
    assert "/api/v1/support/conversations" in paths
    assert "/api/v1/support/conversations/{ticket_id}/drafts/{message_id}/approve" in paths


class _Memory:
    def __init__(self) -> None:
        self.assistants = []
        self.tickets = []
        self.message_rows = []
        self.members = set()

    def summary(self, organization_id):
        return summarize(
            [ticket for ticket in self.tickets if ticket.organization_id == organization_id],
            [message for message in self.message_rows if message.organization_id == organization_id],
        )

    def list_assistants(self, organization_id):
        return [assistant for assistant in self.assistants if assistant.organization_id == organization_id]

    def get_assistant(self, organization_id, assistant_id):
        return next(
            (
                assistant
                for assistant in self.assistants
                if assistant.organization_id == organization_id and assistant.id == assistant_id
            ),
            None,
        )

    def add_assistant(self, organization_id, user_id, fields):
        now = datetime.now(timezone.utc)
        assistant = SupportAssistant(
            id=_id(),
            organization_id=organization_id,
            created_by=user_id,
            created_at=now,
            updated_at=now,
            **fields,
        )
        self.assistants.append(assistant)
        return assistant

    def touch_assistant(self, assistant):
        assistant.updated_at = datetime.now(timezone.utc)

    def list_tickets(self, organization_id, q=None, status=None, priority=None, escalated=None):
        rows = [ticket for ticket in self.tickets if ticket.organization_id == organization_id]
        if status:
            rows = [ticket for ticket in rows if _status(ticket) == status]
        if priority:
            rows = [ticket for ticket in rows if ticket.priority == priority]
        if escalated is not None:
            rows = [ticket for ticket in rows if ticket.escalated is escalated]
        if q:
            needle = q.lower()
            rows = [
                ticket
                for ticket in rows
                if needle in ticket.subject.lower() or needle in (ticket.body or "").lower()
            ]
        return rows

    def get_ticket(self, organization_id, ticket_id):
        return next(
            (ticket for ticket in self.tickets if ticket.organization_id == organization_id and ticket.id == ticket_id),
            None,
        )

    def add_ticket(self, **fields):
        now = datetime.now(timezone.utc)
        user_id = fields.pop("user_id")
        ticket = SupportTicket(
            id=_id(),
            created_by=user_id,
            created_at=now,
            updated_at=now,
            status=TicketStatus.open,
            escalated=False,
            **fields,
        )
        self.tickets.append(ticket)
        return ticket

    def touch(self, ticket):
        ticket.updated_at = datetime.now(timezone.utc)

    def messages(self, organization_id, ticket_id):
        rows = [
            message
            for message in self.message_rows
            if message.organization_id == organization_id and message.ticket_id == ticket_id
        ]
        return sorted(rows, key=lambda message: message.created_at)

    def get_message(self, organization_id, ticket_id, message_id):
        return next(
            (
                message
                for message in self.message_rows
                if message.organization_id == organization_id
                and message.ticket_id == ticket_id
                and message.id == message_id
            ),
            None,
        )

    def add_message(self, **fields):
        ticket = fields.pop("ticket")
        message = SupportMessage(
            id=_id(),
            ticket_id=ticket.id,
            organization_id=ticket.organization_id,
            created_at=datetime.now(timezone.utc),
            **fields,
        )
        self.message_rows.append(message)
        return message

    def member_exists(self, organization_id, user_id):
        return (organization_id, user_id) in self.members


class _Manager:
    def __init__(self, text='{"reply":"Ships in 5 business days.","insufficient":false,"escalate":false}', provider="gemini", fail=False):
        self.text = text
        self.provider = provider
        self.fail = fail
        self.calls = []

    def generate(self, request, **kwargs):
        self.calls.append((request, kwargs))
        if self.fail:
            raise ProviderChainFailed([])
        return GenerationOutcome(
            response=ProviderResponse(
                provider=self.provider,
                model="test-model",
                text=self.text,
                usage=TokenUsage(1, 1, "provider"),
                latency_ms=1,
            ),
            fallback_from="gemini" if self.provider == "groq" else None,
        )


class _ExplodingManager:
    def generate(self, request, **kwargs):
        raise AssertionError("The model should not be called")


def _support(passages=None, manager=None):
    repo = _Memory()
    found = passages if passages is not None else _passages
    return SupportService(None, manager=manager or _Manager(), repository=repo, passages=found), repo


def _empty(_organization_id, _question):
    return []


def _passages(_organization_id, _question):
    return [{"filename": "Northwind Studio sample.txt", "excerpt": "Orders ship in 5 business days."}]


def _assistant():
    return {
        "name": "Northwind desk",
        "description": "Answers from the studio notes.",
        "welcome_message": "Hello, how can we help?",
        "instructions": "Use the shipping note only.",
        "tone": "friendly",
        "language": "English",
        "enabled": True,
    }


def _start(assistant_id):
    return {
        "assistant_id": assistant_id,
        "subject": "Shipping time",
        "message": "When will my order ship?",
        "priority": "normal",
    }


def _status(ticket) -> str:
    value = ticket.status
    return value.value if hasattr(value, "value") else str(value)


def _id() -> uuid.UUID:
    return uuid.uuid4()
