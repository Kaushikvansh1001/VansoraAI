"""Import every model so Alembic and create_all see the full schema."""

from app.models.analytics import Dataset, DatasetAnalysis
from app.models.base import Base
from app.models.identity import LocalCredential, Organization, OrganizationMember, Profile
from app.models.knowledge import Conversation, Document, DocumentChunk, Message
from app.models.operations import AiFeedback, AiProvider, AiUsageLog, AuditLog, Job
from app.models.support import OutboxMessage, SupportMessage, SupportTicket
from app.models.workflows import (
    Workflow,
    WorkflowEdge,
    WorkflowExecution,
    WorkflowExecutionStep,
    WorkflowNode,
)

__all__ = [
    "AiFeedback",
    "AiProvider",
    "AiUsageLog",
    "AuditLog",
    "Base",
    "Conversation",
    "Dataset",
    "DatasetAnalysis",
    "Document",
    "DocumentChunk",
    "Job",
    "LocalCredential",
    "Message",
    "Organization",
    "OrganizationMember",
    "OutboxMessage",
    "Profile",
    "SupportMessage",
    "SupportTicket",
    "Workflow",
    "WorkflowEdge",
    "WorkflowExecution",
    "WorkflowExecutionStep",
    "WorkflowNode",
]
