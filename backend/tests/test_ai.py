import json
import uuid
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest

from app.core.errors import AppError
from app.services.ai.base import failure_from_status
from app.services.ai.embeddings import EMBEDDING_DIMENSIONS, EmbeddingService
from app.services.ai.exceptions import EmbeddingError, ProviderChainFailed
from app.services.ai.models import GenerationRequest, UsageRecord
from app.services.ai.provider_manager import ProviderManager
from app.services.ai.providers.gemini import GeminiProvider
from app.services.ai.providers.groq import GroqProvider
from app.services.ai.providers.ollama import OllamaProvider
from app.services.ai.usage_tracker import UsageTracker, estimate_cost


class Sink:
    def __init__(self) -> None:
        self.rows: list[UsageRecord] = []

    def record(self, row: UsageRecord) -> None:
        self.rows.append(row)


class Settings:
    def __init__(self, **overrides) -> None:
        self.gemini_api_key = "gemini-test-key"
        self.gemini_model = "gemini-2.5-flash-lite"
        self.groq_api_key = "groq-test-key"
        self.groq_model = "openai/gpt-oss-20b"
        self.ollama_base_url = "http://127.0.0.1:11434"
        self.ollama_model = "llama3.2"
        self.ai_primary_provider = "gemini"
        self.ai_fallback_providers = "groq,ollama"
        self.ai_request_timeout_seconds = 5
        self.ai_health_timeout_seconds = 1
        for key, value in overrides.items():
            setattr(self, key, value)

    @property
    def fallback_provider_list(self) -> list[str]:
        return [name.strip() for name in self.ai_fallback_providers.split(",") if name.strip()]


def manager(handler, **overrides) -> tuple[ProviderManager, Sink, dict]:
    counts = {"gemini": 0, "groq": 0, "ollama": 0}
    bodies: dict = {}

    def routed(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if "googleapis" in host:
            counts["gemini"] += 1
            name = "gemini"
        elif "groq" in host:
            counts["groq"] += 1
            name = "groq"
        else:
            counts["ollama"] += 1
            name = "ollama"
        if request.content:
            bodies[name] = json.loads(request.content.decode())
        return handler(name, request)

    client = httpx.Client(transport=httpx.MockTransport(routed))
    sink = Sink()
    built = ProviderManager(
        Settings(**overrides),
        client=client,
        sink=sink,
        max_attempts=overrides.get("max_attempts", 3),
        base_delay=0,
        sleep=lambda _seconds: None,
    )
    return built, sink, {"counts": counts, "bodies": bodies}


def gemini_ok(text: str = "hello", usage: bool = True) -> dict:
    payload = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    if usage:
        payload["usageMetadata"] = {"promptTokenCount": 5, "candidatesTokenCount": 7}
    return payload


def groq_ok(text: str = "from groq") -> dict:
    return {
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 2, "completion_tokens": 3},
    }


def test_gemini_success_uses_provider_token_counts():
    def handler(name, _request):
        assert name == "gemini"
        return httpx.Response(200, json=gemini_ok())

    built, sink, seen = manager(handler, ai_fallback_providers="")
    outcome = built.generate(GenerationRequest("Explain the policy."), organization_id=uuid.uuid4(), user_id=uuid.uuid4(), feature="provider_test")
    assert outcome.response.text == "hello"
    assert outcome.response.usage.source == "provider"
    assert outcome.response.usage.input_tokens == 5
    assert outcome.fallback_from is None
    assert sink.rows[0].status == "succeeded"
    assert sink.rows[0].cost_is_estimate is True
    assert seen["counts"]["groq"] == 0


def test_groq_success():
    def handler(name, _request):
        assert name == "groq"
        return httpx.Response(200, json=groq_ok())

    built, sink, _seen = manager(handler, ai_primary_provider="groq", ai_fallback_providers="")
    outcome = built.generate(GenerationRequest("Hello"), organization_id=None, user_id=None, feature="provider_test")
    assert outcome.response.provider == "groq"
    assert outcome.response.usage.output_tokens == 3
    assert sink.rows[0].provider == "groq"


def test_ollama_success():
    def handler(name, _request):
        assert name == "ollama"
        return httpx.Response(200, json={"message": {"content": "local"}, "prompt_eval_count": 4, "eval_count": 6})

    built, _sink, _seen = manager(handler, ai_primary_provider="ollama", ai_fallback_providers="")
    outcome = built.generate(GenerationRequest("Hello"), organization_id=None, user_id=None, feature="provider_test")
    assert outcome.response.text == "local"
    assert outcome.response.usage.source == "provider"


