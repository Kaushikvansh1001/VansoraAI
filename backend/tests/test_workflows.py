import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.core.errors import AppError
from app.models.enums import ExecutionStatus, WorkflowStatus
from app.models.workflows import Workflow, WorkflowEdge, WorkflowExecution, WorkflowExecutionStep, WorkflowNode
from app.repositories.workflows import document_lookup, execution_lookup, workflow_lookup
from app.services.ai.exceptions import ProviderChainFailed
from app.services.ai.models import GenerationOutcome, ProviderResponse, TokenUsage
from app.services.workflows.catalog import build_template, list_templates
from app.services.workflows.engine import AiText, execute_graph
from app.services.workflows.graph import EdgeSpec, NodeSpec, prepare_graph
from app.services.workflows.service import WorkflowService
from app.services.workflows.sources import dataset_summary_text


def test_templates_are_valid_graphs():
    templates = list_templates()
    assert len(templates) >= 4
    assert {item["id"] for item in templates} >= {
        "document_summary",
        "document_classification",
        "data_insights",
        "document_approval",
    }
    for item in templates:
        _name, _description, nodes, edges = build_template(item["id"])
        prepared = prepare_graph(nodes, edges)
        assert prepared.order[0].node_type.endswith("uploaded") or prepared.order[0].node_type == "manual_trigger"
        assert len(prepared.nodes) == len(nodes)


def test_invalid_graphs_are_rejected():
    start = _id()
    other = _id()
    with pytest.raises(AppError) as shell:
        prepare_graph([NodeSpec(start, "shell", "Run code", {"command": "ls"})], [])
    assert shell.value.code == "invalid_workflow"

    with pytest.raises(AppError):
        prepare_graph(
            [NodeSpec(start, "manual_trigger", "Start", {}), NodeSpec(other, "manual_trigger", "Again", {})],
            [],
        )

    save = _id()
    with pytest.raises(AppError):
        prepare_graph(
            [NodeSpec(start, "manual_trigger", "Start", {}), NodeSpec(save, "save_result", "Save", {"name": "Result"})],
            [EdgeSpec(save, start, "out")],
        )

    left = _id()
    right = _id()
    with pytest.raises(AppError):
        prepare_graph(
            [
                NodeSpec(start, "manual_trigger", "Start", {}),
                NodeSpec(left, "save_result", "Left", {"name": "Left"}),
                NodeSpec(right, "save_result", "Right", {"name": "Right"}),
            ],
            [EdgeSpec(start, left, "out"), EdgeSpec(left, right, "out"), EdgeSpec(right, left, "out")],
        )

    check = _id()
    with pytest.raises(AppError):
        prepare_graph(
            [
                NodeSpec(start, "manual_trigger", "Start", {}),
                NodeSpec(check, "condition", "Check", {"field": "text", "operator": "eq", "value": "yes"}),
            ],
            [EdgeSpec(start, check, "true")],
        )

    with pytest.raises(AppError):
        prepare_graph(
            [NodeSpec(start, "manual_trigger", "Start", {}), NodeSpec(save, "save_result", "Save", {"name": "Result", "python": "open"})],
            [EdgeSpec(start, save, "out")],
        )

    nodes = [NodeSpec(start, "manual_trigger", "Start", {}, 0, 0)]
    edges = []
    previous = start
    for index in range(5):
        current = _id()
        nodes.append(NodeSpec(current, "summarise_text", f"Summary {index}", {"instruction": "Summarise."}, index + 1, 0))
        edges.append(EdgeSpec(previous, current, "out"))
        previous = current
    with pytest.raises(AppError):
        prepare_graph(nodes, edges)


def test_condition_runs_only_the_matching_branch():
    yes = _run_branch("yes")
    no = _run_branch("no")
    assert _step(yes, "Kept").status == "succeeded"
    assert _step(yes, "Dropped").output_json["skipped"] is True
    assert _step(no, "Dropped").status == "succeeded"
    assert _step(no, "Kept").status == "cancelled"
    assert yes.status == "succeeded"


def test_compare_values_and_field_exists():
    greater = _compare("10", "gt", "2")
    smaller = _compare("1", "gt", "2")
    assert _step(greater, "Kept").status == "succeeded"
    assert _step(smaller, "Dropped").status == "succeeded"

    literal = _compare("AB", "contains", "A.B")
    assert _step(literal, "Kept").status == "cancelled"
    assert _step(literal, "Dropped").status == "succeeded"

    missing = _exists("missing")
    present = _exists("text")
    assert _step(missing, "Dropped").status == "succeeded"
    assert _step(present, "Kept").status == "succeeded"


