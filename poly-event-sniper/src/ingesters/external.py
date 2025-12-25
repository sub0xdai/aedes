"""External event ingester for News/Social feeds."""

import asyncio
from collections.abc import AsyncIterator
from time import time

from loguru import logger

from src.interfaces.ingester import ExternalEventIngester
from src.models import EventType, MarketEvent


class ManualEventIngester(ExternalEventIngester):
    """Manual event ingester for testing and emergency overrides.

    Allows injecting events directly into the pipeline without
    requiring live API connections. Useful for:
    - Testing the signal generation pipeline
    - Manual "God Mode" overrides
    - Simulating external events

    Events are queued and yielded via stream() as they are injected.
    """

    def __init__(self, default_source: str = "manual") -> None:
        """Initialize the manual event ingester.

        Args:
            default_source: Default source identifier for injected events.
        """
        self._default_source = default_source
        self._queue: asyncio.Queue[MarketEvent] = asyncio.Queue()
        self._is_connected = False
        self._configured_sources: set[str] = set()

    async def connect(self) -> None:
        """Mark ingester as connected and ready to receive events."""
        self._is_connected = True
        logger.info("ManualEventIngester connected")

    async def disconnect(self) -> None:
        """Mark ingester as disconnected."""
        self._is_connected = False
        # Put a sentinel None to unblock any waiting stream consumers
        await self._queue.put(None)  # type: ignore[arg-type]
        logger.info("ManualEventIngester disconnected")

    async def configure(self, sources: list[str]) -> None:
        """Configure expected sources (for documentation/validation).

        Args:
            sources: List of source identifiers to expect.
        """
        self._configured_sources.update(sources)
        logger.info("Configured {} sources: {}", len(sources), sources)

    async def inject_event(
        self,
        content: str,
        source: str | None = None,
        event_type: EventType = EventType.NEWS,
    ) -> None:
        """Inject an event into the stream.

        Args:
            content: Text content of the event.
            source: Source identifier (uses default if not specified).
            event_type: Type of event (NEWS or SOCIAL).
        """
        event = MarketEvent(
            event_type=event_type,
            timestamp=time(),
            content=content,
            source=source or self._default_source,
        )

        await self._queue.put(event)
        logger.info(
            "Injected {} event from {}: {}",
            event_type.value,
            event.source,
            content[:50] + "..." if len(content) > 50 else content,
        )

    async def stream(self) -> AsyncIterator[MarketEvent]:
        """Stream events as they are injected.

        Yields:
            MarketEvent objects as they are added to the queue.
        """
        while self._is_connected:
            try:
                # Wait for event with timeout to allow checking is_connected
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)

                # None is sentinel for disconnect
                if event is None:
                    break

                yield event

            except asyncio.TimeoutError:
                # No event received, check if still connected and continue
                continue
            except asyncio.CancelledError:
                logger.info("Stream cancelled")
                break

    @property
    def is_connected(self) -> bool:
        """Check if ingester is connected."""
        return self._is_connected
