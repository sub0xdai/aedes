"""Integration tests for the orchestrator."""

from collections.abc import AsyncIterator

import pytest

from src.interfaces.executor import BaseExecutor
from src.interfaces.ingester import MarketDataIngester
from src.interfaces.parser import BaseParser
from src.models import (
    EventType,
    ExecutionResult,
    MarketEvent,
    OrderStatus,
    Side,
    TradeSignal,
)
from src.orchestrator import Orchestrator


class MockIngester(MarketDataIngester):
    """Mock ingester for testing."""

    def __init__(self, events: list[MarketEvent]) -> None:
        self._events = events
        self._connected = False
        self._subscribed: list[str] = []

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def subscribe(self, token_ids: list[str]) -> None:
        self._subscribed = token_ids

    async def stream(self) -> AsyncIterator[MarketEvent]:
        for event in self._events:
            yield event

    @property
    def is_connected(self) -> bool:
        return self._connected


class MockParser(BaseParser):
    """Mock parser for testing."""

    def __init__(self, signals: dict[str, TradeSignal | None]) -> None:
        """Map event token_id to signal or None."""
        self._signals = signals

    def evaluate(self, event: MarketEvent) -> TradeSignal | None:
        return self._signals.get(event.token_id)

    def reset(self) -> None:
        pass


class MockExecutor(BaseExecutor):
    """Mock executor for testing."""

    def __init__(self) -> None:
        self.executed_signals: list[TradeSignal] = []
        self.setup_called = False

    async def setup(self) -> None:
        self.setup_called = True

    async def execute(self, signal: TradeSignal) -> ExecutionResult:
        self.executed_signals.append(signal)
        return ExecutionResult(
            order_id="mock_order",
            status=OrderStatus.FILLED,
            filled_price=0.50,
            filled_size=signal.size_usdc / 0.50,
        )

    async def get_balance(self) -> float:
        return 10000.0


class TestOrchestrator:
    """Test suite for Orchestrator."""

    @pytest.fixture
    def sample_event(self) -> MarketEvent:
        """Create a sample market event."""
        return MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
            market_id="market_456",
            best_bid=0.25,
            best_ask=0.29,
        )

    @pytest.fixture
    def sample_signal(self) -> TradeSignal:
        """Create a sample trade signal."""
        return TradeSignal(
            token_id="token_123",
            side=Side.BUY,
            size_usdc=100.0,
            reason="Test signal",
        )

    @pytest.mark.asyncio
    async def test_full_pipeline(
        self, sample_event: MarketEvent, sample_signal: TradeSignal
    ) -> None:
        """Test complete event -> signal -> execution pipeline."""
        # Create mocks
        ingester = MockIngester([sample_event])
        parser = MockParser({"token_123": sample_signal})
        executor = MockExecutor()

        # Create and run orchestrator
        orchestrator = Orchestrator(ingester, parser, executor)
        await orchestrator.start()

        # Verify setup was called
        assert executor.setup_called

        # Verify ingester was connected
        assert ingester.is_connected is False  # Disconnected after stream ends

        # Verify execution
        assert len(executor.executed_signals) == 1
        assert executor.executed_signals[0].token_id == "token_123"
        assert executor.executed_signals[0].size_usdc == 100.0

        # Verify metrics
        metrics = orchestrator.metrics
        assert metrics["events_processed"] == 1
        assert metrics["signals_generated"] == 1
        assert metrics["trades_executed"] == 1
        assert metrics["errors_encountered"] == 0

    @pytest.mark.asyncio
    async def test_no_signal_no_execution(self, sample_event: MarketEvent) -> None:
        """Test that no execution occurs when parser returns None."""
        ingester = MockIngester([sample_event])
        parser = MockParser({})  # No signals
        executor = MockExecutor()

        orchestrator = Orchestrator(ingester, parser, executor)
        await orchestrator.start()

        assert len(executor.executed_signals) == 0
        assert orchestrator.metrics["events_processed"] == 1
        assert orchestrator.metrics["signals_generated"] == 0
        assert orchestrator.metrics["trades_executed"] == 0

    @pytest.mark.asyncio
    async def test_multiple_events(self) -> None:
        """Test processing multiple events."""
        events = [
            MarketEvent(
                event_type=EventType.PRICE_CHANGE,
                token_id="token_A",
                market_id="market_456",
                best_bid=0.25,
                best_ask=0.29,
            ),
            MarketEvent(
                event_type=EventType.PRICE_CHANGE,
                token_id="token_B",
                market_id="market_456",
                best_bid=0.73,
                best_ask=0.77,
            ),
            MarketEvent(
                event_type=EventType.PRICE_CHANGE,
                token_id="token_C",
                market_id="market_456",
                best_bid=0.50,
                best_ask=0.52,
            ),
        ]

        signal_a = TradeSignal(
            token_id="token_A",
            side=Side.BUY,
            size_usdc=100.0,
            reason="Buy A",
        )
        signal_b = TradeSignal(
            token_id="token_B",
            side=Side.SELL,
            size_usdc=50.0,
            reason="Sell B",
        )

        ingester = MockIngester(events)
        parser = MockParser(
            {
                "token_A": signal_a,
                "token_B": signal_b,
                # token_C has no signal
            }
        )
        executor = MockExecutor()

        orchestrator = Orchestrator(ingester, parser, executor)
        await orchestrator.start()

        assert orchestrator.metrics["events_processed"] == 3
        assert orchestrator.metrics["signals_generated"] == 2
        assert orchestrator.metrics["trades_executed"] == 2
        assert len(executor.executed_signals) == 2

    @pytest.mark.asyncio
    async def test_metrics_initial_state(self) -> None:
        """Test that metrics start at zero."""
        ingester = MockIngester([])
        parser = MockParser({})
        executor = MockExecutor()

        orchestrator = Orchestrator(ingester, parser, executor)

        metrics = orchestrator.metrics
        assert metrics["events_processed"] == 0
        assert metrics["signals_generated"] == 0
        assert metrics["trades_executed"] == 0
        assert metrics["errors_encountered"] == 0


