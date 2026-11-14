import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.repositories.ai_usage import AiUsageRepository
from app.schemas.ai import (
    CapabilitiesResponse,
    FallbackEventResponse,
    ProviderHealthResponse,
    ProviderStatusResponse,
    TestGenerationResponse,
    UsageProviderResponse,
    UsageResponse,
    money,
)
from app.services.ai.exceptions import ProviderChainFailed
from app.services.ai.models import GenerationRequest
from app.services.ai.provider_manager import ProviderManager
from app.services.ai.usage_tracker import UsageTracker, estimate_cost


class AiAdminService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.manager = ProviderManager(self.settings, sink=UsageTracker(db))
        self.usage = AiUsageRepository(db)

    def provider_status(self) -> ProviderStatusResponse:
        active = self.settings.ai_primary_provider.strip().lower()
        providers = []
        for report in self.manager.health():
            providers.append(
                ProviderHealthResponse(
                    provider=report.provider,
                    model=report.model,
                    configured=report.configured,
                    status=report.status,
                    detail=report.detail,
                    models=report.models,
                    capabilities=CapabilitiesResponse(
                        text=report.capabilities.text,
                        stream=report.capabilities.stream,
                        json_output=report.capabilities.json_output,
                        json_schema=report.capabilities.json_schema,
                        tools=report.capabilities.tools,
                    ),
                    active=report.provider == active,
                )
            )
        return ProviderStatusResponse(
            active_provider=active,
            fallback_providers=self.settings.fallback_provider_list,
            providers=providers,
        )

    def usage_summary(self, organization_id: uuid.UUID) -> UsageResponse:
        rows = self.usage.summary(organization_id)
        providers = [
            UsageProviderResponse(
                provider=row["provider"],
                requests_succeeded=row["requests_succeeded"],
                requests_failed=row["requests_failed"],
                input_tokens=row["input_tokens"],
                output_tokens=row["output_tokens"],
                estimated_cost_usd=money(row["estimated_cost_usd"]),
            )
            for row in rows
        ]
        return UsageResponse(
            requests_succeeded=sum(row.requests_succeeded for row in providers),
            requests_failed=sum(row.requests_failed for row in providers),
            input_tokens=sum(row.input_tokens for row in providers),
            output_tokens=sum(row.output_tokens for row in providers),
            estimated_cost_usd=money(sum((Decimal(row.estimated_cost_usd) for row in providers), Decimal("0"))),
            cost_is_estimate=True,
            providers=providers,
        )

    def fallback_history(self, organization_id: uuid.UUID) -> list[FallbackEventResponse]:
        return [
            FallbackEventResponse(
                provider=row.provider,
                model=row.model,
                status=row.status,
                error_category=row.error_code,
                fallback_from=row.fallback_from,
                latency_ms=row.latency_ms,
                created_at=row.created_at,
            )
            for row in self.usage.fallback_history(organization_id)
        ]

    def test_generation(self, organization_id: uuid.UUID, user_id: uuid.UUID, prompt: str) -> TestGenerationResponse:
        try:
            outcome = self.manager.generate(
                GenerationRequest(prompt=prompt),
                organization_id=organization_id,
                user_id=user_id,
                feature="provider_test",
            )
        except ProviderChainFailed as exc:
            raise AppError("providers_unavailable", str(exc), 502) from exc
        result = outcome.response
        cost = estimate_cost(result.provider, result.model, result.usage.input_tokens, result.usage.output_tokens)
        return TestGenerationResponse(
            text=result.text,
            provider=result.provider,
            model=result.model,
            fallback_from=outcome.fallback_from,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            tokens_source=result.usage.source,
            estimated_cost_usd=money(cost),
            cost_is_estimate=True,
        )
