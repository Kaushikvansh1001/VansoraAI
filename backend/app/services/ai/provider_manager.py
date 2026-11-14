import logging
import time
from collections.abc import Callable, Iterator

import httpx

from app.core.config import Settings
from app.services.ai.exceptions import ProviderChainFailed, ProviderError
from app.services.ai.models import GenerationOutcome, GenerationRequest, HealthReport, ProviderResponse, UsageRecord
from app.services.ai.providers.gemini import GeminiProvider
from app.services.ai.providers.groq import GroqProvider
from app.services.ai.providers.ollama import OllamaProvider
from app.services.ai.usage_tracker import estimate_cost

logger = logging.getLogger("vansoraai")
Sleep = Callable[[float], None]


class ProviderManager:
    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.Client | None = None,
        sink: object | None = None,
        max_attempts: int = 3,
        base_delay: float = 0.4,
        sleep: Sleep = time.sleep,
    ) -> None:
        self.settings = settings
        self.client = client or httpx.Client()
        self.sink = sink
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.sleep = sleep
        self.providers = {
            "gemini": GeminiProvider(settings.gemini_api_key, settings.gemini_model, self.client, settings.ai_request_timeout_seconds),
            "groq": GroqProvider(settings.groq_api_key, settings.groq_model, self.client, settings.ai_request_timeout_seconds),
            "ollama": OllamaProvider(settings.ollama_base_url, settings.ollama_model, self.client, settings.ai_request_timeout_seconds),
        }

    def chain(self) -> list:
        names: list[str] = []
        primary = self.settings.ai_primary_provider.strip().lower()
        if primary:
            names.append(primary)
        for name in self.settings.fallback_provider_list:
            if name not in names:
                names.append(name)
        ordered = []
        for name in names:
            provider = self.providers.get(name)
            if provider is None:
                continue
            ordered.append(provider)
        return ordered

    def health(self) -> list[HealthReport]:
        reports = []
        for provider in self.chain():
            reports.append(self._health_one(provider))
        return reports

    def generate(
        self,
        request: GenerationRequest,
        *,
        organization_id,
        user_id,
        feature: str,
    ) -> GenerationOutcome:
        failures: list[ProviderError] = []
        providers = self.chain()
        if not providers:
            raise ProviderChainFailed([])
        for provider in providers:
            started = time.perf_counter()
            try:
                result = self._with_retry(provider, request)
            except ProviderError as exc:
                latency = _elapsed(started)
                self._record(
                    provider=provider.name,
                    model=provider.model,
                    feature=feature,
                    organization_id=organization_id,
                    user_id=user_id,
                    status="failed",
                    usage_input=0,
                    usage_output=0,
                    tokens_source="estimated",
                    latency_ms=latency,
                    error_category=exc.category,
                    fallback_from=failures[-1].provider if failures else None,
                )
                logger.info("ai request provider=%s status=failed category=%s", provider.name, exc.category)
                failures.append(exc)
                continue
            latency = _elapsed(started)
            fallback_from = failures[-1].provider if failures else None
            self._record(
                provider=result.provider,
                model=result.model,
                feature=feature,
                organization_id=organization_id,
                user_id=user_id,
                status="succeeded",
                usage_input=result.usage.input_tokens,
                usage_output=result.usage.output_tokens,
                tokens_source=result.usage.source,
                latency_ms=latency,
                error_category=None,
                fallback_from=fallback_from,
            )
            logger.info("ai request provider=%s status=succeeded fallback_from=%s", result.provider, fallback_from)
            return GenerationOutcome(
                response=ProviderResponse(
                    provider=result.provider,
                    model=result.model,
                    text=result.text,
                    usage=result.usage,
                    latency_ms=latency,
                ),
                fallback_from=fallback_from,
            )
        raise ProviderChainFailed(failures)

    def stream(
        self,
        request: GenerationRequest,
        *,
        organization_id,
        user_id,
        feature: str,
    ) -> Iterator[str]:
        result = self.generate(
            request,
            organization_id=organization_id,
            user_id=user_id,
            feature=feature,
        )
        if result.response.text:
            yield result.response.text

    def _with_retry(self, provider, request: GenerationRequest) -> ProviderResponse:
        attempt = 0
        while True:
            attempt += 1
            try:
                return provider.generate(request)
            except ProviderError as exc:
                if not exc.recoverable or attempt >= self.max_attempts:
                    raise
                self.sleep(self.base_delay * (2 ** (attempt - 1)))

    def _health_one(self, provider) -> HealthReport:
        capabilities = provider.capabilities()
        if not provider.configured:
            detail = {
                "gemini": "GEMINI_API_KEY is not set.",
                "groq": "GROQ_API_KEY is not set.",
                "ollama": "OLLAMA_BASE_URL is not set.",
            }.get(provider.name, "The provider is not configured.")
            return HealthReport(provider.name, provider.model, False, "not_configured", detail, [], capabilities)
        try:
            models = provider.list_models(self.settings.ai_health_timeout_seconds)
        except ProviderError as exc:
            return HealthReport(provider.name, provider.model, True, "unavailable", exc.message, [], capabilities)
        normalized = {model.removeprefix("models/") for model in models}
        if models and provider.model not in normalized and provider.model not in models:
            return HealthReport(
                provider.name,
                provider.model,
                True,
                "degraded",
                f"{provider.model} was not in the provider model list.",
                models,
                capabilities,
            )
        return HealthReport(provider.name, provider.model, True, "available", "", models, capabilities)

    def _record(self, **kwargs) -> None:
        if self.sink is None:
            return
        cost = estimate_cost(kwargs["provider"], kwargs["model"], kwargs["usage_input"], kwargs["usage_output"])
        self.sink.record(
            UsageRecord(
                organization_id=kwargs["organization_id"],
                user_id=kwargs["user_id"],
                provider=kwargs["provider"],
                model=kwargs["model"],
                feature=kwargs["feature"],
                input_tokens=kwargs["usage_input"],
                output_tokens=kwargs["usage_output"],
                estimated_cost_usd=cost,
                latency_ms=kwargs["latency_ms"],
                status=kwargs["status"],
                error_category=kwargs["error_category"],
                fallback_from=kwargs["fallback_from"],
                tokens_source=kwargs["tokens_source"],
                cost_is_estimate=True,
            )
        )


def _elapsed(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
