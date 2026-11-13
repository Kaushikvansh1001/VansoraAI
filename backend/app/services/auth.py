import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    verify_password_or_dummy,
)
from app.db.session import set_current_user
from app.models.identity import LocalCredential, Profile
from app.repositories.users import UserRepository
from app.schemas.auth import UserResponse
from app.services.audit import record_audit

VERIFICATION_HOURS = 24
RESET_MINUTES = 60


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)

    def register(self, *, email: str, password: str, full_name: str, ip_address: str | None) -> tuple[UserResponse, str | None]:
        self._require_local_auth()
        normalized = email.lower()
        if self.users.get_by_email(normalized):
            raise AppError("email_taken", "An account with that email already exists.", 409)

        user_id = uuid.uuid4()
        set_current_user(self.db, user_id)
        profile = Profile(id=user_id, email=normalized, full_name=full_name)
        raw_token = secrets.token_urlsafe(32)
        credential = LocalCredential(
            user_id=user_id,
            password_hash=hash_password(password),
            verification_token_hash=hash_token(raw_token),
            verification_expires_at=datetime.now(timezone.utc) + timedelta(hours=VERIFICATION_HOURS),
        )
        self.db.add(profile)
        self.db.add(credential)
        try:
            self.db.flush()
        except IntegrityError as exc:
            raise AppError("email_taken", "An account with that email already exists.", 409) from exc

        record_audit(
            self.db,
            action="auth.register",
            resource_type="profile",
            actor_id=user_id,
            resource_id=user_id,
            ip_address=ip_address,
        )
        return self._user_response(profile, email_verified=False), self._dev_token(raw_token)

    def verify_email(self, token: str) -> tuple[str, UserResponse]:
        self._require_local_auth()
        credential = self.users.get_by_verification_hash(hash_token(token))
        if credential is None or not self._is_current(credential.verification_expires_at):
            raise AppError("invalid_token", "That verification link is invalid or expired.", 400)
        profile = self.users.get_by_id(credential.user_id)
        if profile is None:
            raise AppError("invalid_token", "That verification link is invalid or expired.", 400)

        credential.email_verified_at = datetime.now(timezone.utc)
        credential.verification_token_hash = None
        credential.verification_expires_at = None
        record_audit(
            self.db,
            action="auth.verify_email",
            resource_type="profile",
            actor_id=profile.id,
            resource_id=profile.id,
        )
        return create_access_token(user_id=profile.id, email=profile.email), self._user_response(profile, True)

    def login(self, *, email: str, password: str, ip_address: str | None) -> tuple[str, UserResponse]:
        self._require_local_auth()
        profile = self.users.get_by_email(email.lower())
        credential = self.users.get_credentials(profile.id) if profile else None
        if not verify_password_or_dummy(password, credential.password_hash if credential else None) or profile is None:
            raise AppError("invalid_credentials", "Email or password is incorrect.", 401)
        if credential is None or credential.email_verified_at is None:
            raise AppError("email_not_verified", "Verify your email before signing in.", 403)

        record_audit(
            self.db,
            action="auth.login",
            resource_type="profile",
            actor_id=profile.id,
            resource_id=profile.id,
            ip_address=ip_address,
        )
        return create_access_token(user_id=profile.id, email=profile.email), self._user_response(profile, True)

    def forgot_password(self, email: str) -> str | None:
        self._require_local_auth()
        profile = self.users.get_by_email(email.lower())
        credential = self.users.get_credentials(profile.id) if profile else None
        if profile is None or credential is None:
            return None
        raw_token = secrets.token_urlsafe(32)
        credential.reset_token_hash = hash_token(raw_token)
        credential.reset_expires_at = datetime.now(timezone.utc) + timedelta(minutes=RESET_MINUTES)
        record_audit(
            self.db,
            action="auth.forgot_password",
            resource_type="profile",
            actor_id=profile.id,
            resource_id=profile.id,
        )
        return self._dev_token(raw_token)

    def reset_password(self, *, token: str, password: str) -> None:
        self._require_local_auth()
        credential = self.users.get_by_reset_hash(hash_token(token))
        if credential is None or not self._is_current(credential.reset_expires_at):
            raise AppError("invalid_token", "That reset link is invalid or expired.", 400)
        credential.password_hash = hash_password(password)
        credential.reset_token_hash = None
        credential.reset_expires_at = None
        if credential.email_verified_at is None:
            credential.email_verified_at = datetime.now(timezone.utc)
        record_audit(
            self.db,
            action="auth.reset_password",
            resource_type="profile",
            actor_id=credential.user_id,
            resource_id=credential.user_id,
        )

    def update_profile(self, profile: Profile, full_name: str) -> UserResponse:
        profile.full_name = full_name
        profile.updated_at = datetime.now(timezone.utc)
        verified = self._is_verified(profile)
        return self._user_response(profile, verified)

    def to_response(self, profile: Profile) -> UserResponse:
        return self._user_response(profile, self._is_verified(profile))

    def ensure_supabase_profile(self, *, user_id: uuid.UUID, email: str, full_name: str | None) -> Profile:
        set_current_user(self.db, user_id)
        profile = self.users.get_by_id(user_id)
        if profile is not None:
            return profile
        profile = Profile(
            id=user_id,
            email=email.lower(),
            full_name=(full_name or email.split("@")[0])[:120],
        )
        self.db.add(profile)
        try:
            self.db.flush()
        except IntegrityError as exc:
            raise AppError("email_taken", "That email is already registered.", 409) from exc
        return profile

    def _is_verified(self, profile: Profile) -> bool:
        if get_settings().auth_mode == "supabase":
            return True
        credential = self.users.get_credentials(profile.id)
        return credential is not None and credential.email_verified_at is not None

    def _user_response(self, profile: Profile, email_verified: bool) -> UserResponse:
        return UserResponse(
            id=profile.id,
            email=profile.email,
            full_name=profile.full_name,
            is_super_admin=profile.is_super_admin,
            email_verified=email_verified,
        )

    def _dev_token(self, raw_token: str) -> str | None:
        if get_settings().dev_tokens_enabled:
            return raw_token
        return None

    def _require_local_auth(self) -> None:
        if get_settings().auth_mode != "local":
            raise AppError(
                "auth_handled_by_supabase",
                "This server uses Supabase Auth. Register and sign in through the Supabase client.",
                404,
            )

    @staticmethod
    def _is_current(expires_at: datetime | None) -> bool:
        if expires_at is None:
            return False
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at >= datetime.now(timezone.utc)
