import uuid

from sqlalchemy.orm import Session

from app.models.identity import Profile
from app.repositories.dashboard import DashboardRepository
from app.schemas.dashboard import ActivityItem, ConversationItem, DashboardResponse, DocumentStatusCounts
from app.services.organizations import OrganizationService


class DashboardService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.organizations = OrganizationService(db)

    def get_dashboard(self, user: Profile, organization_id: uuid.UUID) -> DashboardResponse:
        self.organizations.require_context(user, organization_id)
        stats = DashboardRepository(self.db, organization_id)
        input_tokens, output_tokens, estimated_cost = stats.token_totals()
        status_counts = stats.document_status_counts()
        return DashboardResponse(
            documents=stats.document_count(),
            conversations=stats.conversation_count(),
            queries=stats.query_count(),
            workflows=stats.workflow_count(),
            successful_executions=stats.successful_execution_count(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=f"{estimated_cost:.6f}",
            document_status=DocumentStatusCounts(**status_counts),
            recent_activity=[
                ActivityItem(action=item.action, resource_type=item.resource_type, created_at=item.created_at)
                for item in stats.recent_activity()
            ],
            recent_conversations=[
                ConversationItem(id=item.id, title=item.title, created_at=item.created_at)
                for item in stats.recent_conversations()
            ],
        )
