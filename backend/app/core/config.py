from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_name: str = "VansoraAI"
    secret_key: str = "local-dev-only-change-me"
    access_token_expire_minutes: int = 60
    database_url: str = ""
    cors_origins: str = "http://localhost:3000,http://localhost:3001"
    auth_mode: str = "supabase"
    expose_dev_tokens: bool = False
    job_poll_seconds: float = 2.0
    supabase_url: str = ""
    supabase_jwt_secret: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "documents"

    @field_validator("app_env", "auth_mode")
    @classmethod
    def lowercase(cls, value: str) -> str:
        return value.lower().strip()

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def dev_tokens_enabled(self) -> bool:
        return self.expose_dev_tokens and self.app_env == "test"

    def validate_runtime(self) -> None:
        if self.app_env not in {"development", "production", "test"}:
            raise ValueError("APP_ENV must be development, production, or test.")
        if self.auth_mode not in {"local", "supabase"}:
            raise ValueError("AUTH_MODE must be 'supabase' or, for the test suite only, 'local'.")
        if not self.database_url.strip():
            raise ValueError(
                "DATABASE_URL is required. Use the Supabase session-pooler connection string."
            )
        if self.app_env in {"development", "production"}:
            if self.auth_mode != "supabase":
                raise ValueError("Development and production use Supabase Auth.")
            if not self.supabase_url.strip():
                raise ValueError("SUPABASE_URL is required.")
            if not self.supabase_service_role_key.strip():
                raise ValueError(
                    "SUPABASE_SERVICE_ROLE_KEY is required on the server so files go to Supabase Storage."
                )
            lowered = self.database_url.lower()
            if "localhost" in lowered or "127.0.0.1" in lowered:
                raise ValueError("Use the Supabase pooler URL. Do not use a database installed on this computer.")
        if self.app_env == "production":
            if self.expose_dev_tokens:
                raise ValueError("EXPOSE_DEV_TOKENS must be false in production.")
            if self.secret_key == "local-dev-only-change-me":
                raise ValueError("Set a unique SECRET_KEY before production.")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_runtime()
    return settings
