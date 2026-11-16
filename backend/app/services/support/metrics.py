"""Counts for the support dashboard.

AI draft totals count every generated reply. Approved totals count only the
replies a person kept in the conversation. Nothing in these numbers was emailed.
"""

from collections import Counter


def summarize(tickets, messages) -> dict:
    statuses = Counter(_value(ticket.status) for ticket in tickets)
    providers = Counter(
        message.provider
        for message in messages
        if _value(message.author_type) == "ai" and message.provider
    )
    recent = sorted(tickets, key=lambda ticket: ticket.updated_at or ticket.created_at, reverse=True)[:8]
    return {
        "total": len(tickets),
        "open": statuses.get("open", 0),
        "pending": statuses.get("pending", 0),
        "resolved": statuses.get("resolved", 0),
        "closed": statuses.get("closed", 0),
        "ai_drafts": sum(1 for message in messages if _value(message.author_type) == "ai"),
        "approved_replies": sum(1 for message in messages if message.draft_status == "approved"),
        "escalated": sum(1 for ticket in tickets if ticket.escalated),
        "average_response_seconds": average_response_seconds(messages),
        "providers": [{"provider": name, "drafts": count} for name, count in sorted(providers.items())],
        "recent": recent,
    }


def average_response_seconds(messages) -> int | None:
    ordered = sorted(messages, key=lambda message: message.created_at)
    first_customer: dict = {}
    first_approved: dict = {}
    for message in ordered:
        if getattr(message, "internal", False) or message.created_at is None:
            continue
        ticket_id = message.ticket_id
        author = _value(message.author_type)
        if author == "customer" and ticket_id not in first_customer:
            first_customer[ticket_id] = message.created_at
        if author == "ai" and message.draft_status == "approved" and ticket_id not in first_approved:
            first_approved[ticket_id] = message.created_at
    samples = []
    for ticket_id, started in first_customer.items():
        approved = first_approved.get(ticket_id)
        if approved is not None and approved >= started:
            samples.append(int((approved - started).total_seconds()))
    if not samples:
        return None
    return int(sum(samples) / len(samples))


def _value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)
