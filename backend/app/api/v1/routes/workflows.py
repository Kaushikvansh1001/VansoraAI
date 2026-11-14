import uuid

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.errors import AppError
from app.core.security import generation_rate_limiter
from app.db.session import get_db
from app.models.identity import Profile
from app.schemas.workflows import (
    ExecutionResponse,
    RunRequest,
    StepResponse,
    TemplateCard,
    TemplateRequest,
    WorkflowCard,
    WorkflowResponse,
    WorkflowSummary,
    WorkflowWrite,
    EdgeResponse,
    NodeResponse,
)
from app.services.organizations import OrganizationService
from app.services.workflows.service import WorkflowService

router = APIRouter(prefix="/workflows", tags=["workflows"])


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


def _duration(start, end) -> int | None:
    if start is None or end is None:
        return None
    return max(0, int((end - start).total_seconds() * 1000))


def _workflow_response(workflow, nodes, edges) -> WorkflowResponse:
    return WorkflowResponse(
        id=workflow.id,
        name=workflow.name,
        description=workflow.description,
        status=_value(workflow.status),
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
        nodes=[
            NodeResponse(
                id=node.id,
                node_type=node.node_type,
                label=node.label,
                position_x=node.position_x,
                position_y=node.position_y,
                config=node.config or {},
            )
            for node in nodes
        ],
        edges=[
            EdgeResponse(
                id=edge.id,
                source_node_id=edge.source_node_id,
                target_node_id=edge.target_node_id,
                source_handle=edge.source_handle,
                target_handle=edge.target_handle,
            )
            for edge in edges
        ],
    )


def _step_response(step) -> StepResponse:
    return StepResponse(
        id=step.id,
        node_id=step.node_id,
        node_type=step.node_type,
        node_label=step.node_label,
        status=_value(step.status),
        input_json=step.input_json,
        output_json=step.output_json,
        error_message=step.error_message,
        started_at=step.started_at,
        finished_at=step.finished_at,
        duration_ms=_duration(step.started_at, step.finished_at),
    )


def _execution_response(execution, workflow_name: str, steps=None) -> ExecutionResponse:
    return ExecutionResponse(
        id=execution.id,
        workflow_id=execution.workflow_id,
        workflow_name=workflow_name,
        status=_value(execution.status),
        trigger_type=execution.trigger_type,
        error_message=execution.error_message,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
        duration_ms=_duration(execution.started_at, execution.finished_at),
        created_at=execution.created_at,
        steps=[_step_response(step) for step in steps] if steps is not None else [],
    )


@router.get("/summary", response_model=WorkflowSummary)
def summary(context: tuple = Depends(_member)) -> WorkflowSummary:
    organization_id, _user, db = context
    counts, recent, templates = WorkflowService(db).summary(organization_id)
    return WorkflowSummary(
        **counts,
        recent_executions=[_execution_response(execution, name) for execution, name in recent],
        templates=[TemplateCard(**item) for item in templates],
    )


@router.get("/executions/{execution_id}", response_model=ExecutionResponse)
def get_execution(execution_id: uuid.UUID, context: tuple = Depends(_member)) -> ExecutionResponse:
    organization_id, _user, db = context
    execution, name, steps = WorkflowService(db).get_run(organization_id, execution_id)
    return _execution_response(execution, name, steps)


@router.post("/from-template", response_model=WorkflowResponse)
def create_from_template(body: TemplateRequest, context: tuple = Depends(_member)) -> WorkflowResponse:
    organization_id, user, db = context
    workflow, nodes, edges = WorkflowService(db).create_from_template(
        organization_id=organization_id,
        user_id=user.id,
        template_id=body.template_id,
    )
    return _workflow_response(workflow, nodes, edges)


@router.get("", response_model=list[WorkflowCard])
def list_workflows(context: tuple = Depends(_member)) -> list[WorkflowCard]:
    organization_id, _user, db = context
    return [
        WorkflowCard(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            status=_value(workflow.status),
            updated_at=workflow.updated_at,
            node_count=int(count or 0),
        )
        for workflow, count in WorkflowService(db).list_workflows(organization_id)
    ]


@router.post("", response_model=WorkflowResponse)
def create_workflow(body: WorkflowWrite, context: tuple = Depends(_member)) -> WorkflowResponse:
    organization_id, user, db = context
    workflow, nodes, edges = WorkflowService(db).create(
        organization_id=organization_id,
        user_id=user.id,
        name=body.name,
        description=body.description,
        status=body.status,
        nodes=body.nodes,
        edges=body.edges,
    )
    return _workflow_response(workflow, nodes, edges)


@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(workflow_id: uuid.UUID, context: tuple = Depends(_member)) -> WorkflowResponse:
    organization_id, _user, db = context
    return _workflow_response(*WorkflowService(db).get(organization_id, workflow_id))


@router.patch("/{workflow_id}", response_model=WorkflowResponse)
def update_workflow(workflow_id: uuid.UUID, body: WorkflowWrite, context: tuple = Depends(_member)) -> WorkflowResponse:
    organization_id, _user, db = context
    workflow, nodes, edges = WorkflowService(db).update(
        organization_id=organization_id,
        workflow_id=workflow_id,
        name=body.name,
        description=body.description,
        status=body.status,
        nodes=body.nodes,
        edges=body.edges,
    )
    return _workflow_response(workflow, nodes, edges)


@router.delete("/{workflow_id}", status_code=204)
def delete_workflow(workflow_id: uuid.UUID, context: tuple = Depends(_member)) -> Response:
    organization_id, user, db = context
    WorkflowService(db).delete(organization_id, workflow_id, user.id)
    return Response(status_code=204)


@router.post("/{workflow_id}/run", response_model=ExecutionResponse)
def run_workflow(workflow_id: uuid.UUID, body: RunRequest, context: tuple = Depends(_member)) -> ExecutionResponse:
    organization_id, user, db = context
    generation_rate_limiter.check(str(user.id))
    execution, name, steps = WorkflowService(db).run(
        organization_id=organization_id,
        user_id=user.id,
        workflow_id=workflow_id,
        text=body.text,
        document_id=body.document_id,
        dataset_id=body.dataset_id,
    )
    return _execution_response(execution, name, steps)


@router.get("/{workflow_id}/executions", response_model=list[ExecutionResponse])
def list_executions(workflow_id: uuid.UUID, context: tuple = Depends(_member)) -> list[ExecutionResponse]:
    organization_id, _user, db = context
    workflow, runs = WorkflowService(db).list_runs(organization_id, workflow_id)
    return [_execution_response(execution, workflow.name) for execution in runs]
