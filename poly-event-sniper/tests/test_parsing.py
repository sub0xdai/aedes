"""Unit tests for the parsing layer."""

from time import sleep

import pytest
from pydantic import ValidationError

from src.models import EventType, MarketEvent, Side, ThresholdRule, TradeSignal
from src.parsers.threshold import PriceThresholdParser


class TestThresholdRuleValidation:
    """Test suite for ThresholdRule model validation."""

    def test_valid_rule_creation(self) -> None:
        """Test creating a valid threshold rule."""
        rule = ThresholdRule(
            token_id="token_123",
            trigger_side=Side.BUY,
            threshold=0.30,
            comparison="below",
            size_usdc=100.0,
        )
        assert rule.token_id == "token_123"
        assert rule.threshold == 0.30

    def test_threshold_must_be_between_0_and_1(self) -> None:
        """Test threshold must be in (0, 1) range."""
        with pytest.raises(ValidationError):
            ThresholdRule(
                token_id="token_123",
                trigger_side=Side.BUY,
                threshold=1.5,  # Invalid: > 1
                comparison="below",
                size_usdc=100.0,
            )

        with pytest.raises(ValidationError):
            ThresholdRule(
                token_id="token_123",
                trigger_side=Side.BUY,
                threshold=0.0,  # Invalid: = 0
                comparison="below",
                size_usdc=100.0,
            )

    def test_rule_is_immutable(self) -> None:
        """Test that ThresholdRule is frozen."""
        rule = ThresholdRule(
            token_id="token_123",
            trigger_side=Side.BUY,
            threshold=0.30,
            comparison="below",
            size_usdc=100.0,
        )
        with pytest.raises(ValidationError):
            rule.threshold = 0.50  # type: ignore[misc]


class TestPriceThresholdParser:
    """Test suite for PriceThresholdParser."""

    @pytest.fixture
    def buy_below_rule(self) -> ThresholdRule:
        """Create a rule to BUY when price drops below 0.30."""
        return ThresholdRule(
            token_id="token_123",
            trigger_side=Side.BUY,
            threshold=0.30,
            comparison="below",
            size_usdc=100.0,
            cooldown_seconds=0.1,  # Short cooldown for testing
        )

    @pytest.fixture
    def sell_above_rule(self) -> ThresholdRule:
        """Create a rule to SELL when price rises above 0.70."""
        return ThresholdRule(
            token_id="token_123",
            trigger_side=Side.SELL,
            threshold=0.70,
            comparison="above",
            size_usdc=50.0,
            cooldown_seconds=0.1,
        )

    @pytest.fixture
    def parser_buy_below(self, buy_below_rule: ThresholdRule) -> PriceThresholdParser:
        """Create parser with buy-below rule."""
        return PriceThresholdParser([buy_below_rule])

    @pytest.fixture
    def parser_sell_above(self, sell_above_rule: ThresholdRule) -> PriceThresholdParser:
        """Create parser with sell-above rule."""
        return PriceThresholdParser([sell_above_rule])

    def test_no_signal_when_price_above_threshold(
        self, parser_buy_below: PriceThresholdParser
    ) -> None:
        """Test that no signal is generated when price is above threshold."""
        event = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
            market_id="market_456",
            best_bid=0.48,
            best_ask=0.52,
        )

        signal = parser_buy_below.evaluate(event)
        assert signal is None

    def test_signal_when_price_crosses_below_threshold(
        self, parser_buy_below: PriceThresholdParser
    ) -> None:
        """Test signal generation when price crosses below threshold."""
        # First event: price above threshold (sets baseline)
        event1 = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
            market_id="market_456",
            best_bid=0.33,
            best_ask=0.37,
        )
        parser_buy_below.evaluate(event1)

        # Second event: price crosses below threshold
        event2 = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
            market_id="market_456",
            best_bid=0.25,
            best_ask=0.29,
        )

        signal = parser_buy_below.evaluate(event2)

        assert signal is not None
        assert signal.side == Side.BUY
        assert signal.token_id == "token_123"
        assert signal.size_usdc == 100.0

    def test_signal_when_price_crosses_above_threshold(
        self, parser_sell_above: PriceThresholdParser
    ) -> None:
        """Test signal generation when price crosses above threshold."""
        # First event: price below threshold (sets baseline)
        event1 = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
            market_id="market_456",
            best_bid=0.63,
            best_ask=0.67,
        )
        parser_sell_above.evaluate(event1)

        # Second event: price crosses above threshold
        event2 = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
            market_id="market_456",
            best_bid=0.73,
            best_ask=0.77,
        )

        signal = parser_sell_above.evaluate(event2)

        assert signal is not None
        assert signal.side == Side.SELL
        assert signal.size_usdc == 50.0

    def test_cooldown_prevents_rapid_signals(
        self, parser_buy_below: PriceThresholdParser
    ) -> None:
        """Test that cooldown prevents rapid signal generation."""
        # Set baseline above threshold
        above_event = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
            market_id="market_456",
            best_bid=0.33,
            best_ask=0.37,
        )
        parser_buy_below.evaluate(above_event)

        # Cross below threshold
        below_event = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
            market_id="market_456",
            best_bid=0.25,
            best_ask=0.29,
        )

        # First signal should trigger
        signal1 = parser_buy_below.evaluate(below_event)
        assert signal1 is not None

        # Go back above threshold
        parser_buy_below.evaluate(above_event)

        # Immediate second crossing should be blocked by cooldown
        signal2 = parser_buy_below.evaluate(below_event)
        assert signal2 is None

        # Wait for cooldown to expire
        sleep(0.15)

        # Reset by going above threshold
        parser_buy_below.evaluate(above_event)

        # Now crossing should work again
        signal3 = parser_buy_below.evaluate(below_event)
        assert signal3 is not None

    def test_reset_clears_state(self, parser_buy_below: PriceThresholdParser) -> None:
        """Test that reset clears parser state."""
        event = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
            market_id="market_456",
            best_bid=0.25,
            best_ask=0.29,
        )

        parser_buy_below.evaluate(event)
        assert len(parser_buy_below._last_price) > 0

        parser_buy_below.reset()

        assert len(parser_buy_below._last_price) == 0
        assert len(parser_buy_below._last_trigger) == 0

    def test_ignores_untracked_tokens(
        self, parser_buy_below: PriceThresholdParser
    ) -> None:
        """Test that parser ignores events for untracked tokens."""
        event = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="other_token",  # Not in rules
            market_id="market_456",
            best_bid=0.10,
            best_ask=0.15,
        )

        signal = parser_buy_below.evaluate(event)
        assert signal is None

    def test_ignores_irrelevant_event_types(
        self, parser_buy_below: PriceThresholdParser
    ) -> None:
        """Test that parser ignores tick size change events."""
        event = MarketEvent(
            event_type=EventType.TICK_SIZE_CHANGE,
            token_id="token_123",
            market_id="market_456",
        )

        signal = parser_buy_below.evaluate(event)
        assert signal is None

    def test_uses_last_trade_price_fallback(
        self, parser_buy_below: PriceThresholdParser
    ) -> None:
        """Test that parser uses last_price when bid/ask unavailable."""
        # Set baseline
        event1 = MarketEvent(
            event_type=EventType.LAST_TRADE,
            token_id="token_123",
            market_id="market_456",
            last_price=0.35,
        )
        parser_buy_below.evaluate(event1)

        # Cross below with last_price only
        event2 = MarketEvent(
            event_type=EventType.LAST_TRADE,
            token_id="token_123",
            market_id="market_456",
            last_price=0.25,
        )

        signal = parser_buy_below.evaluate(event2)
        assert signal is not None

    def test_no_signal_without_price_data(
        self, parser_buy_below: PriceThresholdParser
    ) -> None:
        """Test that no signal is generated when price data is missing."""
        event = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
            market_id="market_456",
            # No price data
        )

        signal = parser_buy_below.evaluate(event)
        assert signal is None


