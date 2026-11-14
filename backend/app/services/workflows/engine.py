import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.services.ai.base import scrub_text
from app.services.ai.exceptions import ProviderChainFailed
from app.services.workflows.catalog import AI_TYPES, LOGIC_TYPES, MAX_AI_CALLS, MAX_SECONDS, MAX_TEXT
from app.services.workflows.graph import EdgeSpec, NodeSpec, prepare_graph

LoadSource = Callable[[str], dict | None]
Clock = Callable[[], float]


@dataclass(frozen=True)
class AiText:
    text: str
    provider: str
    model: str


@dataclass
class StepRecord:
    node_id: str
    node_type: str
    node_label: str
    status: str
    input_json: dict | None
    output_json: dict | None
    error_message: str | None
    started_at: datetime
    finished_at: datetime


@dataclass
class RunResult:
    status: str
    trigger_type: str
    error_message: str | None
    started_at: datetime
    finished_at: datetime
    steps: list[StepRecord] = field(default_factory=list)


class NodeFailure(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def execute_graph(
    nodes: list[NodeSpec],
    edges: list[EdgeSpec],
    *,
    text: str,
    document_id: str | None,
    dataset_id: str | None,
    load_document: LoadSource,
    load_dataset: LoadSource,
    complete_ai: Callable[[str], AiText],
    clock: Clock | None = None,
    max_seconds: float = MAX_SECONDS,
) -> RunResult:
    """Run a validated graph in one request. Node code, shell, and SQL are not accepted."""
    prepared = prepare_graph(nodes, edges)
    tick = clock or time.monotonic
    started = datetime.now(timezone.utc)
    origin = tick()
    by_id = {node.id: node for node in prepared.nodes}
    outgoing: dict[str, list[EdgeSpec]] = {node.id: [] for node in prepared.nodes}
    for edge in prepared.edges:
        outgoing[edge.source].append(edge)
    activated = {prepared.order[0].id}
    bag: dict = {"text": "", "fields": {}}
    steps: list[StepRecord] = []
    failed: str | None = None
    cursor = started
    ai_calls = 0

    for node in prepared.order:
        if failed:
            cursor = _append(steps, node, "cancelled", None, {"skipped": True, "reason": "Stopped because an earlier step failed."}, "Stopped because an earlier step failed.", cursor, 0)
            continue
        if node.id not in activated:
            cursor = _append(steps, node, "cancelled", _snapshot(bag, text), {"skipped": True, "reason": "This branch was not taken."}, None, cursor, 0)
            continue
        now = tick()
        if now - origin > max_seconds:
            failed = f"{node.label}: This run reached the time limit."
            cursor = _append(steps, node, "failed", _snapshot(bag, text), None, failed, cursor, 0)
            continue
        begin = now
        snapshot = _snapshot(bag, text)
        try:
            if node.node_type in AI_TYPES:
                if ai_calls >= MAX_AI_CALLS:
                    raise NodeFailure("This run reached the AI request limit.")
                ai_calls += 1
            output = _run_node(
                node,
                bag,
                text=text,
                document_id=document_id,
                dataset_id=dataset_id,
                load_document=load_document,
                load_dataset=load_dataset,
                complete_ai=complete_ai,
            )
        except NodeFailure as exc:
            failed = f"{node.label}: {exc.message}"[:500]
            cursor = _append(steps, node, "failed", snapshot, None, failed, cursor, _millis(tick() - begin))
            continue
        except ProviderChainFailed:
            failed = f"{node.label}: The AI providers could not complete this step."
            cursor = _append(steps, node, "failed", snapshot, None, failed, cursor, _millis(tick() - begin))
            continue
        bag = _merge(bag, output)
        _activate(node, output, outgoing, activated, by_id)
        cursor = _append(steps, node, "succeeded", snapshot, output, None, cursor, _millis(tick() - begin))

    return RunResult(
        status="failed" if failed else "succeeded",
        trigger_type="manual",
        error_message=failed,
        started_at=started,
        finished_at=datetime.now(timezone.utc),
        steps=steps,
    )


def _run_node(node: NodeSpec, bag: dict, *, text, document_id, dataset_id, load_document, load_dataset, complete_ai) -> dict:
    kind = node.node_type
    if kind == "manual_trigger":
        body = scrub_text(text or "", MAX_TEXT).strip()
        if not body:
            raise NodeFailure("Enter some text before running this workflow.")
        return {"text": body}
    if kind == "document_uploaded":
        return _source(document_id, load_document, "Choose a document before running this workflow.", "That document is not in this organization.", "document_id", "filename")
    if kind == "dataset_uploaded":
        return _source(dataset_id, load_dataset, "Choose a dataset before running this workflow.", "That dataset is not ready in this organization.", "dataset_id", "name")
    if kind in AI_TYPES:
        return _ai(node, bag, complete_ai)
    if kind == "condition":
        result = _compare(_lookup(bag, node.config["field"]), node.config["operator"], node.config.get("value", ""))
        return _branch(bag, result)
    if kind == "compare_values":
        right = _lookup(bag, node.config["right_field"]) if node.config.get("right_field") else node.config.get("right_value", "")
        result = _compare(_lookup(bag, node.config["left_field"]), node.config["operator"], right)
        return _branch(bag, result)
    if kind == "field_exists":
        value = _lookup(bag, node.config["field"])
        return _branch(bag, value is not None and str(value).strip() != "")
    if kind == "save_result":
        return {"name": node.config["name"], "saved": True, "text": _text(bag), "fields": dict(bag.get("fields") or {})}
    if kind == "update_status":
        return {"status": node.config["status"], "text": _text(bag)}
    if kind == "create_notification":
        message = scrub_text(node.config.get("message") or _text(bag), 500).strip()
        return {"title": node.config["title"], "message": message, "text": message}
    if kind == "generate_report":
        lines = [node.config["title"], ""]
        if _text(bag):
            lines.append(_text(bag))
        fields = bag.get("fields") if isinstance(bag.get("fields"), dict) else {}
        if fields:
            lines.append("")
            for key, value in list(fields.items())[:12]:
                lines.append(f"{key}: {value}")
        report = scrub_text("\n".join(lines).strip(), MAX_TEXT)
        return {"title": node.config["title"], "text": report, "report": report}
    raise NodeFailure("That node type is not available.")


def _source(identifier, loader, missing: str, absent: str, id_key: str, name_key: str) -> dict:
    if not identifier:
        raise NodeFailure(missing)
    loaded = loader(str(identifier))
    if not loaded:
        raise NodeFailure(absent)
    body = scrub_text(str(loaded.get("text") or ""), MAX_TEXT).strip()
    if not body:
        raise NodeFailure("This file has no readable text.")
    output = {"text": body, id_key: str(identifier)}
    if loaded.get(name_key):
        output[name_key] = scrub_text(str(loaded[name_key]), 200)
    return output


def _ai(node: NodeSpec, bag: dict, complete_ai) -> dict:
    source = _text(bag)
    if not source:
        raise NodeFailure("The previous step did not produce any text.")
    task, hint, read = _ai_contract(node)
    instruction = node.config.get("instruction") or node.config.get("question") or task
    prompt = (
        "You are one step in a VansoraAI workflow. "
        "Return one JSON object and nothing else. Do not use markdown. Do not add keys. "
        f"Task: {task} "
        f"Instruction: {instruction} "
        f"JSON shape: {hint} "
        f"Text:\n{source[:6000]}"
    )
    try:
        result = complete_ai(prompt)
    except ProviderChainFailed:
        raise
    if not isinstance(result, AiText) or not isinstance(result.text, str):
        raise NodeFailure("The model response could not be read, so it was not passed on.")
    payload = _parse_object(result.text)
    output = read(node, payload)
    output["provider"] = scrub_text(result.provider, 40)
    output["model"] = scrub_text(result.model, 80)
    return output


def _ai_contract(node: NodeSpec):
    if node.node_type == "summarise_text":
        return ("Summarise the text.", '{"summary": "short text"}', _read_summary)
    if node.node_type == "extract_information":
        names = ", ".join(node.config["fields"])
        return ("Extract the requested fields.", f'{{"fields": {{"{names}": "text"}}}}', _read_fields)
    if node.node_type == "classify_content":
        names = ", ".join(node.config["labels"])
        return (f"Choose exactly one label from: {names}.", '{"label": "one configured label"}', _read_label)
    if node.node_type == "generate_response":
        return ("Write the requested response.", '{"response": "text"}', _read_response)
    return ("Answer the question from the text.", '{"analysis": "text"}', _read_analysis)


def _read_summary(_node: NodeSpec, payload: dict) -> dict:
    summary = _required_text(payload, "summary")
    return {"text": summary, "summary": summary}


def _read_fields(node: NodeSpec, payload: dict) -> dict:
    raw = payload.get("fields")
    if not isinstance(raw, dict):
        raise NodeFailure("The model response did not include the requested fields, so it was not passed on.")
    fields = {}
    for name in node.config["fields"]:
        if name not in raw:
            raise NodeFailure(f"The model response did not include {name}, so it was not passed on.")
        value = raw[name]
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise NodeFailure(f"The model response did not include {name}, so it was not passed on.")
        if isinstance(value, float) and (value != value or value in {float("inf"), float("-inf")}):
            raise NodeFailure(f"The model response did not include {name}, so it was not passed on.")
        text = scrub_text(str(value), 500).strip()
        if not text:
            raise NodeFailure(f"The model response left {name} empty, so it was not passed on.")
        fields[name] = text
    lines = [f"{name}: {value}" for name, value in fields.items()]
    return {"text": "\n".join(lines), "fields": fields}


def _read_label(node: NodeSpec, payload: dict) -> dict:
    label = _required_text(payload, "label")
    match = next((choice for choice in node.config["labels"] if choice.casefold() == label.casefold()), None)
    if match is None:
        raise NodeFailure("The model returned a label that is not one of the configured choices, so it was not passed on.")
    return {"text": match, "label": match}


def _read_response(_node: NodeSpec, payload: dict) -> dict:
    text = _required_text(payload, "response")
    return {"text": text, "response": text}


def _read_analysis(_node: NodeSpec, payload: dict) -> dict:
    text = _required_text(payload, "analysis")
    return {"text": text, "analysis": text}


def _required_text(payload: dict, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise NodeFailure(f"The model response did not include {key}, so it was not passed on.")
    text = scrub_text(value, 4000).strip()
    if not text:
        raise NodeFailure(f"The model response did not include {key}, so it was not passed on.")
    return text


def _parse_object(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*", "", cleaned).strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise NodeFailure("The model response did not match the expected fields, so it was not passed on.")
    try:
        value = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise NodeFailure("The model response did not match the expected fields, so it was not passed on.") from exc
    if not isinstance(value, dict):
        raise NodeFailure("The model response did not match the expected fields, so it was not passed on.")
    return value


def _branch(bag: dict, result: bool) -> dict:
    return {"result": result, "branch": "true" if result else "false", "text": _text(bag)}


def _compare(left, operator: str, right) -> bool:
    if operator in {"gt", "lt", "gte", "lte"}:
        left_number = _number(left)
        right_number = _number(right)
        if left_number is None or right_number is None:
            raise NodeFailure("Both values need to be numbers for this comparison.")
        if operator == "gt":
            return left_number > right_number
        if operator == "lt":
            return left_number < right_number
        if operator == "gte":
            return left_number >= right_number
        return left_number <= right_number
    left_text = "" if left is None else str(left).strip().lower()
    right_text = "" if right is None else str(right).strip().lower()
    if operator == "eq":
        return left_text == right_text
    if operator == "ne":
        return left_text != right_text
    if operator == "contains":
        return right_text in left_text
    raise NodeFailure("That comparison is not available.")


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (value != value or value in {float("inf"), float("-inf")}):
            return None
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _lookup(bag: dict, field: str):
    fields = bag.get("fields") if isinstance(bag.get("fields"), dict) else {}
    direct = bag.get(field)
    if field in {"text", "label", "result", "filename", "name", "title", "summary", "analysis", "response"} and isinstance(direct, (str, int, float, bool)):
        return direct
    if field in fields:
        return fields[field]
    if isinstance(direct, (str, int, float, bool)):
        return direct
    return None


def _text(bag: dict) -> str:
    value = bag.get("text")
    return value if isinstance(value, str) else ""


def _merge(bag: dict, output: dict) -> dict:
    merged = {"text": bag.get("text") or "", "fields": dict(bag.get("fields") or {})}
    if isinstance(output.get("text"), str):
        merged["text"] = output["text"]
    if isinstance(output.get("fields"), dict):
        merged["fields"].update(output["fields"])
    for key, value in output.items():
        if key in {"text", "fields"}:
            continue
        if isinstance(value, (str, int, float, bool)):
            merged[key] = value
    return merged


def _activate(node: NodeSpec, output: dict, outgoing: dict[str, list[EdgeSpec]], activated: set[str], by_id: dict[str, NodeSpec]) -> None:
    handle = None
    if node.node_type in LOGIC_TYPES:
        handle = "true" if output.get("result") is True else "false"
    for edge in outgoing[node.id]:
        if handle is not None and edge.source_handle != handle:
            continue
        if edge.target in by_id:
            activated.add(edge.target)


def _snapshot(bag: dict, run_text: str) -> dict:
    fields = bag.get("fields") if isinstance(bag.get("fields"), dict) else {}
    safe = {str(key)[:80]: scrub_text(str(value), 200) for key, value in list(fields.items())[:12]}
    return {"text": scrub_text(str(bag.get("text") or run_text or ""), 2000), "fields": safe}


def _append(steps: list[StepRecord], node: NodeSpec, status: str, payload: dict | None, output: dict | None, error: str | None, cursor: datetime, duration_ms: int) -> datetime:
    started = cursor
    finished = cursor + timedelta(milliseconds=max(duration_ms, 0) + 1)
    steps.append(
        StepRecord(
            node_id=node.id,
            node_type=node.node_type,
            node_label=node.label,
            status=status,
            input_json=payload,
            output_json=output,
            error_message=error[:500] if error else None,
            started_at=started,
            finished_at=finished,
        )
    )
    return finished


def _millis(seconds: float) -> int:
    if seconds < 0:
        return 0
    return int(seconds * 1000)
