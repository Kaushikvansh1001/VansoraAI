import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.identity import Profile
from app.schemas.organizations import (
    AddMemberRequest,
    CreateOrganizationRequest,
    MemberResponse,
    OrganizationResponse,
    UpdateMemberRequest,
    UpdateOrganizationRequest,
)
from app.services.organizations import OrganizationService

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("", response_model=list[OrganizationResponse])
def list_organizations(
    user: Profile = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[OrganizationResponse]:
    return OrganizationService(db).list_for_user(user)


@router.post("", response_model=OrganizationResponse, status_code=201)
def create_organization(
    body: CreateOrganizationRequest,
    request: Request,
    user: Profile = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    return OrganizationService(db).create(user, body.name, _ip(request))


@router.get("/{organization_id}", response_model=OrganizationResponse)
def get_organization(
    organization_id: uuid.UUID,
    user: Profile = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    return OrganizationService(db).get_for_member(user, organization_id)


@router.patch("/{organization_id}", response_model=OrganizationResponse)
def update_organization(
    organization_id: uuid.UUID,
    body: UpdateOrganizationRequest,
    request: Request,
    user: Profile = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    return OrganizationService(db).update(user, organization_id, body.name, _ip(request))


@router.get("/{organization_id}/members", response_model=list[MemberResponse])
def list_members(
    organization_id: uuid.UUID,
    user: Profile = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MemberResponse]:
    return OrganizationService(db).list_members(user, organization_id)


@router.post("/{organization_id}/members", response_model=MemberResponse, status_code=201)
def add_member(
    organization_id: uuid.UUID,
    body: AddMemberRequest,
    request: Request,
    user: Profile = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MemberResponse:
    return OrganizationService(db).add_member(user, organization_id, body.email, body.role, _ip(request))


@router.patch("/{organization_id}/members/{member_id}", response_model=MemberResponse)
def update_member(
    organization_id: uuid.UUID,
    member_id: uuid.UUID,
    body: UpdateMemberRequest,
    request: Request,
    user: Profile = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MemberResponse:
    return OrganizationService(db).update_member(user, organization_id, member_id, body.role, _ip(request))


@router.delete("/{organization_id}/members/{member_id}", status_code=204)
def remove_member(
    organization_id: uuid.UUID,
    member_id: uuid.UUID,
    request: Request,
    user: Profile = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    OrganizationService(db).remove_member(user, organization_id, member_id, _ip(request))
    return Response(status_code=204)
