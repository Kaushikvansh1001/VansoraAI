import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import DocumentStatus, ExecutionStatus, MessageRole
from app.models.knowledge import Conversation, Document, Message
from app.models.operations import AiUsageLog, AuditLog
from app.models.workflows import Workflow, WorkflowExecution


class DashboardRepository:
    def __init__(self, db: Session, organization_id: uuid.UUID) -> None:
        self.db = db
        self.organization_id = organization_id

    def _count(self, model) -> int:
        value = self.db.scalar(
            select(func.count()).select_from(model).where(model.organization_id == self.organization_id)
        )
        return int(value or 0)

    def document_count(self) -> int:
        return self._count(Document)

    def conversation_count(self) -> int:
        return self._count(Conversation)

    def query_count(self) -> int:
        value = self.db.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.organization_id == self.organization_id,
                Message.role == MessageRole.user,
            )
        )
        return int(value or 0)

    def workflow_count(self) -> int:
        return self._count(Workflow)

    def successful_execution_count(self) -> int:
        value = self.db.scalar(
            select(func.count())
            .select_from(WorkflowExecution)
            .where(
                WorkflowExecution.organization_id == self.organization_id,
                WorkflowExecution.status == ExecutionStatus.succeeded,
            )
        )
        return int(value or 0)

    def document_status_counts(self) -> dict[str, int]:
        rows = self.db.execute(
            select(Document.status, func.count())
            .where(Document.organization_id == self.organization_id)
            .group_by(Document.status)
        ).all()
        counts = {status.value: 0 for status in DocumentStatus}
        for status, count in rows:
            counts[status.value] = int(count)
        return counts

    def token_totals(self) -> tuple[int, int, Decimal]:
        row = self.db.execute(
            select(
                func.coalesce(func.sum(AiUsageLog.input_tokens), 0),
                func.coalesce(func.sum(AiUsageLog.output_tokens), 0),
                func.coalesce(func.sum(AiUsageLog.estimated_cost_usd), 0),
            ).where(AiUsageLog.organization_id == self.organization_id)
        ).one()
        return int(row[0]), int(row[1]), Decimal(row[2])

    def recent_activity(self) -> list[AuditLog]:
        return list(
            self.db.scalars(
                select(AuditLog)
                .where(AuditLog.organization_id == self.organization_id)
                .order_by(AuditLog.created_at.desc())
                .limit(8)
            ).all()
        )

    def recent_conversations(self) -> list[Conversation]:
        return list(
            self.db.scalars(
                select(Conversation)
                .where(Conversation.organization_id == self.organization_id)
                .order_by(Conversation.created_at.desc())
                .limit(5)
            ).all()
        )
