class ProviderError(Exception):
    """A single provider failed. Recoverable errors may be retried or sent to the fallback."""

    def __init__(
        self,
        provider: str,
        category: str,
        message: str,
        *,
        recoverable: bool,
        status_code: int | None = None,
    ) -> None:
        self.provider = provider
        self.category = category
        self.message = message
        self.recoverable = recoverable
        self.status_code = status_code
        super().__init__(f"{provider}: {category}: {message}")


class ProviderChainFailed(Exception):
    """Every configured provider failed. The message lists categories, not secrets or prompts."""

    def __init__(self, errors: list[ProviderError]) -> None:
        self.errors = errors
        summary = "; ".join(f"{error.provider}: {error.category}" for error in errors) or "no providers configured"
        super().__init__(summary)


class EmbeddingError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
