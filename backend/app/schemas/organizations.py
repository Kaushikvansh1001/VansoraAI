import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import MemberRole


class CreateOrganizationRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)


class UpdateOrganizationRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)


class AddMemberRequest(BaseModel):
    email: EmailStr
    role: MemberRole = MemberRole.member


class UpdateMemberRequest(BaseModel):
    role: MemberRole


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    role: MemberRole
    created_at: datetime


class MemberResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: EmailStr
    full_name: str
    role: MemberRole
    created_at: datetime
