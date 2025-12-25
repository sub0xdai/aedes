"""Tests for Phase 7.5 Orchestrator integration with strategies and portfolio."""

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.interfaces.executor import BaseExecutor
from src.interfaces.ingester import MarketDataIngester
from src.interfaces.parser import BaseParser
from src.interfaces.strategy import BaseStrategy
from src.managers.portfolio import PortfolioManager
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
from src.orchestrator import Orchestrator
from src.persistence import DatabaseManager
from src.strategies.parser_adapter import ParserStrategyAdapter


class MockIngester(MarketDataIngester):
    """Mock ingester that yields predefined events."""

    def __init__(self, events: list[MarketEvent]) -> None:
        self._events = events
        self._connected = False

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def subscribe(self, token_ids: list[str]) -> None:
        pass

    async def stream(self) -> AsyncIterator[MarketEvent]:
        for event in self._events:
            yield event

    @property
    def is_connected(self) -> bool:
        return self._connected


class MockParser(BaseParser):
    """Mock parser that returns predefined signals."""

    def __init__(self, token_to_signal: dict[str, TradeSignal | None]) -> None:
        self._token_to_signal = token_to_signal

    def evaluate(self, event: MarketEvent) -> TradeSignal | None:
        if event.token_id is None:
            return None
        return self._token_to_signal.get(event.token_id)

    def reset(self) -> None:
        pass


class MockExecutor(BaseExecutor):
    """Mock executor for testing."""

    def __init__(self) -> None:
        self.executed_signals: list[TradeSignal] = []
        self.executed_orders: list[Order] = []

    async def setup(self) -> None:
        pass

    async def execute(self, signal: TradeSignal) -> ExecutionResult:
        self.executed_signals.append(signal)
        return ExecutionResult(
            order_id="mock_order",
            status=OrderStatus.FILLED,
            filled_price=0.50,
            filled_size=signal.size_usdc / 0.50,
        )

    async def execute_order(self, order: Order) -> ExecutionResult:
        """Execute an Order (new Phase 7 method)."""
        self.executed_orders.append(order)
        return ExecutionResult(
            order_id=f"order_{order.client_order_id}",
            status=OrderStatus.FILLED,
            filled_price=0.50,
            filled_size=order.quantity,
        )

    async def get_balance(self) -> float:
        return 10000.0


class MockStrategy(BaseStrategy):
    """Mock strategy for testing."""

    def __init__(self, orders_to_generate: list[Order] | None = None) -> None:
        self._orders = orders_to_generate or []
        self._events_received: list[MarketEvent] = []
        self._fills_received: list[tuple[Order, ExecutionResult]] = []

    def on_tick(self, event: MarketEvent) -> None:
        self._events_received.append(event)

    def on_fill(self, order: Order, result: ExecutionResult) -> None:
        self._fills_received.append((order, result))

    def generate_signals(self) -> list[Order]:
        orders = self._orders.copy()
        self._orders = []  # Clear after generating
        return orders

    def reset(self) -> None:
        self._orders = []
        self._events_received = []
        self._fills_received = []

    @property
    def name(self) -> str:
        return "mock_strategy"


