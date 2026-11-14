import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.operations import AiUsageLog
from app.services.ai.models import UsageRecord

# Published list prices in USD per 1,000,000 tokens. These are estimates, not invoices.
_MODEL_PRICES: dict[tuple[str, str], tuple[Decimal, Decimal]] = {
    ("gemini", "gemini-2.5-flash-lite"): (Decimal("0.10"), Decimal("0.40")),
    ("groq", "openai/gpt-oss-20b"): (Decimal("0"), Decimal("0")),
    ("ollama", "llama3.2"): (Decimal("0"), Decimal("0")),
}
_PROVIDER_DEFAULTS: dict[str, tuple[Decimal, Decimal]] = {
    "gemini": (Decimal("0.10"), Decimal("0.40")),
    "groq": (Decimal("0.05"), Decimal("0.08")),
    "ollama": (Decimal("0"), Decimal("0")),
}
_UNKNOWN_PRICE = (Decimal("1"), Decimal("3"))


def estimate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> Decimal:
    input_price, output_price = _MODEL_PRICES.get((provider, model)) or _PROVIDER_DEFAULTS.get(provider) or _UNKNOWN_PRICE
    cost = (Decimal(input_tokens) / Decimal(1_000_000)) * input_price
    cost += (Decimal(output_tokens) / Decimal(1_000_000)) * output_price
    return cost.quantize(Decimal("0.000001"))


class UsageTracker:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record(self, entry: UsageRecord) -> None:
        self.db.add(
            AiUsageLog(
                organization_id=entry.organization_id if isinstance(entry.organization_id, uuid.UUID) else None,
                user_id=entry.user_id if isinstance(entry.user_id, uuid.UUID) else None,
                provider=entry.provider,
                model=entry.model,
                feature=entry.feature,
                input_tokens=entry.input_tokens,
                output_tokens=entry.output_tokens,
                estimated_cost_usd=entry.estimated_cost_usd,
                latency_ms=entry.latency_ms,
                status=entry.status,
                error_code=entry.error_category,
                fallback_from=entry.fallback_from,
                tokens_source=entry.tokens_source,
                cost_is_estimate=True,
            )
        )
        self.db.flush()
