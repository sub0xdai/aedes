"""Unit tests for the ingestion layer."""

import json

import pytest

from src.exceptions import SubscriptionError
from src.ingesters.polymarket import PolymarketIngester
from src.models import EventType, MarketEvent


class TestPolymarketIngester:
    """Test suite for PolymarketIngester."""

    @pytest.fixture
    def ingester(self) -> PolymarketIngester:
        """Create ingester instance."""
        return PolymarketIngester()

    def test_initial_state(self, ingester: PolymarketIngester) -> None:
        """Test initial ingester state."""
        assert ingester.is_connected is False
        assert len(ingester._subscribed_tokens) == 0

    def test_parse_book_message(self, ingester: PolymarketIngester) -> None:
        """Test parsing of book update message."""
        msg = json.dumps(
            {
                "event_type": "book",
                "asset_id": "token_123",
                "market": "market_456",
                "buys": [{"price": "0.45"}],
                "sells": [{"price": "0.55"}],
            }
        )

        event = ingester._parse_message(msg)

        assert event is not None
        assert event.event_type == EventType.BOOK_UPDATE
        assert event.token_id == "token_123"
        assert event.market_id == "market_456"
        assert event.best_bid == 0.45
        assert event.best_ask == 0.55

    def test_parse_price_change_message(self, ingester: PolymarketIngester) -> None:
        """Test parsing of price change message."""
        msg = json.dumps(
            {
                "event_type": "price_change",
                "asset_id": "token_123",
                "market": "market_456",
                "best_bid": "0.48",
                "best_ask": "0.52",
            }
        )

        event = ingester._parse_message(msg)

        assert event is not None
        assert event.event_type == EventType.PRICE_CHANGE
        assert event.best_bid == 0.48
        assert event.best_ask == 0.52

    def test_parse_last_trade_message(self, ingester: PolymarketIngester) -> None:
        """Test parsing of last trade price message."""
        msg = json.dumps(
            {
                "event_type": "last_trade_price",
                "asset_id": "token_123",
                "market": "market_456",
                "price": "0.55",
                "size": "100.0",
            }
        )

        event = ingester._parse_message(msg)

        assert event is not None
        assert event.event_type == EventType.LAST_TRADE
        assert event.last_price == 0.55
        assert event.last_size == 100.0

    def test_parse_invalid_json_returns_none(
        self, ingester: PolymarketIngester
    ) -> None:
        """Test that invalid JSON returns None."""
        assert ingester._parse_message("invalid json") is None

    def test_parse_empty_object_returns_none(
        self, ingester: PolymarketIngester
    ) -> None:
        """Test that empty object returns None."""
        assert ingester._parse_message("{}") is None

    def test_parse_unknown_event_type_returns_none(
        self, ingester: PolymarketIngester
    ) -> None:
        """Test that unknown event types return None."""
        msg = json.dumps(
            {
                "event_type": "unknown_event",
                "asset_id": "token_123",
                "market": "market_456",
            }
        )
        assert ingester._parse_message(msg) is None

    def test_parse_preserves_raw_data(self, ingester: PolymarketIngester) -> None:
        """Test that raw_data contains original payload."""
        msg = json.dumps(
            {
                "event_type": "price_change",
                "asset_id": "token_123",
                "market": "market_456",
                "best_bid": "0.48",
                "best_ask": "0.52",
                "extra_field": "extra_value",
            }
        )

        event = ingester._parse_message(msg)

        assert event is not None
        assert event.raw_data["extra_field"] == "extra_value"


class TestSafeFloat:
    """Test suite for safe float parsing."""

    @pytest.fixture
    def ingester(self) -> PolymarketIngester:
        """Create ingester instance."""
        return PolymarketIngester()

    def test_safe_float_valid_string(self, ingester: PolymarketIngester) -> None:
        """Test safe float parsing with valid string."""
        assert ingester._safe_float("0.5") == 0.5
        assert ingester._safe_float("1.0") == 1.0
        assert ingester._safe_float("0.001") == 0.001

    def test_safe_float_valid_number(self, ingester: PolymarketIngester) -> None:
        """Test safe float parsing with valid number."""
        assert ingester._safe_float(0.5) == 0.5
        assert ingester._safe_float(1) == 1.0

    def test_safe_float_none(self, ingester: PolymarketIngester) -> None:
        """Test safe float parsing with None."""
        assert ingester._safe_float(None) is None

    def test_safe_float_invalid_string(self, ingester: PolymarketIngester) -> None:
        """Test safe float parsing with invalid string."""
        assert ingester._safe_float("invalid") is None
        assert ingester._safe_float("") is None

    def test_safe_float_invalid_type(self, ingester: PolymarketIngester) -> None:
        """Test safe float parsing with invalid types."""
        assert ingester._safe_float({}) is None
        assert ingester._safe_float([]) is None


class TestIngesterConnection:
    """Test suite for ingester connection handling."""

    @pytest.mark.asyncio
    async def test_subscribe_without_connection_registers_tokens(self) -> None:
        """Test that subscribing without connection registers tokens for later."""
        ingester = PolymarketIngester()

        # Should not raise - registers tokens for subscription on connect
        await ingester.subscribe(["token_123"])
        assert "token_123" in ingester._subscribed_tokens

    @pytest.mark.asyncio
    async def test_stream_without_connection_raises(self) -> None:
        """Test that streaming without connection raises error."""
        from src.exceptions import ConnectionError

        ingester = PolymarketIngester()

        with pytest.raises(ConnectionError):
            async for _ in ingester.stream():
                pass


class TestMarketEventValidation:
    """Test suite for MarketEvent model validation."""

    def test_valid_market_event(self) -> None:
        """Test creating a valid MarketEvent."""
        event = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
            market_id="market_456",
            best_bid=0.45,
            best_ask=0.55,
        )
        assert event.token_id == "token_123"
        assert event.best_bid == 0.45

    def test_market_event_is_immutable(self) -> None:
        """Test that MarketEvent is frozen."""
        from pydantic import ValidationError

        event = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
            market_id="market_456",
        )
        with pytest.raises(ValidationError):
            event.token_id = "different_token"  # type: ignore[misc]

    def test_market_event_price_bounds(self) -> None:
        """Test that prices are bounded [0, 1]."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MarketEvent(
                event_type=EventType.PRICE_CHANGE,
                token_id="token_123",
                market_id="market_456",
                best_bid=1.5,  # Invalid: > 1
            )

        with pytest.raises(ValidationError):
            MarketEvent(
                event_type=EventType.PRICE_CHANGE,
                token_id="token_123",
                market_id="market_456",
                best_ask=-0.1,  # Invalid: < 0
            )
