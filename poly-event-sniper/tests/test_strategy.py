"""Tests for Phase 7.4 Strategy interface and ParserStrategyAdapter."""

import pytest

from src.interfaces.parser import BaseParser
from src.interfaces.strategy import BaseStrategy
from src.models import (
    EventType,
    ExecutionResult,
    MarketEvent,
    Order,
    OrderStatus,
    OrderType,
    Side,
    TradeSignal,
)
from src.strategies.parser_adapter import ParserStrategyAdapter


class MockParser(BaseParser):
    """Mock parser that returns signal when token matches."""

    def __init__(self, token_to_signal: dict[str, TradeSignal | None]) -> None:
        self._token_to_signal = token_to_signal
        self.reset_called = False

    def evaluate(self, event: MarketEvent) -> TradeSignal | None:
        if event.token_id is None:
            return None
        return self._token_to_signal.get(event.token_id)

    def reset(self) -> None:
        self.reset_called = True


class TestBaseStrategyInterface:
    """Tests for BaseStrategy ABC."""

    def test_base_strategy_is_abstract(self) -> None:
        """BaseStrategy cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseStrategy()  # type: ignore[abstract]

    def test_base_strategy_requires_on_tick(self) -> None:
        """Subclass must implement on_tick."""
        class IncompleteStrategy(BaseStrategy):
            def on_fill(self, order: Order, result: ExecutionResult) -> None:
                pass

            def generate_signals(self) -> list[Order]:
                return []

            def reset(self) -> None:
                pass

            @property
            def name(self) -> str:
                return "test"

        with pytest.raises(TypeError):
            IncompleteStrategy()  # type: ignore[abstract]


class TestParserStrategyAdapter:
    """Tests for ParserStrategyAdapter."""

    @pytest.fixture
    def sample_signal(self) -> TradeSignal:
        """Create a sample trade signal."""
        return TradeSignal(
            token_id="token_123",
            side=Side.BUY,
            size_usdc=100.0,
            reason="Test signal",
        )

    @pytest.fixture
    def sample_event(self) -> MarketEvent:
        """Create a sample market event."""
        return MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
            best_bid=0.45,
            best_ask=0.55,
        )

    def test_adapter_implements_base_strategy(
        self, sample_signal: TradeSignal
    ) -> None:
        """ParserStrategyAdapter should implement BaseStrategy."""
        parser = MockParser({"token_123": sample_signal})
        adapter = ParserStrategyAdapter(parser)
        assert isinstance(adapter, BaseStrategy)

    def test_adapter_name_includes_parser_class(
        self, sample_signal: TradeSignal
    ) -> None:
        """Adapter name should include wrapped parser class name."""
        parser = MockParser({"token_123": sample_signal})
        adapter = ParserStrategyAdapter(parser)
        assert "MockParser" in adapter.name
        assert adapter.name == "adapted_MockParser"

    def test_on_tick_evaluates_parser(
        self, sample_signal: TradeSignal, sample_event: MarketEvent
    ) -> None:
        """on_tick should call parser.evaluate."""
        parser = MockParser({"token_123": sample_signal})
        adapter = ParserStrategyAdapter(parser)

        # on_tick should store signal for generate_signals
        adapter.on_tick(sample_event)

        # Signal should be available from generate_signals
        orders = adapter.generate_signals()
        assert len(orders) == 1

    def test_on_tick_no_signal_no_order(self, sample_event: MarketEvent) -> None:
        """on_tick with no signal should produce no orders."""
        parser = MockParser({})  # No signals
        adapter = ParserStrategyAdapter(parser)

        adapter.on_tick(sample_event)
        orders = adapter.generate_signals()
        assert len(orders) == 0

    def test_generate_signals_converts_to_order(
        self, sample_signal: TradeSignal, sample_event: MarketEvent
    ) -> None:
        """generate_signals should convert TradeSignal to Order."""
        parser = MockParser({"token_123": sample_signal})
        adapter = ParserStrategyAdapter(parser)

        adapter.on_tick(sample_event)
        orders = adapter.generate_signals()

        assert len(orders) == 1
        order = orders[0]

        assert isinstance(order, Order)
        assert order.token_id == sample_signal.token_id
        assert order.side == sample_signal.side
        assert order.reason == sample_signal.reason
        assert order.order_type == OrderType.FOK

    def test_generate_signals_clears_pending(
        self, sample_signal: TradeSignal, sample_event: MarketEvent
    ) -> None:
        """generate_signals should clear pending signal after returning."""
        parser = MockParser({"token_123": sample_signal})
        adapter = ParserStrategyAdapter(parser)

        adapter.on_tick(sample_event)
        orders1 = adapter.generate_signals()
        assert len(orders1) == 1

        # Second call should return empty
        orders2 = adapter.generate_signals()
        assert len(orders2) == 0

    def test_on_fill_is_passthrough(
        self, sample_signal: TradeSignal
    ) -> None:
        """on_fill should not raise (parsers are stateless)."""
        parser = MockParser({"token_123": sample_signal})
        adapter = ParserStrategyAdapter(parser)

        order = Order(
            token_id="token_123",
            side=Side.BUY,
            quantity=100.0,
            reason="Test",
        )
        result = ExecutionResult(
            order_id="order_123",
            status=OrderStatus.FILLED,
            filled_price=0.50,
        )

        # Should not raise
        adapter.on_fill(order, result)

    def test_reset_propagates_to_parser(
        self, sample_signal: TradeSignal
    ) -> None:
        """reset should call parser.reset."""
        parser = MockParser({"token_123": sample_signal})
        adapter = ParserStrategyAdapter(parser)

        assert not parser.reset_called
        adapter.reset()
        assert parser.reset_called

    def test_reset_clears_pending_signal(
        self, sample_signal: TradeSignal, sample_event: MarketEvent
    ) -> None:
        """reset should clear any pending signal."""
        parser = MockParser({"token_123": sample_signal})
        adapter = ParserStrategyAdapter(parser)

        adapter.on_tick(sample_event)
        adapter.reset()

        # Should have no pending signal
        orders = adapter.generate_signals()
        assert len(orders) == 0

    def test_quantity_calculated_from_size_and_price(
        self, sample_event: MarketEvent
    ) -> None:
        """Order quantity should be calculated from size_usdc."""
        signal = TradeSignal(
            token_id="token_123",
            side=Side.BUY,
            size_usdc=100.0,
            reason="Test",
        )
        parser = MockParser({"token_123": signal})
        adapter = ParserStrategyAdapter(parser)

        adapter.on_tick(sample_event)
        orders = adapter.generate_signals()

        # Quantity = size_usdc / mid_price (or 0.5 if no price)
        # Event has bid=0.45, ask=0.55, so mid=0.50
        # quantity = 100 / 0.50 = 200
        assert len(orders) == 1
        assert orders[0].quantity == pytest.approx(200.0)

    def test_quantity_uses_default_when_no_price(self) -> None:
        """Quantity should use 0.5 when event has no price data."""
        signal = TradeSignal(
            token_id="token_123",
            side=Side.BUY,
            size_usdc=100.0,
            reason="Test",
        )
        event = MarketEvent(
            event_type=EventType.NEWS,
            token_id="token_123",
            # No price data
        )
        parser = MockParser({"token_123": signal})
        adapter = ParserStrategyAdapter(parser)

        adapter.on_tick(event)
        orders = adapter.generate_signals()

        # quantity = 100 / 0.5 = 200
        assert len(orders) == 1
        assert orders[0].quantity == pytest.approx(200.0)
