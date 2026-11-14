from collections.abc import Iterator

import httpx

from app.services.ai.base import estimate_tokens, send_json
from app.services.ai.exceptions import ProviderError
from app.services.ai.models import GenerationRequest, ProviderCapabilities, ProviderResponse, TokenUsage
from app.services.ai.providers.gemini import _reject_unsupported


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str, model: str, client: httpx.Client, timeout: float = 30) -> None:
        self.base_url = base_url.strip().rstrip("/")
        self.model = model
        self.client = client
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(text=True, stream=True, json_output=True, json_schema=False, tools=False)

    def generate(self, request: GenerationRequest) -> ProviderResponse:
        self._ensure_ready(request)
        payload = send_json(
            self.client,
            "POST",
            f"{self.base_url}/api/chat",
            provider=self.name,
            headers={"Content-Type": "application/json"},
            payload=self._body(request),
            timeout=self.timeout,
        )
        text = str((payload.get("message") or {}).get("content") or "").strip()
        if not text:
            raise ProviderError(self.name, "server_error", "Ollama returned an empty response.", recoverable=True)
        return ProviderResponse(
            provider=self.name,
            model=self.model,
            text=text,
            usage=_usage(payload, request.prompt, text),
            latency_ms=0,
        )

    def stream(self, request: GenerationRequest) -> Iterator[str]:
        self._ensure_ready(request)
        text = self.generate(request).text
        if text:
            yield text

    def list_models(self, timeout: float) -> list[str]:
        if not self.configured:
            return []
        payload = send_json(
            self.client,
            "GET",
            f"{self.base_url}/api/tags",
            provider=self.name,
            headers={},
            payload=None,
            timeout=timeout,
        )
        return [str(item["name"]) for item in payload.get("models") or [] if isinstance(item, dict) and item.get("name")]

    def _ensure_ready(self, request: GenerationRequest) -> None:
        if not self.configured:
            raise ProviderError(self.name, "not_configured", "OLLAMA_BASE_URL is not set.", recoverable=False)
        _reject_unsupported(self.name, self.capabilities(), request)

    def _body(self, request: GenerationRequest) -> dict:
        body: dict = {
            "model": self.model,
            "messages": [{"role": "user", "content": request.prompt}],
            "stream": False,
        }
        if request.json_schema is not None:
            body["format"] = "json"
        return body


def _usage(payload: dict, prompt: str, text: str) -> TokenUsage:
    prompt_tokens = payload.get("prompt_eval_count")
    output_tokens = payload.get("eval_count")
    if isinstance(prompt_tokens, int) and isinstance(output_tokens, int):
        return TokenUsage(prompt_tokens, output_tokens, "provider")
    return TokenUsage(estimate_tokens(prompt), estimate_tokens(text), "estimated")