def test_quota_exhaustion_falls_back_to_groq():
    def handler(name, _request):
        if name == "gemini":
            return httpx.Response(429, json={"error": {"message": "quota"}})
        return httpx.Response(200, json=groq_ok())

    built, sink, seen = manager(handler, max_attempts=2)
    outcome = built.generate(GenerationRequest("Hello"), organization_id=None, user_id=None, feature="provider_test")
    assert outcome.response.provider == "groq"
    assert outcome.fallback_from == "gemini"
    assert seen["counts"]["gemini"] == 2
    assert seen["counts"]["groq"] == 1
    assert [row.status for row in sink.rows] == ["failed", "succeeded"]
    assert sink.rows[0].error_category == "rate_limit"


def test_invalid_credentials_are_not_retried():
    def handler(name, _request):
        if name == "gemini":
            return httpx.Response(401, text="API key not valid")
        return httpx.Response(200, json=groq_ok())

    built, sink, seen = manager(handler, max_attempts=3)
    outcome = built.generate(GenerationRequest("Hello"), organization_id=None, user_id=None, feature="provider_test")
    assert seen["counts"]["gemini"] == 1
    assert outcome.response.provider == "groq"
    assert sink.rows[0].error_category == "invalid_credentials"


def test_timeout_is_retried_then_fails_over():
    def handler(name, _request):
        if name == "gemini":
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, json=groq_ok())

    built, sink, seen = manager(handler, max_attempts=2)
    outcome = built.generate(GenerationRequest("Hello"), organization_id=None, user_id=None, feature="provider_test")
    assert seen["counts"]["gemini"] == 2
    assert outcome.response.text == "from groq"
    assert sink.rows[0].error_category == "timeout"


def test_unavailable_provider_does_not_report_success():
    def handler(name, _request):
        raise httpx.ConnectError("refused")

    built, sink, _seen = manager(handler, ai_primary_provider="ollama", ai_fallback_providers="", max_attempts=2)
    with pytest.raises(ProviderChainFailed) as caught:
        built.generate(GenerationRequest("Hello"), organization_id=None, user_id=None, feature="provider_test")
    assert "ollama: connection" in str(caught.value)
    assert all(row.status == "failed" for row in sink.rows)
    assert not any(row.status == "succeeded" for row in sink.rows)


def test_missing_usage_is_marked_estimated():
    def handler(name, _request):
        return httpx.Response(200, json=gemini_ok(usage=False))

    built, sink, _seen = manager(handler, ai_fallback_providers="")
    outcome = built.generate(GenerationRequest("abcd"), organization_id=None, user_id=None, feature="provider_test")
    assert outcome.response.usage.source == "estimated"
    assert outcome.response.usage.input_tokens >= 1
    assert sink.rows[0].tokens_source == "estimated"


def test_cost_estimate_is_labeled_and_calculated():
    assert estimate_cost("gemini", "gemini-2.5-flash-lite", 1_000_000, 2_000_000) == Decimal("0.900000")
    assert estimate_cost("ollama", "llama3.2", 500, 500) == Decimal("0.000000")


def test_gemini_sends_json_schema_and_tools():
    def handler(name, _request):
        return httpx.Response(200, json=gemini_ok("{}", usage=True))

    built, _sink, seen = manager(handler, ai_fallback_providers="")
    request = GenerationRequest("Return json", json_schema={"type": "object"}, tools=[{"name": "lookup"}])
    built.generate(request, organization_id=None, user_id=None, feature="provider_test")
    body = seen["bodies"]["gemini"]
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["responseSchema"]["type"] == "object"
    assert body["tools"][0]["functionDeclarations"][0]["name"] == "lookup"


def test_groq_json_mode_does_not_pretend_to_send_a_schema():
    def handler(name, _request):
        return httpx.Response(200, json=groq_ok("{}"))

    built, _sink, seen = manager(handler, ai_primary_provider="groq", ai_fallback_providers="")
    built.generate(
        GenerationRequest("Return json", json_schema={"type": "object"}),
        organization_id=None,
        user_id=None,
        feature="provider_test",
    )
    body = seen["bodies"]["groq"]
    assert body["response_format"] == {"type": "json_object"}
    assert "responseSchema" not in body


def test_ollama_rejects_tools_without_calling_the_server():
    client = httpx.Client(transport=httpx.MockTransport(lambda _request: (_ for _ in ()).throw(AssertionError("called"))))
    provider = OllamaProvider("http://127.0.0.1:11434", "llama3.2", client)
    with pytest.raises(Exception) as caught:
        provider.generate(GenerationRequest("Hello", tools=[{"name": "lookup"}]))
    assert caught.value.category == "unsupported"


