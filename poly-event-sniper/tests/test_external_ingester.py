"""Tests for the ExternalEventIngester (News/Social event injection)."""

import asyncio

import pytest

from src.ingesters.external import ManualEventIngester
from src.models import EventType, MarketEvent


class TestManualEventIngesterInit:
    """Tests for ManualEventIngester initialization."""

    def test_initial_state(self) -> None:
        """Ingester should start disconnected with empty queue."""
        ingester = ManualEventIngester()
        assert ingester.is_connected is False

    def test_default_source(self) -> None:
        """Ingester should have configurable default source."""
        ingester = ManualEventIngester(default_source="twitter")
        assert ingester._default_source == "twitter"


class TestManualEventIngesterLifecycle:
    """Tests for connect/disconnect lifecycle."""

    @pytest.mark.asyncio
    async def test_connect(self) -> None:
        """Connect should mark ingester as connected."""
        ingester = ManualEventIngester()
        await ingester.connect()
        assert ingester.is_connected is True

    @pytest.mark.asyncio
    async def test_disconnect(self) -> None:
        """Disconnect should mark ingester as disconnected."""
        ingester = ManualEventIngester()
        await ingester.connect()
        await ingester.disconnect()
        assert ingester.is_connected is False

    @pytest.mark.asyncio
    async def test_configure_stores_sources(self) -> None:
        """Configure should store source identifiers."""
        ingester = ManualEventIngester()
        await ingester.configure(["reuters", "bloomberg"])
        assert "reuters" in ingester._configured_sources
        assert "bloomberg" in ingester._configured_sources


class TestManualEventIngesterInjectEvent:
    """Tests for inject_event functionality."""

    @pytest.mark.asyncio
    async def test_inject_event_creates_market_event(self) -> None:
        """Injected events should be available in stream."""
        ingester = ManualEventIngester()
        await ingester.connect()

        await ingester.inject_event("FED raises rates by 25bp", source="reuters")

        # Get event from stream
        event = await asyncio.wait_for(ingester._queue.get(), timeout=1.0)

        assert event.event_type == EventType.NEWS
        assert event.content == "FED raises rates by 25bp"
        assert event.source == "reuters"
        assert event.token_id is None
        assert event.market_id is None

    @pytest.mark.asyncio
    async def test_inject_event_uses_default_source(self) -> None:
        """Injected events should use default source if not specified."""
        ingester = ManualEventIngester(default_source="manual")
        await ingester.connect()

        await ingester.inject_event("Breaking news")

        event = await asyncio.wait_for(ingester._queue.get(), timeout=1.0)
        assert event.source == "manual"

    @pytest.mark.asyncio
    async def test_inject_event_with_social_type(self) -> None:
        """Should support SOCIAL event type."""
        ingester = ManualEventIngester()
        await ingester.connect()

        await ingester.inject_event(
            "@elonmusk: Crypto to the moon!",
            source="twitter",
            event_type=EventType.SOCIAL,
        )

        event = await asyncio.wait_for(ingester._queue.get(), timeout=1.0)
        assert event.event_type == EventType.SOCIAL
        assert event.source == "twitter"

    @pytest.mark.asyncio
    async def test_inject_multiple_events(self) -> None:
        """Multiple injected events should queue in order."""
        ingester = ManualEventIngester()
        await ingester.connect()

        await ingester.inject_event("Event 1")
        await ingester.inject_event("Event 2")
        await ingester.inject_event("Event 3")

        event1 = await asyncio.wait_for(ingester._queue.get(), timeout=1.0)
        event2 = await asyncio.wait_for(ingester._queue.get(), timeout=1.0)
        event3 = await asyncio.wait_for(ingester._queue.get(), timeout=1.0)

        assert event1.content == "Event 1"
        assert event2.content == "Event 2"
        assert event3.content == "Event 3"


class TestManualEventIngesterStream:
    """Tests for stream functionality."""

    @pytest.mark.asyncio
    async def test_stream_yields_injected_events(self) -> None:
        """Stream should yield events as they are injected."""
        ingester = ManualEventIngester()
        await ingester.connect()

        # Inject event before starting stream
        await ingester.inject_event("Test event")

        # Get first event from stream
        async for event in ingester.stream():
            assert event.content == "Test event"
            break  # Exit after first event

    @pytest.mark.asyncio
    async def test_stream_waits_for_events(self) -> None:
        """Stream should wait for events with timeout."""
        ingester = ManualEventIngester()
        await ingester.connect()

        # Start stream task
        events_received: list[MarketEvent] = []

        async def consume_stream() -> None:
            async for event in ingester.stream():
                events_received.append(event)
                if len(events_received) >= 2:
                    break

        stream_task = asyncio.create_task(consume_stream())

        # Give stream time to start
        await asyncio.sleep(0.01)

        # Inject events
        await ingester.inject_event("Event A")
        await ingester.inject_event("Event B")

        # Wait for stream to receive events
        await asyncio.wait_for(stream_task, timeout=1.0)

        assert len(events_received) == 2
        assert events_received[0].content == "Event A"
        assert events_received[1].content == "Event B"

    @pytest.mark.asyncio
    async def test_stream_stops_on_disconnect(self) -> None:
        """Stream should stop when disconnected."""
        ingester = ManualEventIngester()
        await ingester.connect()

        events_received: list[MarketEvent] = []

        async def consume_stream() -> None:
            async for event in ingester.stream():
                events_received.append(event)

        stream_task = asyncio.create_task(consume_stream())

        # Inject one event
        await ingester.inject_event("Event 1")
        await asyncio.sleep(0.01)

        # Disconnect should stop the stream
        await ingester.disconnect()

        # Stream task should complete
        await asyncio.wait_for(stream_task, timeout=1.0)

        assert len(events_received) == 1