def test_ai_output_must_match_before_it_is_passed_on():
    calls = []
    result = _run(
        _line(
            ("manual_trigger", "Start", {}),
            ("summarise_text", "Summarise", {"instruction": "Summarise."}),
            ("save_result", "Save", {"name": "Summary"}),
        ),
        text="A long note",
        complete=_ai('{"summary": "A short summary."}', calls),
    )
    assert result.status == "succeeded"
    assert _step(result, "Save").output_json["text"] == "A short summary."
    assert len(calls) == 1
    assert "gsk_" not in calls[0]

    rejected = _run(
        _line(
            ("manual_trigger", "Start", {}),
            ("classify_content", "Classify", {"labels": ["Approve", "Reject"]}),
            ("save_result", "Save", {"name": "Decision"}),
        ),
        text="Please review",
        complete=_ai('{"label": "Drop table"}', []),
    )
    assert rejected.status == "failed"
    assert _step(rejected, "Classify").output_json is None
    assert _step(rejected, "Save").status == "cancelled"
    assert "Drop table" not in json.dumps([step.output_json for step in rejected.steps])

    accepted = _run(
        _line(("manual_trigger", "Start", {}), ("classify_content", "Classify", {"labels": ["Approve", "Reject"]})),
        text="Please review",
        complete=_ai('{"label": "approve"}', []),
    )
    assert _step(accepted, "Classify").output_json["label"] == "Approve"


def test_provider_key_in_model_text_is_redacted():
    result = _run(
        _line(("manual_trigger", "Start", {}), ("summarise_text", "Summarise", {"instruction": "Summarise."})),
        text="A note",
        complete=_ai('{"summary": "token gsk_abcdefghijklmnopqrstuvwxyz"}', []),
    )
    dumped = json.dumps(_step(result, "Summarise").output_json)
    assert result.status == "succeeded"
    assert "gsk_" not in dumped
    assert "[redacted]" in dumped


def test_provider_failure_stops_the_run():
    def fail(_prompt):
        raise ProviderChainFailed([])

    result = _run(
        _line(
            ("manual_trigger", "Start", {}),
            ("summarise_text", "Summarise", {"instruction": "Summarise."}),
            ("save_result", "Save", {"name": "Summary"}),
        ),
        text="A note",
        complete=fail,
    )
    assert result.status == "failed"
    assert "could not complete" in result.error_message
    assert _step(result, "Save").status == "cancelled"
    assert _step(result, "Save").output_json["skipped"] is True


def test_time_limit_stops_before_later_nodes():
    result = _run(
        _line(("manual_trigger", "Start", {}), ("save_result", "Save", {"name": "Summary"})),
        text="A note",
        clock=lambda: 0,
        max_seconds=-1,
    )
    assert result.status == "failed"
    assert "time limit" in result.error_message
    assert _step(result, "Save").status == "cancelled"


def test_missing_document_does_not_call_the_model():
    def fail(_prompt):
        raise AssertionError("The model should not be called.")

    result = _run(
        _line(("document_uploaded", "Document", {}), ("summarise_text", "Summarise", {"instruction": "Summarise."})),
        document_id=str(uuid.uuid4()),
        load_document=lambda _value: None,
        complete=fail,
    )
    assert result.status == "failed"
    assert "not in this organization" in result.error_message
    assert _step(result, "Summarise").status == "cancelled"


def test_dataset_summary_uses_profile_numbers():
    text = dataset_summary_text(
        "sales.csv",
        4,
        1,
        {"columns": [{"name": "revenue", "type": "number", "missing": 0, "numeric": {"sum": 70}}]},
    )
    assert "revenue" in text
    assert "70" in text
    assert "storage" not in text


def test_queries_are_scoped_to_the_organization():
    organization_id = uuid.uuid4()
    workflow_sql = str(workflow_lookup(organization_id, uuid.uuid4()).compile(dialect=postgresql.dialect()))
    document_sql = str(document_lookup(organization_id, uuid.uuid4()).compile(dialect=postgresql.dialect()))
    execution_sql = str(execution_lookup(organization_id, uuid.uuid4()).compile(dialect=postgresql.dialect()))
    assert "workflows.organization_id" in workflow_sql
    assert "documents.organization_id" in document_sql
    assert "workflow_executions.organization_id" in execution_sql


