import uuid

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.workflows import Workflow
from app.services.ai.models import GenerationRequest
from app.services.audit import record_audit
from app.services.workflows.catalog import build_template, list_templates
from app.services.workflows.engine import AiText, execute_graph
from app.services.workflows.graph import EdgeSpec, NodeSpec, prepare_graph
from app.repositories.workflows import WorkflowRepository


class WorkflowService:
    def __init__(self, db: Session | None = None, manager=None, repository=None, clock=None) -> None:
        self.db = db
        self.manager = manager
        self.repo = repository or WorkflowRepository(db)
        self.clock = clock

    def summary(self, organization_id: uuid.UUID):
        return self.repo.counts(organization_id), self.repo.recent_runs(organization_id), list_templates()

    def list_workflows(self, organization_id: uuid.UUID):
        return self.repo.list_workflows(organization_id)

    def get(self, organization_id: uuid.UUID, workflow_id: uuid.UUID):
        workflow = self.repo.get_workflow(organization_id, workflow_id)
        if workflow is None:
            raise AppError("not_found", "That workflow does not exist.", 404)
        return (
            workflow,
            self.repo.list_nodes(organization_id, workflow_id),
            self.repo.list_edges(organization_id, workflow_id),
        )

    def create(self, *, organization_id: uuid.UUID, user_id: uuid.UUID, name: str, description: str | None, status: str, nodes, edges):
        prepared = prepare_graph(*_incoming(nodes, edges))
        workflow = self.repo.insert_workflow(
            organization_id=organization_id,
            user_id=user_id,
            name=_name(name),
            description=_description(description),
            status=status,
            nodes=prepared.nodes,
            edges=prepared.edges,
        )
        self._audit("workflow.created", "workflow", user_id, organization_id, workflow.id, {"status": status})
        return self.get(organization_id, workflow.id)

    def create_from_template(self, *, organization_id: uuid.UUID, user_id: uuid.UUID, template_id: str):
        name, description, nodes, edges = build_template(template_id)
        prepared = prepare_graph(nodes, edges)
        workflow = self.repo.insert_workflow(
            organization_id=organization_id,
            user_id=user_id,
            name=name,
            description=description,
            status="draft",
            nodes=prepared.nodes,
            edges=prepared.edges,
        )
        self._audit("workflow.created", "workflow", user_id, organization_id, workflow.id, {"template": template_id})
        return self.get(organization_id, workflow.id)

    def update(self, *, organization_id: uuid.UUID, workflow_id: uuid.UUID, name: str, description: str | None, status: str, nodes, edges):
        workflow, _, _ = self.get(organization_id, workflow_id)
        prepared = prepare_graph(*_incoming(nodes, edges))
        self.repo.update_graph(
            workflow,
            name=_name(name),
            description=_description(description),
            status=status,
            nodes=prepared.nodes,
            edges=prepared.edges,
        )
        return self.get(organization_id, workflow_id)

    def delete(self, organization_id: uuid.UUID, workflow_id: uuid.UUID, user_id: uuid.UUID) -> None:
        workflow, _, _ = self.get(organization_id, workflow_id)
        self.repo.delete_workflow(workflow)
        self._audit("workflow.deleted", "workflow", user_id, organization_id, workflow_id, {})

    def run(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        workflow_id: uuid.UUID,
        text: str,
        document_id: uuid.UUID | None,
        dataset_id: uuid.UUID | None,
    ):
        workflow = self.repo.get_workflow(organization_id, workflow_id)
        if workflow is None:
            raise AppError("not_found", "That workflow does not exist.", 404)
        if _status(workflow) == "paused":
            raise AppError("workflow_paused", "This workflow is paused.", 409)
        specs, links = _incoming(
            self.repo.list_nodes(organization_id, workflow_id),
            self.repo.list_edges(organization_id, workflow_id),
        )
        result = execute_graph(
            specs,
            links,
            text=text or "",
            document_id=str(document_id) if document_id else None,
            dataset_id=str(dataset_id) if dataset_id else None,
            load_document=lambda value: self._load(self.repo.load_document, organization_id, value),
            load_dataset=lambda value: self._load(self.repo.load_dataset, organization_id, value),
            complete_ai=self._complete(organization_id, user_id),
            clock=self.clock,
        )
        execution, steps = self.repo.save_run(workflow, user_id, result)
        for step in result.steps:
            if step.status == "succeeded" and step.node_type == "update_status" and step.output_json:
                self.repo.apply_status(workflow, str(step.output_json.get("status") or ""))
        self._audit(
            "workflow.ran",
            "workflow_execution",
            user_id,
            organization_id,
            execution.id,
            {"status": result.status, "trigger_type": "manual"},
        )
        return execution, workflow.name, steps

    def list_runs(self, organization_id: uuid.UUID, workflow_id: uuid.UUID):
        workflow, _, _ = self.get(organization_id, workflow_id)
        return workflow, self.repo.list_runs(organization_id, workflow_id)

    def get_run(self, organization_id: uuid.UUID, execution_id: uuid.UUID):
        found = self.repo.get_run(organization_id, execution_id)
        if found is None:
            raise AppError("not_found", "That run does not exist.", 404)
        return found

    def _complete(self, organization_id: uuid.UUID, user_id: uuid.UUID):
        def complete(prompt: str) -> AiText:
            outcome = self._manager().generate(
                GenerationRequest(prompt=prompt),
                organization_id=organization_id,
                user_id=user_id,
                feature="workflow",
            )
            return AiText(text=outcome.response.text, provider=outcome.response.provider, model=outcome.response.model)
        return complete

    def _manager(self):
        if self.manager is None:
            from app.core.config import get_settings
            from app.services.ai.provider_manager import ProviderManager
            from app.services.ai.usage_tracker import UsageTracker

            self.manager = ProviderManager(get_settings(), sink=UsageTracker(self.db))
        return self.manager

    def _load(self, method, organization_id: uuid.UUID, value: str):
        try:
            parsed = uuid.UUID(value)
        except ValueError:
            return None
        return method(organization_id, parsed)

    def _audit(self, action: str, resource_type: str, user_id, organization_id, resource_id, details: dict) -> None:
        if self.db is None:
            return
        record_audit(
            self.db,
            action=action,
            resource_type=resource_type,
            actor_id=user_id,
            organization_id=organization_id,
            resource_id=resource_id,
            details=details,
        )


def _incoming(nodes, edges) -> tuple[list[NodeSpec], list[EdgeSpec]]:
    specs = [
        NodeSpec(
            id=str(node.id),
            node_type=node.node_type,
            label=node.label,
            config=dict(node.config or {}),
            position_x=float(node.position_x or 0),
            position_y=float(node.position_y or 0),
        )
        for node in nodes
    ]
    links = [
        EdgeSpec(
            source=str(edge.source_node_id),
            target=str(edge.target_node_id),
            source_handle=edge.source_handle or "out",
            id=str(edge.id) if getattr(edge, "id", None) else None,
            target_handle=edge.target_handle,
        )
        for edge in edges
    ]
    return specs, links


def _name(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned or len(cleaned) > 160:
        raise AppError("invalid_workflow", "Give the workflow a name of 160 characters or fewer.", 400)
    return cleaned


def _description(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    if len(cleaned) > 2000:
        raise AppError("invalid_workflow", "The description is too long.", 400)
    return cleaned or None


def _status(workflow: Workflow) -> str:
    status = workflow.status
    return status.value if hasattr(status, "value") else str(status)
