from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderCapabilities:
    text: bool = True
    stream: bool = False
    json_output: bool = False
    json_schema: bool = False
    tools: bool = False


@dataclass(frozen=True)
class GenerationRequest:
    prompt: str
    json_schema: dict | None = None
    tools: list[dict] | None = None


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    source: str


@dataclass(frozen=True)
class GenerationOutcome:
    response: "ProviderResponse"
    fallback_from: str | None


@dataclass(frozen=True)
class ProviderResponse:
    provider: str
    model: str
    text: str
    usage: TokenUsage
    latency_ms: int


@dataclass(frozen=True)
class HealthReport:
    provider: str
    model: str
    configured: bool
    status: str
    detail: str
    models: list[str] = field(default_factory=list)
    capabilities: ProviderCapabilities = field(default_factory=ProviderCapabilities)


@dataclass(frozen=True)
class UsageRecord:
    organization_id: object
    user_id: object
    provider: str
    model: str
    feature: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: object
    latency_ms: int
    status: str
    error_category: str | None
    fallback_from: str | None
    tokens_source: str
    cost_is_estimate: bool = True