def test_save_reopen_and_other_organization_cannot_run():
    organization_id = uuid.uuid4()
    user_id = uuid.uuid4()
    repo = MemoryWorkflows()
    service = WorkflowService(db=None, repository=repo, manager=_Boom())
    start = uuid.uuid4()
    workflow, nodes, _edges = service.create(
        organization_id=organization_id,
        user_id=user_id,
        name="Approval",
        description="Check a note",
        status="draft",
        nodes=[_input(start, "manual_trigger", "Start")],
        edges=[],
    )
    assert nodes[0].label == "Start"
    reopened, reopened_nodes, _reopened_edges = service.get(organization_id, workflow.id)
    assert reopened.name == "Approval"
    assert reopened_nodes[0].node_type == "manual_trigger"

    renamed, renamed_nodes, _renamed_edges = service.update(
        organization_id=organization_id,
        workflow_id=workflow.id,
        name="Approval renamed",
        description=None,
        status="active",
        nodes=[_input(renamed_id := reopened_nodes[0].id, "manual_trigger", "Begin")],
        edges=[],
    )
    assert renamed.name == "Approval renamed"
    assert renamed_nodes[0].label == "Begin"
    assert renamed_id == reopened_nodes[0].id

    with pytest.raises(AppError) as missing:
        service.run(
            organization_id=uuid.uuid4(),
            user_id=user_id,
            workflow_id=workflow.id,
            text="hello",
            document_id=None,
            dataset_id=None,
        )
    assert missing.value.code == "not_found"


def test_paused_workflow_does_not_run():
    organization_id = uuid.uuid4()
    repo = MemoryWorkflows()
    service = WorkflowService(db=None, repository=repo, manager=_Boom())
    workflow, nodes, _edges = service.create(
        organization_id=organization_id,
        user_id=uuid.uuid4(),
        name="Paused",
        description=None,
        status="paused",
        nodes=[_input(uuid.uuid4(), "manual_trigger", "Start")],
        edges=[],
    )
    with pytest.raises(AppError) as paused:
        service.run(
            organization_id=organization_id,
            user_id=uuid.uuid4(),
            workflow_id=workflow.id,
            text="hello",
            document_id=None,
            dataset_id=None,
        )
    assert paused.value.code == "workflow_paused"
    assert nodes[0].node_type == "manual_trigger"


def test_execution_history_keeps_node_output_and_hides_other_organizations():
    organization_id = uuid.uuid4()
    repo = MemoryWorkflows()
    service = WorkflowService(db=None, repository=repo, manager=_SummaryManager())
    start = uuid.uuid4()
    summary = uuid.uuid4()
    workflow, _nodes, _edges = service.create(
        organization_id=organization_id,
        user_id=uuid.uuid4(),
        name="Notes",
        description=None,
        status="active",
        nodes=[
            _input(start, "manual_trigger", "Start", x=0),
            _input(summary, "summarise_text", "Summarise", {"instruction": "Summarise."}, x=200),
        ],
        edges=[_edge(start, summary)],
    )
    execution, name, steps = service.run(
        organization_id=organization_id,
        user_id=uuid.uuid4(),
        workflow_id=workflow.id,
        text="A note about revenue",
        document_id=None,
        dataset_id=None,
    )
    assert name == "Notes"
    assert execution.status == ExecutionStatus.succeeded
    assert steps[1].output_json["summary"] == "Noted."
    assert "gsk_" not in json.dumps(steps[1].output_json)
    found = service.get_run(organization_id, execution.id)
    assert found[2][1].node_label == "Summarise"
    with pytest.raises(AppError) as hidden:
        service.get_run(uuid.uuid4(), execution.id)
    assert hidden.value.code == "not_found"


