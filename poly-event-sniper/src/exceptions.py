"""Custom exceptions for the poly-event-sniper trading system."""


class ExecutorError(Exception):
    """Base exception for executor-related errors."""

    pass


class AuthenticationError(ExecutorError):
    """Raised when API credentials are invalid or authentication fails."""

    pass


class ExecutionError(ExecutorError):
    """Raised when order execution fails."""

    pass


class OrderBookError(ExecutorError):
    """Raised when order book data is unavailable or invalid."""

    pass


class PriceValidationError(ExecutorError):
    """Raised when calculated price fails validation checks."""

    pass


class PositionSizeError(ExecutorError):
    """Raised when position size exceeds configured limits."""

    pass


class RateLimitError(ExecutorError):
    """Raised when rate limit is exceeded."""

    pass


# =============================================================================
# Ingestion Layer Exceptions
# =============================================================================


class IngestionError(Exception):
    """Base exception for ingestion-related errors."""

    pass


class ConnectionError(IngestionError):
    """Raised when WebSocket connection fails."""

    pass


class SubscriptionError(IngestionError):
    """Raised when subscription to market channel fails."""

    pass


class ReconnectionExhaustedError(IngestionError):
    """Raised when max reconnection attempts are exceeded."""

    pass


# =============================================================================
# Parser Layer Exceptions
# =============================================================================


class ParserError(Exception):
    """Base exception for parser-related errors."""

    pass


class InvalidEventError(ParserError):
    """Raised when event data cannot be parsed."""

    pass


class RuleConfigurationError(ParserError):
    """Raised when threshold rules are misconfigured."""

    pass


# =============================================================================
# Discovery Layer Exceptions
# =============================================================================


class DiscoveryError(Exception):
    """Base exception for discovery-related errors."""

    pass


class GammaAPIError(DiscoveryError):
    """Base exception for Gamma API errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GammaRateLimitError(GammaAPIError):
    """Raised when Gamma API returns 429 (rate limited).

    Attributes:
        retry_after: Seconds to wait before retrying (if provided by API).
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class GammaServerError(GammaAPIError):
    """Raised when Gamma API returns 5xx server error."""

    def __init__(
        self,
        message: str = "Server error",
        status_code: int = 500,
    ) -> None:
        super().__init__(message, status_code=status_code)
