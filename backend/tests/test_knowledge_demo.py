import sys
import uuid

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.core.errors import AppError
from app.main import database_unavailable
from app.models.knowledge import Document, DocumentChunk
from app.repositories.knowledge import KnowledgeRepository
from app.services.ai.models import GenerationOutcome, ProviderResponse, TokenUsage
from app.services.knowledge.sample import SAMPLE_FILENAME
from app.services.knowledge.service import KnowledgeService


class MemoryDb:
    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        return None

    def refresh(self, _obj) -> None:
        return None

    def scalar(self, _statement):
        for obj in self.added:
            if isinstance(obj, Document) and obj.filename == SAMPLE_FILENAME:
                return obj
        return None


def demo_settings() -> Settings:
    return Settings(
        app_env="development",
        auth_mode="supabase",
        knowledge_mode="demo",
        database_url="postgresql+psycopg://user:pass@aws-1-ap-southeast-2.pooler.supabase.com:5432/postgres",
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="sb_secret_test",
    )


def full_settings() -> Settings:
    return demo_settings().model_copy(update={"knowledge_mode": "full"})


class Manager:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, request, **kwargs):
        self.prompts.append(request.prompt)
        usage = TokenUsage(4, 6, "provider")
        response = ProviderResponse("gemini", "gemini-flash-lite-latest", "Revenue was 480000 dollars.", usage, 8)
        return GenerationOutcome(response, None)


def test_hosted_text_search_does_not_use_the_vector_column():
    statement = KnowledgeRepository.search_text_statement(uuid.uuid4(), "Oak Lamp revenue", None, 4)
    sql = str(statement.compile(dialect=postgresql.dialect()))
    where = sql.lower().split("where ", 1)[1]
    assert "to_tsvector" in where
    assert "plainto_tsquery" in where
    assert "@@" in where
    assert "ts_rank" in sql
    assert "cosine" not in sql.lower()


def test_demo_ask_uses_text_search_and_does_not_load_fastembed():
    sys.modules.pop("fastembed", None)
    sys.modules.pop("sentence_transformers", None)
    db = MemoryDb()
    manager = Manager()
    passage = DocumentChunk(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        chunk_index=1,
        content="In 2024 Northwind Studio revenue was 480000 dollars.",
        token_count=8,
        embedding=None,
    )

    def text_retrieve(_organization_id, question, _document_id):
        assert "revenue" in question
        return [(passage, SAMPLE_FILENAME)]

    answer = KnowledgeService(
        db,
        settings=demo_settings(),
        manager=manager,
        text_retriever=text_retrieve,
        embeddings=object(),
    ).ask(
        organization_id=passage.organization_id,
        user_id=uuid.uuid4(),
        question="What was Northwind Studio revenue?",
        document_id=None,
    )
    assert answer.retrieval == "text"
    assert "text search" in manager.prompts[0]
    assert "semantic or vector search" in manager.prompts[0]
    assert "fastembed" not in sys.modules
    assert "sentence_transformers" not in sys.modules
    assert any(isinstance(row, DocumentChunk) and row.embedding is None for row in db.added)


def test_demo_sample_is_created_once_and_uploads_are_rejected():
    db = MemoryDb()
    service = KnowledgeService(db, settings=demo_settings(), manager=Manager())
    organization_id = uuid.uuid4()
    user_id = uuid.uuid4()
    first = service.ensure_sample(organization_id, user_id)
    second = service.ensure_sample(organization_id, user_id)
    assert first.id == second.id
    assert sum(isinstance(row, Document) for row in db.added) == 1
    with pytest.raises(AppError) as exc:
        service.upload(organization_id=organization_id, user_id=user_id, filename="notes.txt", content=b"Hello")
    assert exc.value.code == "demo_mode"


def test_local_full_mode_still_embeds_the_question():
    seen = {"embedded": False}

    class Embedder:
        def embed_text(self, _question):
            seen["embedded"] = True
            return [0.1] * 384

    passage = DocumentChunk(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        chunk_index=0,
        content="Refunds take 30 days.",
        token_count=4,
        embedding=[0.1] * 384,
    )
    manager = Manager()

    def retrieve(_organization_id, vector, _document_id):
        assert vector[0] == 0.1
        return [(passage, "policy.txt")]

    answer = KnowledgeService(
        MemoryDb(),
        settings=full_settings(),
        embeddings=Embedder(),
        manager=manager,
        retriever=retrieve,
    ).ask(
        organization_id=passage.organization_id,
        user_id=uuid.uuid4(),
        question="How long do refunds take?",
        document_id=None,
    )
    assert seen["embedded"] is True
    assert answer.retrieval == "vector"
    assert "text search" not in manager.prompts[0]
    assert answer.answer


def test_paused_database_returns_a_clear_status():
    class Request:
        class State:
            request_id = "test-request"

        state = State()

    import asyncio

    response = asyncio.run(database_unavailable(Request(), OperationalError("SELECT 1", {}, Exception("timeout"))))
    assert response.status_code == 503
    assert b"database_unavailable" in response.body
    assert b"resume the project" in response.body
