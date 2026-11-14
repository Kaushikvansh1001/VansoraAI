import uuid

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.errors import AppError
from app.db.session import get_db
from app.models.identity import Profile
from app.schemas.ai import (
    FallbackEventResponse,
    ProviderStatusResponse,
    TestGenerationRequest,
    TestGenerationResponse,
    UsageResponse,
)
from app.services.ai.admin import AiAdminService
from app.services.organizations import OrganizationService

router = APIRouter(prefix="/ai", tags=["ai"])


def _organization_id(x_organization_id: str | None = Header(default=None)) -> uuid.UUID:
    if not x_organization_id:
        raise AppError("organization_required", "Choose an organization before continuing.", 400)
    try:
        return uuid.UUID(x_organization_id)
    except ValueError as exc:
        raise AppError("invalid_organization", "The organization id is not valid.", 400) from exc


def _admin(
    organization_id: uuid.UUID = Depends(_organization_id),
    user: Profile = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> tuple[uuid.UUID, Profile, Session]:
    OrganizationService(db).require_admin(user, organization_id)
    return organization_id, user, db


@router.get("/providers", response_model=ProviderStatusResponse)
def provider_status(context: tuple = Depends(_admin)) -> ProviderStatusResponse:
    _organization_id, _user, db = context
    return AiAdminService(db).provider_status()


@router.get("/health", response_model=ProviderStatusResponse)
def provider_health(context: tuple = Depends(_admin)) -> ProviderStatusResponse:
    _organization_id, _user, db = context
    return AiAdminService(db).provider_status()


@router.get("/usage", response_model=UsageResponse)
def usage(context: tuple = Depends(_admin)) -> UsageResponse:
    organization_id, _user, db = context
    return AiAdminService(db).usage_summary(organization_id)


@router.get("/fallbacks", response_model=list[FallbackEventResponse])
def fallbacks(context: tuple = Depends(_admin)) -> list[FallbackEventResponse]:
    organization_id, _user, db = context
    return AiAdminService(db).fallback_history(organization_id)


@router.post("/test", response_model=TestGenerationResponse)
def test_generation(body: TestGenerationRequest, context: tuple = Depends(_admin)) -> TestGenerationResponse:
    organization_id, user, db = context
    return AiAdminService(db).test_generation(organization_id, user.id, body.prompt)
