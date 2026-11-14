import pytest

from app.core.config import Settings


def _production(**overrides) -> Settings:
    values = {
        "app_env": "production",
        "secret_key": "a-real-production-secret",
        "database_url": "postgresql+psycopg://user:pass@aws-1-ap-southeast-2.pooler.supabase.com:5432/postgres",
        "cors_origins": "https://vansora.vercel.app",
        "auth_mode": "supabase",
        "expose_dev_tokens": False,
        "supabase_url": "https://example.supabase.co",
        "supabase_service_role_key": "sb_secret_test",
        "ai_primary_provider": "gemini",
        "ai_fallback_providers": "groq",
        "ollama_base_url": "",
        "knowledge_mode": "demo",
    }
    values.update(overrides)
    return Settings(**values)


def test_production_accepts_groq_without_a_local_ollama():
    _production().validate_runtime()


def test_production_rejects_localhost_cors_ollama_and_full_knowledge():
    with pytest.raises(ValueError, match="KNOWLEDGE_MODE"):
        _production(knowledge_mode="full").validate_runtime()
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        _production(cors_origins="http://localhost:3000").validate_runtime()
    with pytest.raises(ValueError, match="Ollama"):
        _production(ai_fallback_providers="groq,ollama", ollama_base_url="http://127.0.0.1:11434").validate_runtime()
    with pytest.raises(ValueError, match="Ollama"):
        _production(ai_fallback_providers="groq,ollama", ollama_base_url="").validate_runtime()