class TestOrchestratorErrorHandling:
    """Test suite for orchestrator error handling."""

    @pytest.mark.asyncio
    async def test_parser_error_increments_error_count(self) -> None:
        """Test that parser errors are counted."""

        class FailingParser(BaseParser):
            def evaluate(self, event: MarketEvent) -> TradeSignal | None:
                raise ValueError("Parser failure")

            def reset(self) -> None:
                pass

        event = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
            market_id="market_456",
            best_bid=0.50,
            best_ask=0.52,
        )

        ingester = MockIngester([event])
        parser = FailingParser()
        executor = MockExecutor()

        orchestrator = Orchestrator(ingester, parser, executor)
        await orchestrator.start()

        assert orchestrator.metrics["errors_encountered"] == 1
        assert len(executor.executed_signals) == 0

    @pytest.mark.asyncio
    async def test_executor_error_increments_error_count(self) -> None:
        """Test that executor errors are counted."""

        class FailingExecutor(BaseExecutor):
            async def setup(self) -> None:
                pass

            async def execute(self, signal: TradeSignal) -> ExecutionResult:
                raise ValueError("Executor failure")

            async def get_balance(self) -> float:
                return 10000.0

        event = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
            market_id="market_456",
            best_bid=0.50,
            best_ask=0.52,
        )
        signal = TradeSignal(
            token_id="token_123",
            side=Side.BUY,
            size_usdc=100.0,
            reason="Test",
        )

        ingester = MockIngester([event])
        parser = MockParser({"token_123": signal})
        executor = FailingExecutor()

        orchestrator = Orchestrator(ingester, parser, executor)
        await orchestrator.start()

        assert orchestrator.metrics["errors_encountered"] == 1
        assert orchestrator.metrics["signals_generated"] == 1
        assert orchestrator.metrics["trades_executed"] == 0


class TestMultiIngesterOrchestrator:
    """Test suite for multi-ingester support."""

    @pytest.mark.asyncio
    async def test_accepts_list_of_ingesters(self) -> None:
        """Test that orchestrator can be initialized with multiple ingesters."""
        events_a = [
            MarketEvent(
                event_type=EventType.PRICE_CHANGE,
                token_id="token_A",
                market_id="market_1",
                best_bid=0.25,
                best_ask=0.29,
            )
        ]
        events_b = [
            MarketEvent(
                event_type=EventType.PRICE_CHANGE,
                token_id="token_B",
                market_id="market_2",
                best_bid=0.50,
                best_ask=0.52,
            )
        ]

        ingester_a = MockIngester(events_a)
        ingester_b = MockIngester(events_b)
        parser = MockParser({})
        executor = MockExecutor()

        # Should accept list of ingesters
        orchestrator = Orchestrator(
            ingesters=[ingester_a, ingester_b],
            parsers=[parser],
            executor=executor,
        )
        await orchestrator.start()

        # Events from both ingesters should be processed
        assert orchestrator.metrics["events_processed"] == 2

    @pytest.mark.asyncio
    async def test_events_merged_from_multiple_ingesters(self) -> None:
        """Test that events from multiple ingesters are all processed."""
        events_market = [
            MarketEvent(
                event_type=EventType.PRICE_CHANGE,
                token_id="token_market",
                market_id="market_1",
                best_bid=0.30,
                best_ask=0.32,
            )
        ]
        events_news = [
            MarketEvent(
                event_type=EventType.NEWS,
                content="Breaking news",
                source="test_feed",
            )
        ]

        signal = TradeSignal(
            token_id="token_market",
            side=Side.BUY,
            size_usdc=100.0,
            reason="Market signal",
        )

        market_ingester = MockIngester(events_market)
        news_ingester = MockIngester(events_news)
        parser = MockParser({"token_market": signal})
        executor = MockExecutor()

        orchestrator = Orchestrator(
            ingesters=[market_ingester, news_ingester],
            parsers=[parser],
            executor=executor,
        )
        await orchestrator.start()

        # Both events processed
        assert orchestrator.metrics["events_processed"] == 2
        # Only the market event generates a signal
        assert orchestrator.metrics["signals_generated"] == 1


