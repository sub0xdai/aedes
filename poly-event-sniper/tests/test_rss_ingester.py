"""Tests for RssIngester."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ingesters.rss import RssIngester
from src.models import EventType, MarketEvent


class TestRssIngesterInit:
    """Test RssIngester initialization."""

    def test_default_poll_interval(self) -> None:
        """Test default poll interval is 60 seconds."""
        ingester = RssIngester()
        assert ingester.poll_interval == 60.0

    def test_custom_poll_interval(self) -> None:
        """Test custom poll interval."""
        ingester = RssIngester(poll_interval=30.0)
        assert ingester.poll_interval == 30.0

    def test_initially_disconnected(self) -> None:
        """Test ingester starts disconnected."""
        ingester = RssIngester()
        assert ingester.is_connected is False


class TestRssIngesterConfigure:
    """Test RssIngester configuration."""

    @pytest.mark.asyncio
    async def test_configure_stores_feed_urls(self) -> None:
        """Test that configure stores feed URLs."""
        ingester = RssIngester()
        await ingester.configure(["https://example.com/feed.xml"])
        assert "https://example.com/feed.xml" in ingester.feed_urls

    @pytest.mark.asyncio
    async def test_configure_multiple_feeds(self) -> None:
        """Test configuring multiple feed URLs."""
        ingester = RssIngester()
        await ingester.configure([
            "https://example.com/feed1.xml",
            "https://example.com/feed2.xml",
        ])
        assert len(ingester.feed_urls) == 2


class TestRssIngesterConnect:
    """Test RssIngester connection."""

    @pytest.mark.asyncio
    async def test_connect_marks_connected(self) -> None:
        """Test that connect marks ingester as connected."""
        ingester = RssIngester()
        await ingester.connect()
        assert ingester.is_connected is True
        await ingester.disconnect()

    @pytest.mark.asyncio
    async def test_disconnect_marks_disconnected(self) -> None:
        """Test that disconnect marks ingester as disconnected."""
        ingester = RssIngester()
        await ingester.connect()
        await ingester.disconnect()
        assert ingester.is_connected is False


class TestRssIngesterDeduplication:
    """Test RssIngester duplicate detection."""

    @pytest.mark.asyncio
    async def test_tracks_seen_entries(self) -> None:
        """Test that seen entries are tracked by GUID."""
        ingester = RssIngester()

        # Simulate marking an entry as seen
        ingester._mark_seen("entry-guid-123")

        assert ingester._is_seen("entry-guid-123") is True
        assert ingester._is_seen("entry-guid-456") is False

    @pytest.mark.asyncio
    async def test_uses_link_as_fallback_id(self) -> None:
        """Test that link is used as ID when no GUID present."""
        ingester = RssIngester()

        # Mock entry without GUID
        entry = MagicMock()
        entry.get = MagicMock(side_effect=lambda k, d=None: {
            "id": None,
            "link": "https://example.com/article/123",
        }.get(k, d))

        entry_id = ingester._get_entry_id(entry)
        assert entry_id == "https://example.com/article/123"


class TestRssIngesterEventGeneration:
    """Test RssIngester event generation."""

    @pytest.mark.asyncio
    async def test_creates_news_event_from_entry(self) -> None:
        """Test that RSS entries become NEWS events."""
        ingester = RssIngester()

        # Mock entry
        entry = MagicMock()
        entry.title = "Breaking News: Test Event"
        entry.link = "https://example.com/news/123"
        entry.get = MagicMock(return_value="guid-123")

        event = ingester._entry_to_event(entry, "Example Feed")

        assert event.event_type == EventType.NEWS
        assert event.content == "Breaking News: Test Event"
        assert event.source == "Example Feed"

    @pytest.mark.asyncio
    async def test_includes_link_in_raw_data(self) -> None:
        """Test that event raw_data includes the link."""
        ingester = RssIngester()

        entry = MagicMock()
        entry.title = "Test Article"
        entry.link = "https://example.com/article"
        entry.get = MagicMock(return_value="guid-456")

        event = ingester._entry_to_event(entry, "Test Feed")

        assert event.raw_data.get("link") == "https://example.com/article"


class TestRssIngesterInjectEvent:
    """Test RssIngester manual event injection."""

    @pytest.mark.asyncio
    async def test_inject_event_queues_event(self) -> None:
        """Test that inject_event adds event to queue."""
        ingester = RssIngester()
        await ingester.connect()

        await ingester.inject_event("Test content", source="test")

        # Should have one event in queue
        assert not ingester._queue.empty()
        await ingester.disconnect()


class TestRssIngesterStream:
    """Test RssIngester streaming with mocked feedparser."""

    @pytest.mark.asyncio
    async def test_stream_yields_new_entries(self) -> None:
        """Test that stream yields new RSS entries as events."""
        ingester = RssIngester(poll_interval=0.1)
        await ingester.configure(["https://example.com/feed.xml"])
        await ingester.connect()

        # Mock feedparser response
        mock_feed = MagicMock()
        mock_feed.feed.title = "Test Feed"
        mock_entry = MagicMock()
        mock_entry.title = "New Article"
        mock_entry.link = "https://example.com/article/1"
        mock_entry.get = MagicMock(return_value="guid-new-1")
        mock_feed.entries = [mock_entry]

        events_received: list[MarketEvent] = []

        with patch("src.ingesters.rss.feedparser.parse", return_value=mock_feed):
            # Collect events from stream (with timeout)
            async def collect_events() -> None:
                async for event in ingester.stream():
                    events_received.append(event)
                    if len(events_received) >= 1:
                        await ingester.disconnect()
                        break

            import asyncio
            try:
                await asyncio.wait_for(collect_events(), timeout=2.0)
            except asyncio.TimeoutError:
                await ingester.disconnect()

        assert len(events_received) >= 1
        assert events_received[0].event_type == EventType.NEWS
        assert events_received[0].content == "New Article"

    @pytest.mark.asyncio
    async def test_stream_skips_seen_entries(self) -> None:
        """Test that stream skips already-seen entries."""
        ingester = RssIngester(poll_interval=0.1)
        await ingester.configure(["https://example.com/feed.xml"])

        # Pre-mark entry as seen
        ingester._mark_seen("guid-old-1")

        await ingester.connect()

        # Mock feedparser with only the seen entry
        mock_feed = MagicMock()
        mock_feed.feed.title = "Test Feed"
        mock_entry = MagicMock()
        mock_entry.title = "Old Article"
        mock_entry.link = "https://example.com/article/old"
        mock_entry.get = MagicMock(return_value="guid-old-1")
        mock_feed.entries = [mock_entry]

        events_received: list[MarketEvent] = []
        poll_count = 0

        original_parse = None

        def mock_parse(url: str) -> MagicMock:
            nonlocal poll_count
            poll_count += 1
            return mock_feed

        with patch("src.ingesters.rss.feedparser.parse", side_effect=mock_parse):
            import asyncio

            async def collect_events() -> None:
                nonlocal poll_count
                async for event in ingester.stream():
                    events_received.append(event)
                # Wait for at least 2 poll cycles
                while poll_count < 2:
                    await asyncio.sleep(0.05)
                await ingester.disconnect()

            try:
                await asyncio.wait_for(collect_events(), timeout=2.0)
            except asyncio.TimeoutError:
                await ingester.disconnect()

        # Should have no events (entry was already seen)
        assert len(events_received) == 0
