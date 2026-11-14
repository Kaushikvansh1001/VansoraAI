import re
import uuid

from app.core.errors import AppError
from app.services.ai.base import scrub_text

MAX_NODES = 24
MAX_EDGES = 40
MAX_SECONDS = 20
MAX_AI_CALLS = 4
MAX_TEXT = 8000

NODE_TYPES = {
    "manual_trigger": "trigger",
    "document_uploaded": "trigger",
    "dataset_uploaded": "trigger",
    "summarise_text": "ai",
    "extract_information": "ai",
    "classify_content": "ai",
    "generate_response": "ai",
    "analyse_document": "ai",
    "condition": "logic",
    "compare_values": "logic",
    "field_exists": "logic",
    "save_result": "action",
    "update_status": "action",
    "create_notification": "action",
    "generate_report": "action",
}

TRIGGERS = {name for name, category in NODE_TYPES.items() if category == "trigger"}
AI_TYPES = {name for name, category in NODE_TYPES.items() if category == "ai"}
LOGIC_TYPES = {name for name, category in NODE_TYPES.items() if category == "logic"}
OPERATORS = {"eq", "ne", "contains", "gt", "lt", "gte", "lte"}
STATUSES = {"draft", "active", "paused"}
FIELD_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_ ]{0,40}$")

# text fields: (limit, required, default or None)
_TEXT = {
    "manual_trigger": {},
    "document_uploaded": {},
    "dataset_uploaded": {},
    "summarise_text": {"instruction": (300, False, "Summarise the text in one short paragraph.")},
    "generate_response": {"instruction": (400, True, None)},
    "analyse_document": {"question": (400, True, None)},
    "condition": {"field": (80, True, None), "value": (200, False, "")},
    "compare_values": {"left_field": (80, True, None), "right_field": (80, False, ""), "right_value": (200, False, "")},
    "field_exists": {"field": (80, True, None)},
    "save_result": {"name": (80, True, None)},
    "create_notification": {"title": (120, True, None), "message": (400, False, "")},
    "generate_report": {"title": (120, True, None)},
}


def list_templates() -> list[dict]:
    return [{"id": key, "name": item["name"], "description": item["description"]} for key, item in TEMPLATES.items()]


def build_template(template_id: str):
    from app.services.workflows.graph import EdgeSpec, NodeSpec

    found = TEMPLATES.get(template_id)
    if found is None:
        raise AppError("not_found", "That template does not exist.", 404)
    assigned = {key: str(uuid.uuid4()) for key in found["ids"]}
    nodes = [
        NodeSpec(assigned[key], node_type, label, dict(config), x, y)
        for key, node_type, label, config, x, y in found["nodes"]
    ]
    edges = [EdgeSpec(assigned[source], assigned[target], handle) for source, target, handle in found["edges"]]
    return found["name"], found["description"], nodes, edges


def clean_config(node_type: str, label: str, config: dict) -> dict:
    if not isinstance(config, dict):
        raise AppError("invalid_workflow", f"{label}: configuration must be an object.", 400)
    if node_type == "classify_content":
        return {"labels": _choices(config, label, "labels", minimum=2, maximum=8)}
    if node_type == "extract_information":
        return {"fields": _choices(config, label, "fields", minimum=1, maximum=6)}
    if node_type == "update_status":
        unknown = set(config) - {"status"}
        if unknown:
            raise AppError("invalid_workflow", f"{label}: {', '.join(sorted(unknown))} is not a setting for this node.", 400)
        status = config.get("status")
        if not isinstance(status, str) or status not in STATUSES:
            raise AppError("invalid_workflow", f"{label}: status must be draft, active, or paused.", 400)
        return {"status": status}

    allowed = _TEXT.get(node_type)
    if allowed is None:
        raise AppError("invalid_workflow", f"{label}: this node type is not available.", 400)
    extra = {"operator"} if node_type in {"condition", "compare_values"} else set()
    unknown = set(config) - set(allowed) - extra
    if unknown:
        raise AppError("invalid_workflow", f"{label}: {', '.join(sorted(unknown))} is not a setting for this node.", 400)
    cleaned: dict = {}
    for key, (limit, required, default) in allowed.items():
        if key not in config or config[key] is None or config[key] == "":
            if required:
                raise AppError("invalid_workflow", f"{label}: {key.replace('_', ' ')} is required.", 400)
            if default is None:
                continue
            cleaned[key] = default
            continue
        if not isinstance(config[key], str):
            raise AppError("invalid_workflow", f"{label}: {key.replace('_', ' ')} must be text.", 400)
        cleaned[key] = scrub_text(config[key], limit).strip()
        if required and not cleaned[key]:
            raise AppError("invalid_workflow", f"{label}: {key.replace('_', ' ')} is required.", 400)
    if node_type in {"condition", "compare_values"}:
        _require_operator(label, config, cleaned)
        _require_field(label, cleaned.get("field") or cleaned.get("left_field") or "")
    if node_type == "field_exists":
        _require_field(label, cleaned.get("field", ""))
    if node_type == "compare_values":
        right_field = cleaned.get("right_field") or ""
        right_value = cleaned.get("right_value") or ""
        if bool(right_field) == bool(right_value):
            raise AppError("invalid_workflow", f"{label}: set either a field or a value to compare, not both.", 400)
        if right_field:
            _require_field(label, right_field)
        if not right_field:
            cleaned.pop("right_field", None)
        if not right_value:
            cleaned.pop("right_value", None)
    if node_type == "condition":
        operator = cleaned.get("operator")
        value = cleaned.get("value", "")
        if operator in {"contains", "gt", "lt", "gte", "lte"} and not value:
            raise AppError("invalid_workflow", f"{label}: enter a value to compare.", 400)
    return cleaned


