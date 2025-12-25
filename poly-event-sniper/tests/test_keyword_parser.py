"""Tests for the KeywordParser (News-to-Trade signal generation)."""

import pytest

from src.models import EventType, MarketEvent, Side, TradeSignal
from src.parsers.keyword import KeywordParser, KeywordRule


class TestKeywordRuleValidation:
    """Tests for KeywordRule model validation."""

    def test_valid_rule_creation(self) -> None:
        """Valid rule should be created successfully."""
        rule = KeywordRule(
            keyword="FED HIKE",
            token_id="token_fed_123",
            trigger_side=Side.BUY,
            size_usdc=100.0,
        )
        assert rule.keyword == "FED HIKE"
        assert rule.token_id == "token_fed_123"
        assert rule.trigger_side == Side.BUY
        assert rule.size_usdc == 100.0

    def test_rule_case_sensitivity_default(self) -> None:
        """Rules should be case-insensitive by default."""
        rule = KeywordRule(
            keyword="crypto",
            token_id="token_123",
            trigger_side=Side.BUY,
            size_usdc=50.0,
        )
        assert rule.case_sensitive is False

    def test_rule_is_immutable(self) -> None:
        """Rules should be immutable (frozen)."""
        rule = KeywordRule(
            keyword="test",
            token_id="token_123",
            trigger_side=Side.BUY,
            size_usdc=50.0,
        )
        with pytest.raises(Exception):  # ValidationError for frozen model
            rule.keyword = "changed"  # type: ignore[misc]


class TestKeywordParserInit:
    """Tests for KeywordParser initialization."""

    def test_init_with_rules(self) -> None:
        """Parser should store rules on initialization."""
        rules = [
            KeywordRule(
                keyword="inflation",
                token_id="token_cpi",
                trigger_side=Side.BUY,
                size_usdc=100.0,
            ),
        ]
        parser = KeywordParser(rules)
        assert len(parser._rules) == 1

    def test_init_empty_rules(self) -> None:
        """Parser should accept empty rule list."""
        parser = KeywordParser([])
        assert len(parser._rules) == 0


class TestKeywordParserEvaluate:
    """Tests for KeywordParser.evaluate method."""

    @pytest.fixture
    def parser(self) -> KeywordParser:
        """Create parser with sample rules."""
        rules = [
            KeywordRule(
                keyword="FED HIKE",
                token_id="token_fed_rates",
                trigger_side=Side.BUY,
                size_usdc=100.0,
                reason_template="FED rate hike detected",
            ),
            KeywordRule(
                keyword="RECESSION",
                token_id="token_recession",
                trigger_side=Side.SELL,
                size_usdc=75.0,
                reason_template="Recession keyword detected",
            ),
            KeywordRule(
                keyword="bitcoin",
                token_id="token_btc",
                trigger_side=Side.BUY,
                size_usdc=50.0,
                case_sensitive=False,
            ),
        ]
        return KeywordParser(rules)

    def test_no_signal_for_market_events(self, parser: KeywordParser) -> None:
        """Parser should ignore market data events."""
        event = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="some_token",
            market_id="some_market",
            best_bid=0.5,
            best_ask=0.52,
        )
        signal = parser.evaluate(event)
        assert signal is None

    def test_no_signal_when_no_match(self, parser: KeywordParser) -> None:
        """Parser should return None when no keywords match."""
        event = MarketEvent(
            event_type=EventType.NEWS,
            content="Weather forecast: sunny skies ahead",
            source="weather_api",
        )
        signal = parser.evaluate(event)
        assert signal is None

    def test_signal_on_keyword_match(self, parser: KeywordParser) -> None:
        """Parser should generate signal when keyword matches."""
        event = MarketEvent(
            event_type=EventType.NEWS,
            content="Breaking: FED HIKE of 25 basis points announced",
            source="reuters",
        )
        signal = parser.evaluate(event)

        assert signal is not None
        assert signal.token_id == "token_fed_rates"
        assert signal.side == Side.BUY
        assert signal.size_usdc == 100.0
        assert "FED rate hike detected" in signal.reason

    def test_case_insensitive_match(self, parser: KeywordParser) -> None:
        """Parser should match case-insensitively when configured."""
        event = MarketEvent(
            event_type=EventType.NEWS,
            content="BITCOIN price surges to new highs",
            source="crypto_news",
        )
        signal = parser.evaluate(event)

        assert signal is not None
        assert signal.token_id == "token_btc"

    def test_first_match_wins(self, parser: KeywordParser) -> None:
        """When multiple keywords match, first rule wins."""
        # Create parser where multiple rules could match
        rules = [
            KeywordRule(
                keyword="crypto",
                token_id="token_crypto_general",
                trigger_side=Side.BUY,
                size_usdc=50.0,
            ),
            KeywordRule(
                keyword="bitcoin",
                token_id="token_btc_specific",
                trigger_side=Side.BUY,
                size_usdc=100.0,
            ),
        ]
        parser = KeywordParser(rules)

        event = MarketEvent(
            event_type=EventType.NEWS,
            content="Bitcoin and crypto markets rally",
            source="news",
        )
        signal = parser.evaluate(event)

        # "crypto" rule is first, so it should win
        assert signal is not None
        assert signal.token_id == "token_crypto_general"

    def test_social_event_type(self, parser: KeywordParser) -> None:
        """Parser should process SOCIAL events."""
        event = MarketEvent(
            event_type=EventType.SOCIAL,
            content="@analyst: FED HIKE coming tomorrow!",
            source="twitter",
        )
        signal = parser.evaluate(event)

        assert signal is not None
        assert signal.token_id == "token_fed_rates"

    def test_no_signal_when_content_is_none(self, parser: KeywordParser) -> None:
        """Parser should handle None content gracefully."""
        event = MarketEvent(
            event_type=EventType.NEWS,
            content=None,
            source="unknown",
        )
        signal = parser.evaluate(event)
        assert signal is None

    def test_cooldown_prevents_rapid_signals(self) -> None:
        """Parser should respect cooldown between signals."""
        rules = [
            KeywordRule(
                keyword="alert",
                token_id="token_alert",
                trigger_side=Side.BUY,
                size_usdc=50.0,
                cooldown_seconds=60.0,
            ),
        ]
        parser = KeywordParser(rules)

        event1 = MarketEvent(
            event_type=EventType.NEWS,
            content="Alert: something happened",
            source="news",
        )
        event2 = MarketEvent(
            event_type=EventType.NEWS,
            content="Another alert: more news",
            source="news",
        )

        signal1 = parser.evaluate(event1)
        signal2 = parser.evaluate(event2)

        assert signal1 is not None
        assert signal2 is None  # Blocked by cooldown


class TestKeywordParserReset:
    """Tests for KeywordParser.reset method."""

    def test_reset_clears_cooldowns(self) -> None:
        """Reset should clear cooldown state."""
        rules = [
            KeywordRule(
                keyword="test",
                token_id="token_test",
                trigger_side=Side.BUY,
                size_usdc=50.0,
                cooldown_seconds=60.0,
            ),
        ]
        parser = KeywordParser(rules)

        event = MarketEvent(
            event_type=EventType.NEWS,
            content="test content",
            source="news",
        )

        # First should trigger
        signal1 = parser.evaluate(event)
        assert signal1 is not None

        # Second should be blocked
        signal2 = parser.evaluate(event)
        assert signal2 is None

        # Reset and try again
        parser.reset()
        signal3 = parser.evaluate(event)
        assert signal3 is not None
