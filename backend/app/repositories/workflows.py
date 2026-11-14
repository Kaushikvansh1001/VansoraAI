import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.analytics import Dataset
from app.models.enums import DatasetStatus, DocumentStatus, ExecutionStatus, WorkflowStatus
from app.models.knowledge import Document, DocumentChunk
from app.models.workflows import Workflow, WorkflowEdge, WorkflowExecution, WorkflowExecutionStep, WorkflowNode
from app.services.workflows.engine import RunResult
from app.services.workflows.graph import EdgeSpec, NodeSpec
from app.services.workflows.sources import dataset_summary_text, join_document_text


def workflow_lookup(organization_id: uuid.UUID, workflow_id: uuid.UUID):
    return select(Workflow).where(Workflow.id == workflow_id, Workflow.organization_id == organization_id)


def document_lookup(organization_id: uuid.UUID, document_id: uuid.UUID):
    return select(Document).where(
        Document.id == document_id,
        Document.organization_id == organization_id,
        Document.status == DocumentStatus.ready,
    )


def execution_lookup(organization_id: uuid.UUID, execution_id: uuid.UUID):
    return select(WorkflowExecution).where(
        WorkflowExecution.id == execution_id,
        WorkflowExecution.organization_id == organization_id,
    )


class WorkflowRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def counts(self, organization_id: uuid.UUID) -> dict:
        workflow_rows = self.db.execute(
            select(Workflow.status, func.count()).where(Workflow.organization_id == organization_id).group_by(Workflow.status)
        ).all()
        execution_rows = self.db.execute(
            select(WorkflowExecution.status, func.count())
            .where(WorkflowExecution.organization_id == organization_id)
            .group_by(WorkflowExecution.status)
        ).all()
        workflows = {status.value: 0 for status in WorkflowStatus}
        executions = {status.value: 0 for status in ExecutionStatus}
        for status, count in workflow_rows:
            workflows[_value(status)] = int(count)
        for status, count in execution_rows:
            executions[_value(status)] = int(count)
        return {
            "total": sum(workflows.values()),
            "active": workflows["active"],
            "draft": workflows["draft"],
            "paused": workflows["paused"],
            "successful_executions": executions["succeeded"],
            "failed_executions": executions["failed"],
        }

    def list_workflows(self, organization_id: uuid.UUID) -> list[tuple[Workflow, int]]:
        node_count = (
            select(func.count(WorkflowNode.id))
            .where(WorkflowNode.workflow_id == Workflow.id, WorkflowNode.organization_id == organization_id)
            .correlate(Workflow)
            .scalar_subquery()
        )
        return list(
            self.db.execute(
                select(Workflow, node_count)
                .where(Workflow.organization_id == organization_id)
                .order_by(Workflow.updated_at.desc())
            ).all()
        )

    def get_workflow(self, organization_id: uuid.UUID, workflow_id: uuid.UUID) -> Workflow | None:
        return self.db.scalar(workflow_lookup(organization_id, workflow_id))

    def list_nodes(self, organization_id: uuid.UUID, workflow_id: uuid.UUID) -> list[WorkflowNode]:
        return list(
            self.db.scalars(
                select(WorkflowNode)
                .where(WorkflowNode.organization_id == organization_id, WorkflowNode.workflow_id == workflow_id)
                .order_by(WorkflowNode.position_x, WorkflowNode.position_y, WorkflowNode.label)
            ).all()
        )

    def list_edges(self, organization_id: uuid.UUID, workflow_id: uuid.UUID) -> list[WorkflowEdge]:
        return list(
            self.db.scalars(
                select(WorkflowEdge).where(
                    WorkflowEdge.organization_id == organization_id,
                    WorkflowEdge.workflow_id == workflow_id,
                )
            ).all()
        )

    def insert_workflow(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        description: str | None,
        status: str,
        nodes: list[NodeSpec],
        edges: list[EdgeSpec],
    ) -> Workflow:
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
        self.db.add(workflow)
        self.db.flush()
        self._insert_graph(workflow, nodes, edges)
        return workflow

    def update_graph(
        self,
        workflow: Workflow,
        *,
        name: str,
        description: str | None,
        status: str,
        nodes: list[NodeSpec],
        edges: list[EdgeSpec],
    ) -> None:
        self._snapshot_steps(workflow)
        self.db.execute(
            delete(WorkflowEdge).where(
                WorkflowEdge.workflow_id == workflow.id,
                WorkflowEdge.organization_id == workflow.organization_id,
            )
        )
        self.db.execute(
            delete(WorkflowNode).where(
                WorkflowNode.workflow_id == workflow.id,
                WorkflowNode.organization_id == workflow.organization_id,
            )
        )
        self.db.flush()
        workflow.name = name
        workflow.description = description
        workflow.status = WorkflowStatus(status)
        workflow.updated_at = datetime.now(timezone.utc)
        self._insert_graph(workflow, nodes, edges)

    def delete_workflow(self, workflow: Workflow) -> None:
        self.db.delete(workflow)
        self.db.flush()

    def save_run(self, workflow: Workflow, user_id: uuid.UUID, result: RunResult):
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
        self.db.add(execution)
        steps = []
        for record in result.steps:
            step = WorkflowExecutionStep(
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
            self.db.add(step)
            steps.append(step)
        self.db.flush()
        return execution, steps

    def list_runs(self, organization_id: uuid.UUID, workflow_id: uuid.UUID) -> list[WorkflowExecution]:
        return list(
            self.db.scalars(
                select(WorkflowExecution)
                .where(
                    WorkflowExecution.organization_id == organization_id,
                    WorkflowExecution.workflow_id == workflow_id,
                )
                .order_by(WorkflowExecution.created_at.desc())
            ).all()
        )

    def recent_runs(self, organization_id: uuid.UUID, limit: int = 8) -> list[tuple[WorkflowExecution, str]]:
        return list(
            self.db.execute(
                select(WorkflowExecution, Workflow.name)
                .join(Workflow, Workflow.id == WorkflowExecution.workflow_id)
                .where(
                    WorkflowExecution.organization_id == organization_id,
                    Workflow.organization_id == organization_id,
                )
                .order_by(WorkflowExecution.created_at.desc())
                .limit(limit)
            ).all()
        )

    def get_run(self, organization_id: uuid.UUID, execution_id: uuid.UUID):
        execution = self.db.scalar(execution_lookup(organization_id, execution_id))
        if execution is None:
            return None
        name = self.db.scalar(
            select(Workflow.name).where(
                Workflow.id == execution.workflow_id,
                Workflow.organization_id == organization_id,
            )
        )
        steps = list(
            self.db.scalars(
                select(WorkflowExecutionStep)
                .where(
                    WorkflowExecutionStep.execution_id == execution.id,
                    WorkflowExecutionStep.organization_id == organization_id,
                )
                .order_by(WorkflowExecutionStep.started_at)
            ).all()
        )
        return execution, name or "", steps

    def load_document(self, organization_id: uuid.UUID, document_id: uuid.UUID) -> dict | None:
        document = self.db.scalar(document_lookup(organization_id, document_id))
        if document is None:
            return None
        parts = list(
            self.db.scalars(
                select(DocumentChunk.content)
                .where(
                    DocumentChunk.document_id == document.id,
                    DocumentChunk.organization_id == organization_id,
                )
                .order_by(DocumentChunk.chunk_index)
            ).all()
        )
        return {"filename": document.filename, "text": join_document_text(parts)}

    def load_dataset(self, organization_id: uuid.UUID, dataset_id: uuid.UUID) -> dict | None:
        dataset = self.db.scalar(
            select(Dataset).where(
                Dataset.id == dataset_id,
                Dataset.organization_id == organization_id,
                Dataset.status == DatasetStatus.ready,
            )
        )
        if dataset is None:
            return None
        return {
            "name": dataset.name,
            "text": dataset_summary_text(dataset.name, dataset.row_count, dataset.column_count, dataset.schema_json or {}),
        }

    def apply_status(self, workflow: Workflow, status: str) -> None:
        if status not in {"draft", "active", "paused"}:
            return
        workflow.status = WorkflowStatus(status)
        workflow.updated_at = datetime.now(timezone.utc)

    def _insert_graph(self, workflow: Workflow, nodes: list[NodeSpec], edges: list[EdgeSpec]) -> None:
        for spec in nodes:
            self.db.add(
                WorkflowNode(
                    id=uuid.UUID(spec.id),
                    workflow_id=workflow.id,
                    organization_id=workflow.organization_id,
                    node_type=spec.node_type,
                    label=spec.label,
                    position_x=spec.position_x,
                    position_y=spec.position_y,
                    config=spec.config,
                )
            )
        self.db.flush()
        for spec in edges:
            self.db.add(
                WorkflowEdge(
                    id=uuid.UUID(spec.id) if spec.id else uuid.uuid4(),
                    workflow_id=workflow.id,
                    organization_id=workflow.organization_id,
                    source_node_id=uuid.UUID(spec.source),
                    target_node_id=uuid.UUID(spec.target),
                    source_handle=spec.source_handle,
                    target_handle=spec.target_handle,
                )
            )
        self.db.flush()

    def _snapshot_steps(self, workflow: Workflow) -> None:
        rows = self.db.execute(
            select(WorkflowExecutionStep, WorkflowNode.node_type, WorkflowNode.label)
            .join(WorkflowExecution, WorkflowExecution.id == WorkflowExecutionStep.execution_id)
            .outerjoin(WorkflowNode, WorkflowNode.id == WorkflowExecutionStep.node_id)
            .where(
                WorkflowExecution.workflow_id == workflow.id,
                WorkflowExecution.organization_id == workflow.organization_id,
            )
        ).all()
        for step, node_type, label in rows:
            if step.node_type is None and node_type:
                step.node_type = node_type
                step.node_label = label


def _value(status) -> str:
    return status.value if hasattr(status, "value") else str(status)
