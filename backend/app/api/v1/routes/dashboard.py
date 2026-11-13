import uuid

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.errors import AppError
from app.db.session import get_db
from app.models.identity import Profile
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _organization_id(x_organization_id: str | None = Header(default=None)) -> uuid.UUID:
    if not x_organization_id:
        raise AppError("organization_required", "Choose an organization before continuing.", 400)
    try:
        return uuid.UUID(x_organization_id)
    except ValueError as exc:
        raise AppError("invalid_organization", "The organization id is not valid.", 400) from exc


@router.get("", response_model=DashboardResponse)
def get_dashboard(
    organization_id: uuid.UUID = Depends(_organization_id),
    user: Profile = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardResponse:
    return DashboardService(db).get_dashboard(user, organization_id)
