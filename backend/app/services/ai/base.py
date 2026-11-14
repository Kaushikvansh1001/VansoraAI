import re

import httpx

from app.services.ai.exceptions import ProviderError

_SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_\-]{10,}"),
    re.compile(r"AQ\.[0-9A-Za-z_\-]{10,}"),
    re.compile(r"gsk_[0-9A-Za-z]{10,}"),
    re.compile(r"sk-[0-9A-Za-z]{10,}"),
    re.compile(r"sb_secret_[0-9A-Za-z_\-]{6,}"),
)


def redact(text: str) -> str:
    cleaned = text
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub("[redacted]", cleaned)
    return cleaned.replace("\n", " ")[:300]


def failure_from_status(provider: str, status: int, body: str) -> ProviderError:
    message = redact(body) or f"HTTP {status}"
    if status in {401, 403}:
        return ProviderError(provider, "invalid_credentials", message, recoverable=False, status_code=status)
    if status in {400, 404}:
        return ProviderError(provider, "invalid_model", message, recoverable=False, status_code=status)
    if status == 429:
        return ProviderError(provider, "rate_limit", message, recoverable=True, status_code=status)
    if status in {408, 500, 502, 503}:
        return ProviderError(provider, "server_error", message, recoverable=True, status_code=status)
    return ProviderError(provider, "server_error", message, recoverable=False, status_code=status)


def send_json(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    provider: str,
    headers: dict[str, str],
    payload: dict | None,
    timeout: float,
) -> dict:
    try:
        response = client.request(method, url, headers=headers, json=payload, timeout=timeout)
    except httpx.TimeoutException as exc:
        raise ProviderError(provider, "timeout", "The provider timed out.", recoverable=True) from exc
    except httpx.TransportError as exc:
        raise ProviderError(provider, "connection", "The provider could not be reached.", recoverable=True) from exc
    if response.status_code >= 400:
        raise failure_from_status(provider, response.status_code, response.text)
    try:
        body = response.json()
    except ValueError as exc:
        raise ProviderError(provider, "server_error", "The provider returned invalid JSON.", recoverable=True) from exc
    if not isinstance(body, dict):
        raise ProviderError(provider, "server_error", "The provider returned an unexpected payload.", recoverable=True)
    return body


def estimate_tokens(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return max(1, len(stripped) // 4)
