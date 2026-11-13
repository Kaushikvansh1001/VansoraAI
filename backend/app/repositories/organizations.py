import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import MemberRole
from app.models.identity import Organization, OrganizationMember, Profile


class OrganizationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_user(self, user_id: uuid.UUID) -> list[tuple[Organization, OrganizationMember]]:
        rows = self.db.execute(
            select(Organization, OrganizationMember)
            .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
            .where(OrganizationMember.user_id == user_id)
            .order_by(Organization.name.asc())
        ).all()
        return [(organization, member) for organization, member in rows]

    def get(self, organization_id: uuid.UUID) -> Organization | None:
        return self.db.get(Organization, organization_id)

    def get_member(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> OrganizationMember | None:
        return self.db.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user_id,
            )
        )

    def list_members(self, organization_id: uuid.UUID) -> list[tuple[OrganizationMember, Profile]]:
        rows = self.db.execute(
            select(OrganizationMember, Profile)
            .join(Profile, Profile.id == OrganizationMember.user_id)
            .where(OrganizationMember.organization_id == organization_id)
            .order_by(Profile.full_name.asc())
        ).all()
        return [(member, profile) for member, profile in rows]

    def count_admins(self, organization_id: uuid.UUID) -> int:
        count = self.db.scalar(
            select(func.count())
            .select_from(OrganizationMember)
            .where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.role == MemberRole.org_admin,
            )
        )
        return int(count or 0)

    def slug_taken(self, slug: str) -> bool:
        existing = self.db.scalar(select(Organization.id).where(Organization.slug == slug))
        return existing is not None
