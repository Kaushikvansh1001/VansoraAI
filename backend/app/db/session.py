import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=5, max_overflow=2)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def set_current_user(db: Session, user_id: uuid.UUID) -> None:
    db.execute(
        text("SELECT set_config('app.current_user_id', :user_id, true)"),
        {"user_id": str(user_id)},
    )


def set_current_organization(db: Session, organization_id: uuid.UUID) -> None:
    db.execute(
        text("SELECT set_config('app.current_org_id', :organization_id, true)"),
        {"organization_id": str(organization_id)},
    )
