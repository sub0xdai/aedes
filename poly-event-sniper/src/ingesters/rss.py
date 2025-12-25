"""RSS feed ingester for external news events."""

import asyncio
from collections.abc import AsyncIterator
from time import time
from typing import Any

import feedparser
from loguru import logger

from src.interfaces.ingester import ExternalEventIngester
from src.models import EventType, MarketEvent


class RssIngester(ExternalEventIngester):
    """RSS feed ingester for news events.

    Polls configured RSS feeds at a regular interval and yields
    new entries as MarketEvent objects. Tracks seen entries by
    GUID/link to prevent duplicates.

    Usage:
        ingester = RssIngester(poll_interval=60.0)
        await ingester.configure(["https://example.com/feed.xml"])
        await ingester.connect()

        async for event in ingester.stream():
            # Process event
            pass
    """

    def __init__(self, poll_interval: float = 60.0) -> None:
        """Initialize the RSS ingester.

        Args:
            poll_interval: Seconds between feed polls (default 60).
        """
        self._poll_interval = poll_interval
        self._feed_urls: list[str] = []
        self._seen_ids: set[str] = set()
        self._is_connected = False
        self._queue: asyncio.Queue[MarketEvent] = asyncio.Queue()

    @property
    def poll_interval(self) -> float:
        """Get the poll interval in seconds."""
        return self._poll_interval

    @property
    def feed_urls(self) -> list[str]:
        """Get configured feed URLs."""
        return self._feed_urls.copy()

    @property
    def is_connected(self) -> bool:
        """Check if ingester is connected."""
        return self._is_connected

    async def connect(self) -> None:
        """Mark ingester as connected and ready to poll."""
        self._is_connected = True
        logger.info("RssIngester connected with {} feeds", len(self._feed_urls))

    async def disconnect(self) -> None:
        """Mark ingester as disconnected."""
        self._is_connected = False
        # Put sentinel to unblock stream consumers
        await self._queue.put(None)  # type: ignore[arg-type]
        logger.info("RssIngester disconnected")

    async def configure(self, sources: list[str]) -> None:
        """Configure RSS feed URLs to monitor.

        Args:
            sources: List of RSS/Atom feed URLs.
        """
        self._feed_urls.extend(sources)
        logger.info("Configured {} RSS feeds: {}", len(sources), sources)

    async def inject_event(
        self,
        content: str,
        source: str = "manual",
        event_type: EventType = EventType.NEWS,
    ) -> None:
        """Manually inject an event into the stream.

        Args:
            content: Text content of the event.
            source: Source identifier.
            event_type: Type of event (default NEWS).
        """
        event = MarketEvent(
            event_type=event_type,
            timestamp=time(),
            content=content,
            source=source,
        )
        await self._queue.put(event)
        logger.info("Injected event from {}: {}", source, content[:50])

    def _is_seen(self, entry_id: str) -> bool:
        """Check if an entry has been seen before."""
        return entry_id in self._seen_ids

    def _mark_seen(self, entry_id: str) -> None:
        """Mark an entry as seen."""
        self._seen_ids.add(entry_id)

    def _get_entry_id(self, entry: Any) -> str:
        """Get unique identifier for an RSS entry.

        Uses GUID if available, falls back to link.

        Args:
            entry: feedparser entry object.

        Returns:
            Unique identifier string.
        """
        return entry.get("id") or entry.get("link") or str(hash(entry.get("title", "")))

    def _entry_to_event(self, entry: Any, feed_title: str) -> MarketEvent:
        """Convert an RSS entry to a MarketEvent.

        Args:
            entry: feedparser entry object.
            feed_title: Title of the source feed.

        Returns:
            MarketEvent with NEWS type.
        """
        return MarketEvent(
            event_type=EventType.NEWS,
            timestamp=time(),
            content=entry.title,
            source=feed_title,
            raw_data={
                "link": entry.link,
                "guid": self._get_entry_id(entry),
            },
        )

    async def _poll_feeds(self) -> None:
        """Poll all configured feeds for new entries."""
        for url in self._feed_urls:
            try:
                # feedparser.parse is synchronous, run in thread pool
                loop = asyncio.get_event_loop()
                feed = await loop.run_in_executor(None, feedparser.parse, url)

                feed_title = getattr(feed.feed, "title", url)

                for entry in feed.entries:
                    entry_id = self._get_entry_id(entry)

                    if self._is_seen(entry_id):
                        continue

                    self._mark_seen(entry_id)
                    event = self._entry_to_event(entry, feed_title)
                    await self._queue.put(event)

                    logger.debug(
                        "New RSS entry from {}: {}",
                        feed_title,
                        entry.title[:50] if hasattr(entry, "title") else "untitled",
                    )

            except Exception as e:
                logger.error("Failed to poll RSS feed {}: {}", url, str(e))

    async def stream(self) -> AsyncIterator[MarketEvent]:
        """Stream events from RSS feeds.

        Polls feeds at the configured interval and yields new entries.

        Yields:
            MarketEvent objects for new RSS entries.
        """
        # Start polling task
        async def poll_loop() -> None:
            while self._is_connected:
                await self._poll_feeds()
                await asyncio.sleep(self._poll_interval)

        poll_task = asyncio.create_task(poll_loop())

        try:
            while self._is_connected:
                try:
                    event = await asyncio.wait_for(self._queue.get(), timeout=1.0)

                    # None is sentinel for disconnect
                    if event is None:
                        break

                    yield event

                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break

        finally:
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError:
                pass
