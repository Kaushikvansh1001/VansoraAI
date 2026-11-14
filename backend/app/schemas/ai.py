from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class CapabilitiesResponse(BaseModel):
    text: bool
    stream: bool
    json_output: bool
    json_schema: bool
    tools: bool


class ProviderHealthResponse(BaseModel):
    provider: str
    model: str
    configured: bool
    status: str
    detail: str
    models: list[str]
    capabilities: CapabilitiesResponse
    active: bool


class ProviderStatusResponse(BaseModel):
    active_provider: str
    fallback_providers: list[str]
    providers: list[ProviderHealthResponse]


class UsageProviderResponse(BaseModel):
    provider: str
    requests_succeeded: int
    requests_failed: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: str


class UsageResponse(BaseModel):
    requests_succeeded: int
    requests_failed: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: str
    cost_is_estimate: bool = True
    providers: list[UsageProviderResponse]


class FallbackEventResponse(BaseModel):
    provider: str
    model: str
    status: str
    error_category: str | None
    fallback_from: str | None
    latency_ms: int | None
    created_at: datetime


class TestGenerationRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=500)


class TestGenerationResponse(BaseModel):
    text: str
    provider: str
    model: str
    fallback_from: str | None
    input_tokens: int
    output_tokens: int
    tokens_source: str
    estimated_cost_usd: str
    cost_is_estimate: bool = True


def money(value: Decimal) -> str:
    return f"{Decimal(value):.6f}"
