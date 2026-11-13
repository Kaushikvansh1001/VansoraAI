import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.identity import LocalCredential, Profile


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_email(self, email: str) -> Profile | None:
        return self.db.scalar(select(Profile).where(Profile.email == email))

    def get_by_id(self, user_id: uuid.UUID) -> Profile | None:
        return self.db.get(Profile, user_id)

    def get_credentials(self, user_id: uuid.UUID) -> LocalCredential | None:
        return self.db.get(LocalCredential, user_id)

    def get_by_verification_hash(self, token_hash: str) -> LocalCredential | None:
        return self.db.scalar(
            select(LocalCredential).where(LocalCredential.verification_token_hash == token_hash)
        )

    def get_by_reset_hash(self, token_hash: str) -> LocalCredential | None:
        return self.db.scalar(select(LocalCredential).where(LocalCredential.reset_token_hash == token_hash))