def _require_operator(label: str, raw: dict, cleaned: dict) -> None:
    if "operator" not in raw:
        raise AppError("invalid_workflow", f"{label}: choose a comparison.", 400)
    operator = raw["operator"]
    if not isinstance(operator, str) or operator not in OPERATORS:
        raise AppError("invalid_workflow", f"{label}: that comparison is not available.", 400)
    cleaned["operator"] = operator


def _require_field(label: str, field: str) -> None:
    if not FIELD_NAME.match(field):
        raise AppError("invalid_workflow", f"{label}: use a short field name that starts with a letter.", 400)


def _choices(config: dict, label: str, key: str, *, minimum: int, maximum: int) -> list[str]:
    unknown = set(config) - {key}
    if unknown:
        raise AppError("invalid_workflow", f"{label}: {', '.join(sorted(unknown))} is not a setting for this node.", 400)
    raw = config.get(key)
    if not isinstance(raw, list):
        raise AppError("invalid_workflow", f"{label}: {key} must be a list.", 400)
    values: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            raise AppError("invalid_workflow", f"{label}: each entry must be text.", 400)
        cleaned = scrub_text(item, 40).strip()
        if not cleaned:
            continue
        marker = cleaned.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        values.append(cleaned)
    if len(values) < minimum:
        raise AppError("invalid_workflow", f"{label}: add at least {minimum} {key}.", 400)
    if len(values) > maximum:
        raise AppError("invalid_workflow", f"{label}: use at most {maximum} {key}.", 400)
    return values


def _node(key, node_type, label, config, x, y):
    return (key, node_type, label, config, x, y)


TEMPLATES = {
    "document_summary": {
        "name": "Document summarisation",
        "description": "Read a document, write a short summary, save it, and leave a notification on the run.",
        "ids": ("start", "summarise", "save", "notify"),
        "nodes": [
            _node("start", "document_uploaded", "Document uploaded", {}, 40, 120),
            _node("summarise", "summarise_text", "Summarise", {"instruction": "Summarise the document in one short paragraph."}, 320, 120),
            _node("save", "save_result", "Save summary", {"name": "Summary"}, 600, 120),
            _node("notify", "create_notification", "Notify", {"title": "Summary ready", "message": "The summary is stored on this run."}, 880, 120),
        ],
        "edges": [("start", "summarise", "out"), ("summarise", "save", "out"), ("save", "notify", "out")],
    },
    "document_classification": {
        "name": "Document classification",
        "description": "Classify a document and take a different branch when the label is Invoice.",
        "ids": ("start", "classify", "check", "invoice", "other"),
        "nodes": [
            _node("start", "document_uploaded", "Document uploaded", {}, 40, 140),
            _node("classify", "classify_content", "Classify", {"labels": ["Invoice", "Contract", "Report", "Other"]}, 320, 140),
            _node("check", "condition", "Invoice?", {"field": "label", "operator": "eq", "value": "Invoice"}, 600, 140),
            _node("invoice", "create_notification", "Invoice received", {"title": "Invoice received"}, 900, 40),
            _node("other", "save_result", "Save classification", {"name": "Classification"}, 900, 240),
        ],
        "edges": [
            ("start", "classify", "out"),
            ("classify", "check", "out"),
            ("check", "invoice", "true"),
            ("check", "other", "false"),
        ],
    },
    "data_insights": {
        "name": "AI-powered data insights",
        "description": "Read a dataset profile, ask for the main patterns, and save a text report.",
        "ids": ("start", "analyse", "report", "save"),
        "nodes": [
            _node("start", "dataset_uploaded", "Dataset uploaded", {}, 40, 120),
            _node("analyse", "analyse_document", "Analyse", {"question": "What are the main patterns in this dataset summary?"}, 320, 120),
            _node("report", "generate_report", "Report", {"title": "Data insights"}, 600, 120),
            _node("save", "save_result", "Save insights", {"name": "Insights"}, 880, 120),
        ],
        "edges": [("start", "analyse", "out"), ("analyse", "report", "out"), ("report", "save", "out")],
    },
    "document_approval": {
        "name": "Document approval",
        "description": "Classify a document as Approve, Review, or Reject, then update the workflow only on Approve.",
        "ids": ("start", "classify", "check", "activate", "approved", "review"),
        "nodes": [
            _node("start", "document_uploaded", "Document uploaded", {}, 40, 140),
            _node("classify", "classify_content", "Decide", {"labels": ["Approve", "Review", "Reject"]}, 320, 140),
            _node("check", "condition", "Approved?", {"field": "label", "operator": "eq", "value": "Approve"}, 600, 140),
            _node("activate", "update_status", "Mark active", {"status": "active"}, 880, 40),
            _node("approved", "create_notification", "Approved", {"title": "Document approved"}, 1160, 40),
            _node("review", "create_notification", "Needs review", {"title": "Needs review"}, 880, 250),
        ],
        "edges": [
            ("start", "classify", "out"),
            ("classify", "check", "out"),
            ("check", "activate", "true"),
            ("activate", "approved", "out"),
            ("check", "review", "false"),
        ],
    },
}