class TestOrchestratorWithStrategies:
    """Tests for Orchestrator with strategies."""

    @pytest.fixture
    def sample_event(self) -> MarketEvent:
        return MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
            best_bid=0.45,
            best_ask=0.55,
        )

    @pytest.fixture
    def sample_order(self) -> Order:
        return Order(
            token_id="token_123",
            side=Side.BUY,
            quantity=100.0,
            order_type=OrderType.FOK,
            reason="Test order",
        )

    @pytest.mark.asyncio
    async def test_accepts_strategies_parameter(
        self, sample_event: MarketEvent, sample_order: Order
    ) -> None:
        """Orchestrator should accept strategies parameter."""
        ingester = MockIngester([sample_event])
        strategy = MockStrategy([sample_order])
        executor = MockExecutor()

        orchestrator = Orchestrator(
            ingesters=[ingester],
            strategies=[strategy],
            executor=executor,
        )

        await orchestrator.start()

        # Strategy should have received the event
        assert len(strategy._events_received) == 1
        # Order should have been executed
        assert len(executor.executed_orders) == 1

    @pytest.mark.asyncio
    async def test_strategy_on_tick_called(self, sample_event: MarketEvent) -> None:
        """Strategy.on_tick should be called for each event."""
        ingester = MockIngester([sample_event, sample_event])  # 2 events
        strategy = MockStrategy()
        executor = MockExecutor()

        orchestrator = Orchestrator(
            ingesters=[ingester],
            strategies=[strategy],
            executor=executor,
        )

        await orchestrator.start()

        assert len(strategy._events_received) == 2

    @pytest.mark.asyncio
    async def test_strategy_on_fill_called(
        self, sample_event: MarketEvent, sample_order: Order
    ) -> None:
        """Strategy.on_fill should be called after order execution."""
        ingester = MockIngester([sample_event])
        strategy = MockStrategy([sample_order])
        executor = MockExecutor()

        orchestrator = Orchestrator(
            ingesters=[ingester],
            strategies=[strategy],
            executor=executor,
        )

        await orchestrator.start()

        assert len(strategy._fills_received) == 1
        order, result = strategy._fills_received[0]
        assert order.token_id == "token_123"
        assert result.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_legacy_parsers_wrapped_as_strategies(
        self, sample_event: MarketEvent
    ) -> None:
        """Legacy parsers should be auto-wrapped as strategies."""
        signal = TradeSignal(
            token_id="token_123",
            side=Side.BUY,
            size_usdc=100.0,
            reason="Test signal",
        )
        ingester = MockIngester([sample_event])
        parser = MockParser({"token_123": signal})
        executor = MockExecutor()

        # Using parsers parameter (legacy) with strategies support
        orchestrator = Orchestrator(
            ingesters=[ingester],
            parsers=[parser],
            executor=executor,
        )

        await orchestrator.start()

        # Legacy execution path uses TradeSignal
        assert len(executor.executed_signals) == 1