class TestMultiRuleParser:
    """Test parser with multiple rules."""

    def test_multiple_rules_same_token(self) -> None:
        """Test parser with multiple rules for same token."""
        rules = [
            ThresholdRule(
                token_id="token_123",
                trigger_side=Side.BUY,
                threshold=0.30,
                comparison="below",
                size_usdc=100.0,
                cooldown_seconds=0.1,
            ),
            ThresholdRule(
                token_id="token_123",
                trigger_side=Side.SELL,
                threshold=0.70,
                comparison="above",
                size_usdc=50.0,
                cooldown_seconds=0.1,
            ),
        ]

        parser = PriceThresholdParser(rules)

        # Set baseline (mid-range price)
        baseline = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
            market_id="market_456",
            best_bid=0.48,
            best_ask=0.52,
        )
        parser.evaluate(baseline)

        # Price high enough to trigger sell
        high_event = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
            market_id="market_456",
            best_bid=0.73,
            best_ask=0.77,
        )

        signal = parser.evaluate(high_event)
        assert signal is not None
        assert signal.side == Side.SELL

    def test_multiple_tokens(self) -> None:
        """Test parser with rules for different tokens."""
        rules = [
            ThresholdRule(
                token_id="token_A",
                trigger_side=Side.BUY,
                threshold=0.30,
                comparison="below",
                size_usdc=100.0,
            ),
            ThresholdRule(
                token_id="token_B",
                trigger_side=Side.SELL,
                threshold=0.70,
                comparison="above",
                size_usdc=50.0,
            ),
        ]

        parser = PriceThresholdParser(rules)

        # Token A event should not affect token B rules
        event_a = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_A",
            market_id="market_456",
            best_bid=0.73,
            best_ask=0.77,  # Would trigger token_B's rule if applied
        )

        signal = parser.evaluate(event_a)
        assert signal is None  # No signal because token_A rule is "below 0.30"