def test_server_errors_are_recoverable_and_credentials_are_not():
    assert failure_from_status("gemini", 503, "unavailable").recoverable is True
    assert failure_from_status("gemini", 502, "bad gateway").recoverable is True
    assert failure_from_status("gemini", 500, "boom").recoverable is True
    denied = failure_from_status("gemini", 401, "key AIzaSYFAKEKEY1234567890 rejected")
    assert denied.recoverable is False
    assert "AIza" not in denied.message
    groq = failure_from_status("groq", 401, "key gsk_fakekeyvalue1234567890 rejected")
    assert groq.recoverable is False
    assert "gsk_" not in groq.message
    gemini = failure_from_status("gemini", 401, "key AQ.FakeKeyValue1234567890 rejected")
    assert "AQ." not in gemini.message


def test_usage_tracker_stores_estimates_without_a_prompt_or_key():
    class FakeSession:
        def __init__(self) -> None:
            self.added = []

        def add(self, row) -> None:
            self.added.append(row)

        def flush(self) -> None:
            return None

    session = FakeSession()
    UsageTracker(session).record(
        UsageRecord(
            organization_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            provider="gemini",
            model="gemini-2.5-flash-lite",
            feature="provider_test",
            input_tokens=5,
            output_tokens=7,
            estimated_cost_usd=Decimal("0.000001"),
            latency_ms=12,
            status="succeeded",
            error_category=None,
            fallback_from=None,
            tokens_source="provider",
        )
    )
    row = session.added[0]
    assert row.feature == "provider_test"
    assert row.cost_is_estimate is True
    assert row.tokens_source == "provider"
    assert "prompt" not in row.__dict__
    assert "api_key" not in row.__dict__


def test_embedding_batch_must_match_the_existing_vector_width():
    def embed(texts):
        return [[0.1] * EMBEDDING_DIMENSIONS for _text in texts]

    service = EmbeddingService(embedder=embed)
    vectors = service.embed_texts(["alpha", "beta"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 384


def test_embedding_rejects_a_different_dimension():
    service = EmbeddingService(embedder=lambda texts: [[0.1] * 768 for _text in texts])
    with pytest.raises(EmbeddingError):
        service.embed_text("alpha")


def test_embedding_rejects_blank_text():
    service = EmbeddingService(embedder=lambda texts: [[0.1] * 384 for _text in texts])
    with pytest.raises(EmbeddingError):
        service.embed_texts([" "])


def test_provider_status_schema_has_no_secret_field():
    from app.schemas.ai import CapabilitiesResponse, ProviderHealthResponse

    payload = ProviderHealthResponse(
        provider="gemini",
        model="gemini-2.5-flash-lite",
        configured=True,
        status="not_configured",
        detail="GEMINI_API_KEY is not set.",
        models=[],
        capabilities=CapabilitiesResponse(text=True, stream=True, json_output=True, json_schema=True, tools=True),
        active=True,
    ).model_dump()
    assert "api_key" not in payload
    assert "gemini_api_key" not in payload


def test_members_cannot_open_provider_management(monkeypatch):
    from app.api.v1.routes.ai import _admin
    from app.services.organizations import OrganizationService

    def deny(self, user, organization_id):
        raise AppError("forbidden", "You do not have permission to do that.", 403)

    monkeypatch.setattr(OrganizationService, "require_admin", deny)
    with pytest.raises(AppError) as caught:
        _admin(organization_id=uuid.uuid4(), user=SimpleNamespace(id=uuid.uuid4()), db=object())
    assert caught.value.status_code == 403


def test_direct_provider_clients_parse_their_own_payloads():
    def transport(request: httpx.Request) -> httpx.Response:
        if b"functionDeclarations" in request.content:
            return httpx.Response(200, json=gemini_ok("tool"))
        if request.url.host == "api.groq.com":
            return httpx.Response(200, json=groq_ok("groq-text"))
        return httpx.Response(200, json=gemini_ok("gemini-text"))

    client = httpx.Client(transport=httpx.MockTransport(transport))
    assert GeminiProvider("key", "gemini-2.5-flash-lite", client).generate(GenerationRequest("Hi")).text == "gemini-text"
    assert GroqProvider("key", "openai/gpt-oss-20b", client).generate(GenerationRequest("Hi")).text == "groq-text"
