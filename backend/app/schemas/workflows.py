import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class NodeInput(BaseModel):
    id: uuid.UUID
    node_type: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=160)
    position_x: float = 0
    position_y: float = 0
    config: dict = Field(default_factory=dict)


class EdgeInput(BaseModel):
    id: uuid.UUID | None = None
    source_node_id: uuid.UUID
    target_node_id: uuid.UUID
    source_handle: str | None = None
    target_handle: str | None = None


class WorkflowWrite(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    status: Literal["draft", "active", "paused"] = "draft"
    nodes: list[NodeInput] = Field(min_length=1, max_length=24)
    edges: list[EdgeInput] = Field(default_factory=list, max_length=40)


class TemplateRequest(BaseModel):
    template_id: str = Field(min_length=1, max_length=64)


class RunRequest(BaseModel):
    text: str = Field(default="", max_length=8000)
    document_id: uuid.UUID | None = None
    dataset_id: uuid.UUID | None = None


class NodeResponse(BaseModel):
    id: uuid.UUID
    node_type: str
    label: str
    position_x: float
    position_y: float
    config: dict


class EdgeResponse(BaseModel):
    id: uuid.UUID
    source_node_id: uuid.UUID
    target_node_id: uuid.UUID
    source_handle: str | None
    target_handle: str | None


class WorkflowResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    nodes: list[NodeResponse]
    edges: list[EdgeResponse]


class WorkflowCard(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    status: str
    updated_at: datetime
    node_count: int


class StepResponse(BaseModel):
    id: uuid.UUID
    node_id: uuid.UUID | None
    node_type: str | None
    node_label: str | None
    status: str
    input_json: dict | None
    output_json: dict | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None


class ExecutionResponse(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_name: str
    status: str
    trigger_type: str
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    created_at: datetime
    steps: list[StepResponse] = Field(default_factory=list)


class TemplateCard(BaseModel):
    id: str
    name: str
    description: str


class WorkflowSummary(BaseModel):
    total: int
    active: int
    draft: int
    paused: int
    successful_executions: int
    failed_executions: int
    recent_executions: list[ExecutionResponse]
    templates: list[TemplateCard]
