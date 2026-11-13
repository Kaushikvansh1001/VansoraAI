import os
from pathlib import Path
from urllib.parse import urlparse

import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()


def _database_identity(url: str) -> tuple[str, str, str]:
    parsed = urlparse(url.replace("postgresql+psycopg", "postgresql", 1))
    return ((parsed.hostname or "").lower(), str(parsed.port or 5432), parsed.path.lstrip("/"))


def _shared_database_url() -> str:
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if not env_file.is_file():
        return ""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("DATABASE_URL="):
            return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def pytest_sessionstart(session: pytest.Session) -> None:
    if not TEST_DATABASE_URL:
        return
    shared = _shared_database_url()
    if shared and _database_identity(shared) == _database_identity(TEST_DATABASE_URL):
        pytest.exit(
            "TEST_DATABASE_URL is the shared development database. "
            "Tests will not truncate it. Create a separate disposable Supabase project for tests.",
            returncode=2,
        )
    identity = _database_identity(TEST_DATABASE_URL)
    if identity[0] in {"localhost", "127.0.0.1"}:
        pytest.exit(
            "TEST_DATABASE_URL points at this computer. Use a disposable Supabase database instead.",
            returncode=2,
        )


if TEST_DATABASE_URL:
    os.environ["APP_ENV"] = "test"
    os.environ["AUTH_MODE"] = "local"
    os.environ["EXPOSE_DEV_TOKENS"] = "true"
    os.environ["SECRET_KEY"] = "test-secret-key"
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["CORS_ORIGINS"] = "http://localhost:3000"

    from alembic import command
    from alembic.config import Config
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from app.core.config import get_settings
    from app.main import app
    from app.models import Base

    get_settings.cache_clear()
else:
    app = None
    Base = None


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if TEST_DATABASE_URL:
        return
    reason = (
        "Database tests are skipped. Set TEST_DATABASE_URL to a disposable Supabase project, "
        "never the shared development database."
    )
    skip = pytest.mark.skip(reason=reason)
    for item in items:
        if item.get_closest_marker("db"):
            item.add_marker(skip)


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    if not TEST_DATABASE_URL:
        yield
        return
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL.replace("%", "%%"))
    command.upgrade(config, "head")
    yield


@pytest.fixture(autouse=True)
def clean_database():
    if not TEST_DATABASE_URL or Base is None:
        yield
        return
    engine = create_engine(TEST_DATABASE_URL)
    table_names = ", ".join(table.name for table in reversed(Base.metadata.sorted_tables))
    with Session(engine) as session:
        session.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
        session.commit()
    engine.dispose()
    yield


@pytest.fixture
def client():
    if app is None:
        pytest.skip("TEST_DATABASE_URL is not set")
    with TestClient(app) as test_client:
        yield test_client