class TestOrchestratorWithPortfolio:
    """Tests for Orchestrator with PortfolioManager."""

    @pytest.fixture
    async def db(self, tmp_path: Path) -> DatabaseManager:
        db_path = tmp_path / "test.db"
        db_manager = DatabaseManager(db_path)
        await db_manager.connect()
        yield db_manager
        await db_manager.disconnect()

    @pytest.fixture
    def sample_event(self) -> MarketEvent:
        return MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
            best_bid=0.45,
            best_ask=0.55,
            last_price=0.50,
        )

    @pytest.fixture
    def sample_order(self) -> Order:
        return Order(
            token_id="token_123",
            side=Side.BUY,
            quantity=100.0,
            limit_price=0.50,
            reason="Test order",
        )

    @pytest.mark.asyncio
    async def test_accepts_portfolio_parameter(
        self, db: DatabaseManager, sample_event: MarketEvent, sample_order: Order
    ) -> None:
        """Orchestrator should accept portfolio parameter."""
        ingester = MockIngester([sample_event])
        strategy = MockStrategy([sample_order])
        executor = MockExecutor()
        portfolio = PortfolioManager(database=db)
        await portfolio.load_state(executor)

        orchestrator = Orchestrator(
            ingesters=[ingester],
            strategies=[strategy],
            executor=executor,
            portfolio=portfolio,
        )

        await orchestrator.start()

        # Order should have been validated and executed
        assert len(executor.executed_orders) == 1

    @pytest.mark.asyncio
    async def test_portfolio_rejects_invalid_order(
        self, db: DatabaseManager, sample_event: MarketEvent
    ) -> None:
        """Portfolio should reject orders that fail validation."""
        # Create order that exceeds cash balance
        large_order = Order(
            token_id="token_123",
            side=Side.BUY,
            quantity=100000.0,  # Very large
            limit_price=0.90,  # 100000 * 0.90 = 90000 > 10000 balance
            reason="Too expensive",
        )

        ingester = MockIngester([sample_event])
        strategy = MockStrategy([large_order])
        executor = MockExecutor()
        portfolio = PortfolioManager(database=db)
        await portfolio.load_state(executor)  # 10000 USDC balance

        orchestrator = Orchestrator(
            ingesters=[ingester],
            strategies=[strategy],
            executor=executor,
            portfolio=portfolio,
        )

        await orchestrator.start()

        # Order should NOT have been executed (rejected by portfolio)
        assert len(executor.executed_orders) == 0

    @pytest.mark.asyncio
    async def test_portfolio_updated_on_fill(
        self, db: DatabaseManager, sample_event: MarketEvent, sample_order: Order
    ) -> None:
        """Portfolio should update position after fill."""
        ingester = MockIngester([sample_event])
        strategy = MockStrategy([sample_order])
        executor = MockExecutor()
        portfolio = PortfolioManager(database=db)
        await portfolio.load_state(executor)

        orchestrator = Orchestrator(
            ingesters=[ingester],
            strategies=[strategy],
            executor=executor,
            portfolio=portfolio,
        )

        await orchestrator.start()

        # Portfolio should have a position now
        assert "token_123" in portfolio.positions

    @pytest.mark.asyncio
    async def test_portfolio_price_updates(
        self, db: DatabaseManager
    ) -> None:
        """Portfolio should receive price updates from market events."""
        from src.models import Position, PositionSide

        # Create existing position
        pos = Position(
            token_id="token_456",
            side=PositionSide.LONG,
            quantity=100.0,
            avg_entry_price=0.40,
            current_price=0.40,
        )
        await db.upsert_position(pos)

        # Event with new price
        event = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_456",
            best_bid=0.55,
            best_ask=0.65,
            last_price=0.60,
        )

        ingester = MockIngester([event])
        strategy = MockStrategy()  # No orders
        executor = MockExecutor()
        portfolio = PortfolioManager(database=db)
        await portfolio.load_state(executor)

        orchestrator = Orchestrator(
            ingesters=[ingester],
            strategies=[strategy],
            executor=executor,
            portfolio=portfolio,
        )

        await orchestrator.start()

        # Position current_price should be updated
        assert portfolio.positions["token_456"].current_price == 0.60


class TestOrchestratorBackwardCompatibility:
    """Tests ensuring backward compatibility with legacy API."""

    @pytest.mark.asyncio
    async def test_legacy_parser_api_still_works(self) -> None:
        """Legacy parser-only API should continue to work."""
        event = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
            best_bid=0.45,
            best_ask=0.55,
        )
        signal = TradeSignal(
            token_id="token_123",
            side=Side.BUY,
            size_usdc=100.0,
            reason="Test",
        )

        ingester = MockIngester([event])
        parser = MockParser({"token_123": signal})
        executor = MockExecutor()

        # Legacy positional args
        orchestrator = Orchestrator(
            ingester=ingester,
            parser=parser,
            executor=executor,
        )

        await orchestrator.start()

        # Should execute using TradeSignal path
        assert len(executor.executed_signals) == 1

    @pytest.mark.asyncio
    async def test_metrics_include_strategy_execution(self) -> None:
        """Metrics should count strategy-generated orders."""
        event = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
        )
        order = Order(
            token_id="token_123",
            side=Side.BUY,
            quantity=100.0,
            reason="Test",
        )

        ingester = MockIngester([event])
        strategy = MockStrategy([order])
        executor = MockExecutor()

        orchestrator = Orchestrator(
            ingesters=[ingester],
            strategies=[strategy],
            executor=executor,
        )

        await orchestrator.start()

        metrics = orchestrator.metrics
        assert metrics["events_processed"] == 1
        assert metrics["trades_executed"] == 1
