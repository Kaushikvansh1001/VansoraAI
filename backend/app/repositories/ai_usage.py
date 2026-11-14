import uuid
from decimal import Decimal

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.models.operations import AiUsageLog


class AiUsageRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def summary(self, organization_id: uuid.UUID) -> list[dict]:
        failed = case((AiUsageLog.status != "succeeded", 1), else_=0)
        succeeded = case((AiUsageLog.status == "succeeded", 1), else_=0)
        rows = self.db.execute(
            select(
                AiUsageLog.provider,
                func.coalesce(func.sum(succeeded), 0),
                func.coalesce(func.sum(failed), 0),
                func.coalesce(func.sum(AiUsageLog.input_tokens), 0),
                func.coalesce(func.sum(AiUsageLog.output_tokens), 0),
                func.coalesce(func.sum(AiUsageLog.estimated_cost_usd), 0),
            )
            .where(AiUsageLog.organization_id == organization_id)
            .group_by(AiUsageLog.provider)
            .order_by(AiUsageLog.provider)
        ).all()
        return [
            {
                "provider": provider,
                "requests_succeeded": int(ok or 0),
                "requests_failed": int(bad or 0),
                "input_tokens": int(input_tokens or 0),
                "output_tokens": int(output_tokens or 0),
                "estimated_cost_usd": Decimal(cost or 0),
            }
            for provider, ok, bad, input_tokens, output_tokens, cost in rows
        ]

    def fallback_history(self, organization_id: uuid.UUID, limit: int = 20) -> list[AiUsageLog]:
        return list(
            self.db.scalars(
                select(AiUsageLog)
                .where(
                    AiUsageLog.organization_id == organization_id,
                    or_(AiUsageLog.fallback_from.is_not(None), AiUsageLog.status == "failed"),
                )
                .order_by(AiUsageLog.created_at.desc())
                .limit(limit)
            ).all()
        )
