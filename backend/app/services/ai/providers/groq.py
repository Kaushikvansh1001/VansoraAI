from collections.abc import Iterator

import httpx

from app.services.ai.base import estimate_tokens, send_json
from app.services.ai.exceptions import ProviderError
from app.services.ai.models import GenerationRequest, ProviderCapabilities, ProviderResponse, TokenUsage
from app.services.ai.providers.gemini import _reject_unsupported

_BASE = "https://api.groq.com/openai/v1"


class GroqProvider:
    name = "groq"

    def __init__(self, api_key: str, model: str, client: httpx.Client, timeout: float = 30) -> None:
        self.api_key = api_key.strip()
        self.model = model
        self.client = client
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(text=True, stream=True, json_output=True, json_schema=False, tools=True)

    def generate(self, request: GenerationRequest) -> ProviderResponse:
        self._ensure_ready(request)
        payload = send_json(
            self.client,
            "POST",
            f"{_BASE}/chat/completions",
            provider=self.name,
            headers=self._headers(),
            payload=self._body(request),
            timeout=self.timeout,
        )
        text = _text_from_payload(payload)
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
            f"{_BASE}/models",
            provider=self.name,
            headers=self._headers(),
            payload=None,
            timeout=timeout,
        )
        return [str(item["id"]) for item in payload.get("data") or [] if isinstance(item, dict) and item.get("id")]

    def _ensure_ready(self, request: GenerationRequest) -> None:
        if not self.configured:
            raise ProviderError(self.name, "not_configured", "GROQ_API_KEY is not set.", recoverable=False)
        _reject_unsupported(self.name, self.capabilities(), request)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _body(self, request: GenerationRequest) -> dict:
        prompt = request.prompt
        if request.json_schema is not None:
            prompt = f"{prompt}\n\nReturn JSON matching this schema: {request.json_schema}"
        body: dict = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if request.json_schema is not None:
            body["response_format"] = {"type": "json_object"}
        if request.tools:
            body["tools"] = [{"type": "function", "function": tool} for tool in request.tools]
        return body


def _text_from_payload(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise ProviderError("groq", "server_error", "Groq returned no choices.", recoverable=True)
    message = choices[0].get("message") or {}
    text = str(message.get("content") or "").strip()
    if not text:
        raise ProviderError("groq", "server_error", "Groq returned an empty response.", recoverable=True)
    return text


def _usage(payload: dict, prompt: str, text: str) -> TokenUsage:
    usage = payload.get("usage") or {}
    prompt_tokens = usage.get("prompt_tokens")
    output_tokens = usage.get("completion_tokens")
    if isinstance(prompt_tokens, int) and isinstance(output_tokens, int):
        return TokenUsage(prompt_tokens, output_tokens, "provider")
    return TokenUsage(estimate_tokens(prompt), estimate_tokens(text), "estimated")