def test_document_lookup_uses_the_caller_organization():
    organization_id = uuid.uuid4()
    other = uuid.uuid4()
    document_id = uuid.uuid4()
    repo = MemoryWorkflows()
    repo.documents[(other, document_id)] = {"filename": "secret.txt", "text": "secret"}
    service = WorkflowService(db=None, repository=repo, manager=_Boom())
    start = uuid.uuid4()
    workflow, _nodes, _edges = service.create(
        organization_id=organization_id,
        user_id=uuid.uuid4(),
        name="Read",
        description=None,
        status="draft",
        nodes=[_input(start, "document_uploaded", "Document")],
        edges=[],
    )
    execution, _name, steps = service.run(
        organization_id=organization_id,
        user_id=uuid.uuid4(),
        workflow_id=workflow.id,
        text="",
        document_id=document_id,
        dataset_id=None,
    )
    assert execution.status == ExecutionStatus.failed
    assert repo.loaded_orgs == [organization_id]
    assert steps[0].output_json is None
    assert "secret" not in (steps[0].error_message or "")


def _run_branch(text: str):
    start, check, yes, no = _id(), _id(), _id(), _id()
    return _run(
        (
            [
                NodeSpec(start, "manual_trigger", "Start", {}, 0, 0),
                NodeSpec(check, "condition", "Check", {"field": "text", "operator": "eq", "value": "yes"}, 200, 0),
                NodeSpec(yes, "save_result", "Kept", {"name": "Kept"}, 400, -40),
                NodeSpec(no, "save_result", "Dropped", {"name": "Dropped"}, 400, 80),
            ],
            [EdgeSpec(start, check, "out"), EdgeSpec(check, yes, "true"), EdgeSpec(check, no, "false")],
        ),
        text=text,
    )


def _compare(text: str, operator: str, value: str):
    start, check, yes, no = _id(), _id(), _id(), _id()
    return _run(
        (
            [
                NodeSpec(start, "manual_trigger", "Start", {}, 0, 0),
                NodeSpec(check, "compare_values", "Compare", {"left_field": "text", "operator": operator, "right_value": value}, 200, 0),
                NodeSpec(yes, "save_result", "Kept", {"name": "Kept"}, 400, -40),
                NodeSpec(no, "save_result", "Dropped", {"name": "Dropped"}, 400, 80),
            ],
            [EdgeSpec(start, check, "out"), EdgeSpec(check, yes, "true"), EdgeSpec(check, no, "false")],
        ),
        text=text,
    )


def _exists(field: str):
    start, check, yes, no = _id(), _id(), _id(), _id()
    return _run(
        (
            [
                NodeSpec(start, "manual_trigger", "Start", {}, 0, 0),
                NodeSpec(check, "field_exists", "Exists", {"field": field}, 200, 0),
                NodeSpec(yes, "save_result", "Kept", {"name": "Kept"}, 400, -40),
                NodeSpec(no, "save_result", "Dropped", {"name": "Dropped"}, 400, 80),
            ],
            [EdgeSpec(start, check, "out"), EdgeSpec(check, yes, "true"), EdgeSpec(check, no, "false")],
        ),
        text="hello",
    )


def _line(*items):
    ids = [_id() for _ in items]
    nodes = [NodeSpec(ids[index], kind, label, config, index * 200, 0) for index, (kind, label, config) in enumerate(items)]
    edges = [EdgeSpec(ids[index], ids[index + 1], "out") for index in range(len(ids) - 1)]
    return nodes, edges


def _run(graph, **kwargs):
    nodes, edges = graph
    def fail(_prompt):
        raise AssertionError("The model should not be called.")

    return execute_graph(
        nodes,
        edges,
        text=kwargs.get("text", ""),
        document_id=kwargs.get("document_id"),
        dataset_id=kwargs.get("dataset_id"),
        load_document=kwargs.get("load_document", lambda _value: None),
        load_dataset=kwargs.get("load_dataset", lambda _value: None),
        complete_ai=kwargs.get("complete", fail),
        clock=kwargs.get("clock"),
        max_seconds=kwargs.get("max_seconds", 20),
    )


def _ai(payload: str, calls: list):
    def complete(prompt: str) -> AiText:
        calls.append(prompt)
        return AiText(payload, "gemini", "gemini-flash-lite-latest")
    return complete


def _step(result, label: str):
    return next(step for step in result.steps if step.node_label == label)


def _id() -> str:
    return str(uuid.uuid4())


def _input(node_id, node_type, label, config=None, x=0):
    return SimpleNamespace(id=node_id, node_type=node_type, label=label, config=config or {}, position_x=x, position_y=0)


def _edge(source, target, handle="out"):
    return SimpleNamespace(id=None, source_node_id=source, target_node_id=target, source_handle=handle, target_handle=None)


class _Boom:
    def generate(self, *_args, **_kwargs):
        raise AssertionError("The model should not be called.")


