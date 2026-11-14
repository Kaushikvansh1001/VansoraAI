import json
from collections.abc import Iterator

import httpx

from app.services.ai.base import estimate_tokens, send_json
from app.services.ai.exceptions import ProviderError
from app.services.ai.models import GenerationRequest, ProviderCapabilities, ProviderResponse, TokenUsage

_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str, client: httpx.Client, timeout: float = 30) -> None:
        self.api_key = api_key.strip()
        self.model = model
        self.client = client
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(text=True, stream=True, json_output=True, json_schema=True, tools=True)

    def generate(self, request: GenerationRequest) -> ProviderResponse:
        self._ensure_ready(request)
        body = self._body(request)
        payload = send_json(
            self.client,
            "POST",
            f"{_BASE}/models/{self.model}:generateContent",
            provider=self.name,
            headers=self._headers(),
            payload=body,
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
        names = []
        for item in payload.get("models") or []:
            if isinstance(item, dict) and item.get("name"):
                names.append(str(item["name"]).removeprefix("models/"))
        return names

    def _ensure_ready(self, request: GenerationRequest) -> None:
        if not self.configured:
            raise ProviderError(self.name, "not_configured", "GEMINI_API_KEY is not set.", recoverable=False)
        _reject_unsupported(self.name, self.capabilities(), request)

    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

    def _body(self, request: GenerationRequest) -> dict:
        body: dict = {"contents": [{"role": "user", "parts": [{"text": request.prompt}]}]}
        if request.json_schema is not None:
            body["generationConfig"] = {
                "responseMimeType": "application/json",
                "responseSchema": request.json_schema,
            }
        if request.tools:
            body["tools"] = [{"functionDeclarations": request.tools}]
        return body


def _reject_unsupported(provider: str, capabilities: ProviderCapabilities, request: GenerationRequest) -> None:
    if request.json_schema is not None and not capabilities.json_schema and not capabilities.json_output:
        raise ProviderError(provider, "unsupported", "Structured JSON is not available.", recoverable=False)
    if request.tools and not capabilities.tools:
        raise ProviderError(provider, "unsupported", "Tool calling is not available.", recoverable=False)


def _text_from_payload(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise ProviderError("gemini", "server_error", "Gemini returned no candidates.", recoverable=True)
    parts = ((candidates[0].get("content") or {}).get("parts") or [])
    texts = [str(part.get("text", "")) for part in parts if isinstance(part, dict)]
    text = "".join(texts).strip()
    if not text:
        raise ProviderError("gemini", "server_error", "Gemini returned an empty response.", recoverable=True)
    return text


def _usage(payload: dict, prompt: str, text: str) -> TokenUsage:
    metadata = payload.get("usageMetadata") or {}
    prompt_tokens = metadata.get("promptTokenCount")
    output_tokens = metadata.get("candidatesTokenCount")
    if isinstance(prompt_tokens, int) and isinstance(output_tokens, int):
        return TokenUsage(prompt_tokens, output_tokens, "provider")
    return TokenUsage(estimate_tokens(prompt), estimate_tokens(text or json.dumps(payload)), "estimated")
