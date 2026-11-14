import re
import uuid

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import set_current_organization, set_current_user
from app.models.enums import MemberRole
from app.models.identity import Organization, OrganizationMember, Profile
from app.repositories.organizations import OrganizationRepository
from app.repositories.users import UserRepository
from app.schemas.organizations import MemberResponse, OrganizationResponse
from app.services.audit import record_audit


class OrganizationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.organizations = OrganizationRepository(db)
        self.users = UserRepository(db)

    def list_for_user(self, user: Profile) -> list[OrganizationResponse]:
        rows = self.organizations.list_for_user(user.id)
        return [self._organization_response(organization, member) for organization, member in rows]

    def create(self, user: Profile, name: str, ip_address: str | None) -> OrganizationResponse:
        set_current_user(self.db, user.id)
        organization = Organization(
            name=name.strip(),
            slug=self._unique_slug(name),
            created_by=user.id,
        )
        self.db.add(organization)
        self.db.flush()
        set_current_organization(self.db, organization.id)
        member = OrganizationMember(
            organization_id=organization.id,
            user_id=user.id,
            role=MemberRole.org_admin,
        )
        self.db.add(member)
        self.db.flush()
        self.db.refresh(organization)
        self.db.refresh(member)
        record_audit(
            self.db,
            action="organization.create",
            resource_type="organization",
            actor_id=user.id,
            organization_id=organization.id,
            resource_id=organization.id,
            ip_address=ip_address,
        )
        return self._organization_response(organization, member)

    def get_for_member(self, user: Profile, organization_id: uuid.UUID) -> OrganizationResponse:
        organization, member = self._require_membership(user, organization_id)
        return self._organization_response(organization, member)

    def update(self, user: Profile, organization_id: uuid.UUID, name: str, ip_address: str | None) -> OrganizationResponse:
        organization, member = self._require_role(user, organization_id, MemberRole.org_admin)
        organization.name = name.strip()
        record_audit(
            self.db,
            action="organization.update",
            resource_type="organization",
            actor_id=user.id,
            organization_id=organization.id,
            resource_id=organization.id,
            details={"name": organization.name},
            ip_address=ip_address,
        )
        return self._organization_response(organization, member)

    def list_members(self, user: Profile, organization_id: uuid.UUID) -> list[MemberResponse]:
        self._require_membership(user, organization_id)
        rows = self.organizations.list_members(organization_id)
        return [self._member_response(member, profile) for member, profile in rows]

    def add_member(
        self,
        user: Profile,
        organization_id: uuid.UUID,
        email: str,
        role: MemberRole,
        ip_address: str | None,
    ) -> MemberResponse:
        self._require_role(user, organization_id, MemberRole.org_admin)
        profile = self.users.get_by_email(email.lower())
        credential = self.users.get_credentials(profile.id) if profile else None
        verified = get_settings().auth_mode == "supabase" or (
            credential is not None and credential.email_verified_at is not None
        )
        if profile is None or not verified:
            raise AppError("user_not_found", "No verified account exists for that email.", 404)
        if self.organizations.get_member(organization_id, profile.id):
            raise AppError("already_member", "That person is already in this organization.", 409)
        member = OrganizationMember(organization_id=organization_id, user_id=profile.id, role=role)
        self.db.add(member)
        self.db.flush()
        self.db.refresh(member)
        record_audit(
            self.db,
            action="organization.member_add",
            resource_type="organization_member",
            actor_id=user.id,
            organization_id=organization_id,
            resource_id=member.id,
            details={"role": role.value},
            ip_address=ip_address,
        )
        return self._member_response(member, profile)

    def update_member(
        self,
        user: Profile,
        organization_id: uuid.UUID,
        member_id: uuid.UUID,
        role: MemberRole,
        ip_address: str | None,
    ) -> MemberResponse:
        self._require_role(user, organization_id, MemberRole.org_admin)
        member, profile = self._get_member_row(organization_id, member_id)
        if member.role == MemberRole.org_admin and role != MemberRole.org_admin:
            self._guard_last_admin(organization_id)
        member.role = role
        record_audit(
            self.db,
            action="organization.member_update",
            resource_type="organization_member",
            actor_id=user.id,
            organization_id=organization_id,
            resource_id=member.id,
            details={"role": role.value},
            ip_address=ip_address,
        )
        return self._member_response(member, profile)

    def remove_member(
        self,
        user: Profile,
        organization_id: uuid.UUID,
        member_id: uuid.UUID,
        ip_address: str | None,
    ) -> None:
        self._require_role(user, organization_id, MemberRole.org_admin)
        member, _profile = self._get_member_row(organization_id, member_id)
        if member.role == MemberRole.org_admin:
            self._guard_last_admin(organization_id)
        self.db.delete(member)
        record_audit(
            self.db,
            action="organization.member_remove",
            resource_type="organization_member",
            actor_id=user.id,
            organization_id=organization_id,
            resource_id=member_id,
            ip_address=ip_address,
        )

    def require_context(self, user: Profile, organization_id: uuid.UUID) -> tuple[Organization, OrganizationMember]:
        return self._require_membership(user, organization_id)

    def require_admin(self, user: Profile, organization_id: uuid.UUID) -> tuple[Organization, OrganizationMember]:
        return self._require_role(user, organization_id, MemberRole.org_admin)

    def _require_membership(self, user: Profile, organization_id: uuid.UUID) -> tuple[Organization, OrganizationMember]:
        organization = self.organizations.get(organization_id)
        member = self.organizations.get_member(organization_id, user.id)
        if organization is None or member is None:
            raise AppError("forbidden", "You do not have access to that organization.", 403)
        set_current_user(self.db, user.id)
        set_current_organization(self.db, organization_id)
        return organization, member

    def _require_role(
        self, user: Profile, organization_id: uuid.UUID, role: MemberRole
    ) -> tuple[Organization, OrganizationMember]:
        organization, member = self._require_membership(user, organization_id)
        if member.role != role:
            raise AppError("forbidden", "You do not have permission to do that.", 403)
        return organization, member

    def _guard_last_admin(self, organization_id: uuid.UUID) -> None:
        if self.organizations.count_admins(organization_id) <= 1:
            raise AppError("last_admin", "An organization must keep at least one admin.", 409)

    def _get_member_row(self, organization_id: uuid.UUID, member_id: uuid.UUID) -> tuple[OrganizationMember, Profile]:
        for member, profile in self.organizations.list_members(organization_id):
            if member.id == member_id:
                return member, profile
        raise AppError("not_found", "That member is not in this organization.", 404)

    def _unique_slug(self, name: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48] or "organization"
        slug = base
        suffix = 2
        while self.organizations.slug_taken(slug):
            slug = f"{base[:40]}-{suffix}"
            suffix += 1
        return slug

    @staticmethod
    def _organization_response(organization: Organization, member: OrganizationMember) -> OrganizationResponse:
        return OrganizationResponse(
            id=organization.id,
            name=organization.name,
            slug=organization.slug,
            role=member.role,
            created_at=organization.created_at,
        )

    @staticmethod
    def _member_response(member: OrganizationMember, profile: Profile) -> MemberResponse:
        return MemberResponse(
            id=member.id,
            user_id=profile.id,
            email=profile.email,
            full_name=profile.full_name,
            role=member.role,
            created_at=member.created_at,
        )
