import uuid

from sqlalchemy.orm import Session

from app.models.operations import AuditLog


def record_audit(
    db: Session,
    *,
    action: str,
    resource_type: str,
    actor_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    resource_id: uuid.UUID | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_id=actor_id,
            organization_id=organization_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            ip_address=ip_address,
        )
    )
