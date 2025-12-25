"""Abstract base classes defining ingester interfaces."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from src.exceptions import (
    ConnectionError,
    IngestionError,
    ReconnectionExhaustedError,
    SubscriptionError,
)
from src.models import MarketEvent

# Re-export exceptions for convenience
__all__ = [
    "BaseIngester",
    "MarketDataIngester",
    "ExternalEventIngester",
    "ConnectionError",
    "IngestionError",
    "ReconnectionExhaustedError",
    "SubscriptionError",
]


class BaseIngester(ABC):
    """Abstract base class for all ingester implementations.

    Defines the common lifecycle methods shared by all ingesters.
    Ingesters are async generators that yield MarketEvent objects.

    Subclasses:
        - MarketDataIngester: For market data feeds (WebSocket, etc.)
        - ExternalEventIngester: For external event feeds (News, Social)
    """

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the data source.

        Should handle authentication, WebSocket handshake, and any
        necessary warm-up operations.

        Raises:
            ConnectionError: If unable to connect to data source.
        """
        raise NotImplementedError

    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully close the connection.

        Should ensure all resources are properly released.
        """
        raise NotImplementedError

    @abstractmethod
    def stream(self) -> AsyncIterator[MarketEvent]:
        """Stream events as an async generator.

        Yields:
            MarketEvent objects as they arrive from the data source.

        Raises:
            ConnectionError: If connection is lost.
            ReconnectionExhaustedError: If reconnection attempts fail.
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if currently connected to data source."""
        raise NotImplementedError


class MarketDataIngester(BaseIngester):
    """Abstract base class for market data ingestion (Polymarket, etc.).

    Extends BaseIngester with token-based subscription for market feeds.
    """

    @abstractmethod
    async def subscribe(self, token_ids: list[str]) -> None:
        """Subscribe to market events for specified tokens.

        Args:
            token_ids: List of Polymarket token IDs to monitor.

        Raises:
            SubscriptionError: If subscription fails.
        """
        raise NotImplementedError


class ExternalEventIngester(BaseIngester):
    """Abstract base class for external event ingestion (News, Social).

    Extends BaseIngester with source configuration and manual event injection.
    """

    @abstractmethod
    async def configure(self, sources: list[str]) -> None:
        """Configure external event sources to monitor.

        Args:
            sources: List of source identifiers (e.g., RSS URLs, Twitter handles).

        Raises:
            SubscriptionError: If configuration fails.
        """
        raise NotImplementedError

    @abstractmethod
    async def inject_event(self, content: str, source: str = "manual") -> None:
        """Manually inject an event into the stream.

        Useful for testing the pipeline without live API keys,
        or for emergency manual overrides ("God Mode").

        Args:
            content: Text content of the event.
            source: Origin identifier for the event.
        """
        raise NotImplementedError
