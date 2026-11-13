import uuid
from collections.abc import Generator
from dataclasses import dataclass

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db.session import get_db, set_current_user
from app.models.identity import Organization, OrganizationMember, Profile
from app.services.auth import AuthService
from app.services.organizations import OrganizationService

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class OrgContext:
    user: Profile
    organization: Organization
    member: OrganizationMember


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Profile:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError("unauthorized", "Sign in to continue.", 401)
    claims = decode_access_token(credentials.credentials)
    try:
        user_id = uuid.UUID(str(claims.get("sub")))
    except (TypeError, ValueError) as exc:
        raise AppError("invalid_token", "Sign in again to continue.", 401) from exc

    settings = get_settings()
    auth = AuthService(db)
    if settings.auth_mode == "supabase":
        email = str(claims.get("email") or "").strip()
        if not email:
            raise AppError("invalid_token", "The access token has no email claim.", 401)
        metadata = claims.get("user_metadata") or {}
        full_name = metadata.get("full_name") if isinstance(metadata, dict) else None
        profile = auth.ensure_supabase_profile(user_id=user_id, email=email, full_name=full_name)
    else:
        profile = auth.users.get_by_id(user_id)
        if profile is None:
            raise AppError("invalid_token", "Sign in again to continue.", 401)
        set_current_user(db, profile.id)
    return profile


def get_org_context(
    user: Profile = Depends(get_current_user),
    db: Session = Depends(get_db),
    organization_id: uuid.UUID | None = None,
) -> OrgContext:
    if organization_id is None:
        raise AppError("organization_required", "Choose an organization before continuing.", 400)
    organization, member = OrganizationService(db).require_context(user, organization_id)
    return OrgContext(user=user, organization=organization, member=member)


def db_session() -> Generator[Session, None, None]:
    yield from get_db()