class _SummaryManager:
    def generate(self, request, **kwargs):
        assert kwargs["feature"] == "workflow"
        assert "A note about revenue" in request.prompt
        return GenerationOutcome(
            response=ProviderResponse("gemini", "gemini-flash-lite-latest", '{"summary": "Noted."}', TokenUsage(3, 2, "estimated"), 4),
            fallback_from=None,
        )


class MemoryWorkflows:
    def __init__(self):
        self.workflows = {}
        self.nodes = {}
        self.edges = {}
        self.runs = {}
        self.documents = {}
        self.loaded_orgs = []

    def get_workflow(self, organization_id, workflow_id):
        workflow = self.workflows.get(workflow_id)
        if workflow is None or workflow.organization_id != organization_id:
            return None
        return workflow

    def list_nodes(self, organization_id, workflow_id):
        return [node for node in self.nodes.get(workflow_id, []) if node.organization_id == organization_id]

    def list_edges(self, organization_id, workflow_id):
        return [edge for edge in self.edges.get(workflow_id, []) if edge.organization_id == organization_id]

    def insert_workflow(self, *, organization_id, user_id, name, description, status, nodes, edges):
        now = datetime.now(timezone.utc)
        workflow = Workflow(
            id=uuid.uuid4(),
            organization_id=organization_id,
            created_by=user_id,
            name=name,
            description=description,
            status=WorkflowStatus(status),
            created_at=now,
            updated_at=now,
        )
        self.workflows[workflow.id] = workflow
        self._store(workflow, nodes, edges)
        return workflow

    def update_graph(self, workflow, *, name, description, status, nodes, edges):
        workflow.name = name
        workflow.description = description
        workflow.status = WorkflowStatus(status)
        workflow.updated_at = datetime.now(timezone.utc)
        self._store(workflow, nodes, edges)

    def save_run(self, workflow, user_id, result):
        execution = WorkflowExecution(
            id=uuid.uuid4(),
            workflow_id=workflow.id,
            organization_id=workflow.organization_id,
            status=ExecutionStatus(result.status),
            trigger_type=result.trigger_type,
            started_at=result.started_at,
            finished_at=result.finished_at,
            error_message=result.error_message,
            triggered_by=user_id,
            created_at=result.started_at,
        )
        steps = []
        for record in result.steps:
            steps.append(
                WorkflowExecutionStep(
                    id=uuid.uuid4(),
                    execution_id=execution.id,
                    node_id=uuid.UUID(record.node_id),
                    node_type=record.node_type,
                    node_label=record.node_label,
                    organization_id=workflow.organization_id,
                    status=ExecutionStatus(record.status),
                    input_json=record.input_json,
                    output_json=record.output_json,
                    error_message=record.error_message,
                    started_at=record.started_at,
                    finished_at=record.finished_at,
                )
            )
        self.runs[execution.id] = (execution, steps)
        return execution, steps

    def get_run(self, organization_id, execution_id):
        found = self.runs.get(execution_id)
        if found is None or found[0].organization_id != organization_id:
            return None
        execution, steps = found
        workflow = self.workflows.get(execution.workflow_id)
        return execution, workflow.name if workflow else "", steps

    def load_document(self, organization_id, document_id):
        self.loaded_orgs.append(organization_id)
        return self.documents.get((organization_id, document_id))

    def load_dataset(self, organization_id, dataset_id):
        return None

    def apply_status(self, workflow, status):
        if status in {"draft", "active", "paused"}:
            workflow.status = WorkflowStatus(status)

    def _store(self, workflow, nodes, edges):
        self.nodes[workflow.id] = [
            WorkflowNode(
                id=uuid.UUID(spec.id),
                workflow_id=workflow.id,
                organization_id=workflow.organization_id,
                node_type=spec.node_type,
                label=spec.label,
                position_x=spec.position_x,
                position_y=spec.position_y,
                config=dict(spec.config),
            )
            for spec in nodes
        ]
        self.edges[workflow.id] = [
            WorkflowEdge(
                id=uuid.uuid4(),
                workflow_id=workflow.id,
                organization_id=workflow.organization_id,
                source_node_id=uuid.UUID(spec.source),
                target_node_id=uuid.UUID(spec.target),
                source_handle=spec.source_handle,
                target_handle=spec.target_handle,
            )
            for spec in edges
        ]