class TestMultiParserOrchestrator:
    """Test suite for multi-parser support."""

    @pytest.mark.asyncio
    async def test_accepts_list_of_parsers(self) -> None:
        """Test that orchestrator can be initialized with multiple parsers."""
        event = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
            market_id="market_1",
            best_bid=0.40,
            best_ask=0.42,
        )

        ingester = MockIngester([event])
        parser_a = MockParser({})
        parser_b = MockParser({})
        executor = MockExecutor()

        # Should accept list of parsers
        orchestrator = Orchestrator(
            ingesters=[ingester],
            parsers=[parser_a, parser_b],
            executor=executor,
        )
        await orchestrator.start()

        assert orchestrator.metrics["events_processed"] == 1

    @pytest.mark.asyncio
    async def test_event_evaluated_by_all_parsers(self) -> None:
        """Test that each event is evaluated by all parsers."""
        event = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
            market_id="market_1",
            best_bid=0.40,
            best_ask=0.42,
        )

        signal_from_parser_a = TradeSignal(
            token_id="token_123",
            side=Side.BUY,
            size_usdc=50.0,
            reason="Parser A signal",
        )
        signal_from_parser_b = TradeSignal(
            token_id="token_123",
            side=Side.SELL,
            size_usdc=25.0,
            reason="Parser B signal",
        )

        ingester = MockIngester([event])
        parser_a = MockParser({"token_123": signal_from_parser_a})
        parser_b = MockParser({"token_123": signal_from_parser_b})
        executor = MockExecutor()

        orchestrator = Orchestrator(
            ingesters=[ingester],
            parsers=[parser_a, parser_b],
            executor=executor,
        )
        await orchestrator.start()

        # Single event, but both parsers generate signals
        assert orchestrator.metrics["events_processed"] == 1
        assert orchestrator.metrics["signals_generated"] == 2
        assert orchestrator.metrics["trades_executed"] == 2
        assert len(executor.executed_signals) == 2

    @pytest.mark.asyncio
    async def test_partial_parser_match(self) -> None:
        """Test that only matching parsers generate signals."""
        event = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
            market_id="market_1",
            best_bid=0.40,
            best_ask=0.42,
        )

        signal = TradeSignal(
            token_id="token_123",
            side=Side.BUY,
            size_usdc=50.0,
            reason="Only parser B",
        )

        ingester = MockIngester([event])
        parser_a = MockParser({})  # No match
        parser_b = MockParser({"token_123": signal})  # Matches
        executor = MockExecutor()

        orchestrator = Orchestrator(
            ingesters=[ingester],
            parsers=[parser_a, parser_b],
            executor=executor,
        )
        await orchestrator.start()

        assert orchestrator.metrics["events_processed"] == 1
        assert orchestrator.metrics["signals_generated"] == 1
        assert orchestrator.metrics["trades_executed"] == 1


class TestBackwardCompatibility:
    """Test backward compatibility with single ingester/parser."""

    @pytest.mark.asyncio
    async def test_single_ingester_still_works(self) -> None:
        """Test that passing a single ingester (not in list) still works."""
        event = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="token_123",
            market_id="market_1",
            best_bid=0.40,
            best_ask=0.42,
        )

        ingester = MockIngester([event])
        parser = MockParser({})
        executor = MockExecutor()

        # Should still accept single ingester/parser (wrapped internally)
        orchestrator = Orchestrator(
            ingester=ingester,
            parser=parser,
            executor=executor,
        )
        await orchestrator.start()

        assert orchestrator.metrics["events_processed"] == 1
