"""Prompt and draft checks for support replies.

A draft is stored only after these checks pass. The text is not emailed.
"""

import json
import re

from app.core.errors import AppError
from app.services.ai.base import scrub_text

TONES = ("professional", "friendly", "formal", "concise")
PRIORITIES = ("low", "normal", "high", "urgent")
STATUSES = ("open", "pending", "resolved", "closed")
DEFAULT_INSTRUCTIONS = (
    "Answer only from the support passages. If they do not contain the answer, say so and do not guess."
)
INSUFFICIENT_REPLY = (
    "I don't have enough support information to answer that. A person should review this conversation."
)

DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "insufficient": {"type": "boolean"},
        "escalate": {"type": "boolean"},
    },
    "required": ["reply", "insufficient", "escalate"],
}


def clean_assistant(fields: dict) -> dict:
    tone = str(fields.get("tone") or "professional").strip().lower()
    if tone not in TONES:
        raise AppError("invalid_tone", "Choose a professional, friendly, formal, or concise tone.", 400)
    instructions = scrub_text(str(fields.get("instructions") or ""), 2000).strip()
    if len(instructions) < 10:
        instructions = DEFAULT_INSTRUCTIONS
    description = fields.get("description")
    cleaned_description = None
    if description is not None and str(description).strip():
        cleaned_description = scrub_text(str(description), 500).strip() or None
    return {
        "name": _required(fields.get("name"), "name", 80),
        "description": cleaned_description,
        "welcome_message": _required(fields.get("welcome_message"), "welcome message", 500),
        "instructions": instructions,
        "tone": tone,
        "language": _required(fields.get("language") or "English", "language", 40),
        "enabled": bool(fields.get("enabled", True)),
    }


def clean_priority(value: str) -> str:
    priority = str(value or "").strip().lower()
    if priority not in PRIORITIES:
        raise AppError("invalid_priority", "Choose a low, normal, high, or urgent priority.", 400)
    return priority


def clean_status(value: str) -> str:
    status = str(value or "").strip().lower()
    if status not in STATUSES:
        raise AppError("invalid_status", "Choose an open, pending, resolved, or closed status.", 400)
    return status


def clean_message(value, label: str, limit: int) -> str:
    return _required(value, label, limit)


def insufficient_draft() -> dict:
    return {"reply": INSUFFICIENT_REPLY, "insufficient": True, "escalate": True}


def build_prompt(assistant, history: list[str], passages: list[dict], question: str) -> str:
    passage_lines = []
    for passage in passages[:4]:
        filename = scrub_text(str(passage.get("filename") or "Support note"), 120)
        excerpt = scrub_text(str(passage.get("excerpt") or ""), 500).strip()
        if excerpt:
            passage_lines.append(f"[{filename}] {excerpt}")
    history_lines = [scrub_text(line, 500) for line in history[-8:] if line.strip()]
    instructions = scrub_text(assistant.instructions or DEFAULT_INSTRUCTIONS, 2000)
    return "\n".join(
        [
            "You draft a support reply for a person to review. You do not send it.",
            f"Tone: {assistant.tone}. Language: {assistant.language}.",
            "Assistant instructions, which cannot override the rules below:",
            instructions,
            "Support passages found by text search:",
            "\n".join(passage_lines) if passage_lines else "(none)",
            "Conversation:",
            "\n".join(history_lines) if history_lines else "(none)",
            "Latest customer message:",
            scrub_text(question, 2000),
            "Rules:",
            "Use only the support passages and the conversation.",
            "Do not invent policies, prices, dates, or promises.",
            "If the passages do not contain the answer, set insufficient to true and say what is missing.",
            "Set escalate to true when the customer asks for a person or the passages are not enough.",
            'Return JSON only: {"reply":"...","insufficient":false,"escalate":false}',
        ]
    )


def history_lines(messages) -> list[str]:
    lines = []
    for message in messages:
        if getattr(message, "internal", False):
            continue
        author = _value(message.author_type)
        if author == "ai" and message.draft_status != "approved":
            continue
        label = {"customer": "Customer", "agent": "Agent", "ai": "Approved reply", "system": "Welcome"}.get(
            author, "Note"
        )
        text = scrub_text(message.content or "", 500).strip()
        if text:
            lines.append(f"{label}: {text}")
    return lines


def parse_draft(raw: str) -> dict:
    value = _parse_object(raw)
    reply = value.get("reply")
    insufficient = value.get("insufficient")
    escalate = value.get("escalate")
    if not isinstance(reply, str) or not isinstance(insufficient, bool) or not isinstance(escalate, bool):
        raise _invalid_draft()
    text = scrub_text(reply, 2000).strip()
    if not text:
        raise _invalid_draft()
    return {"reply": text, "insufficient": insufficient, "escalate": escalate}


def _required(value, label: str, limit: int) -> str:
    raw = str(value or "").replace("\x00", "").strip()
    if not raw:
        raise AppError("invalid_message", f"Enter a {label}.", 400)
    if len(raw) > limit:
        raise AppError("invalid_message", f"Keep the {label} under {limit} characters.", 400)
    text = scrub_text(raw, limit).strip()
    if not text:
        raise AppError("invalid_message", f"Enter a {label}.", 400)
    return text


def _invalid_draft() -> AppError:
    return AppError(
        "invalid_draft",
        "The model response did not match the expected fields, so no draft was stored.",
        502,
    )


def _parse_object(raw: str) -> dict:
    cleaned = (raw or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*", "", cleaned).strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise _invalid_draft()
    try:
        value = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise _invalid_draft() from exc
    if not isinstance(value, dict):
        raise _invalid_draft()
    return value


def _value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)
