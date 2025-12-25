"""Tests for the orchestrator callback system."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.callbacks import OrchestratorCallback
from src.models import (
    EventType,
    ExecutionResult,
    MarketEvent,
    OrderStatus,
    Position,
    Side,
    ThresholdRule,
    TradeSignal,
)
from src.orchestrator import Orchestrator


class MockCallback:
    """Test callback that records invocations."""

    def __init__(self) -> None:
        self.signals: list[TradeSignal] = []
        self.trades: list[tuple[TradeSignal, ExecutionResult]] = []
        self.errors: list[tuple[Exception, str]] = []
        self.metrics: list[dict[str, int]] = []
        self.positions: list[Position] = []

    async def on_signal_generated(self, signal: TradeSignal) -> None:
        self.signals.append(signal)

    async def on_trade_executed(
        self, signal: TradeSignal, result: ExecutionResult
    ) -> None:
        self.trades.append((signal, result))

    async def on_error(self, error: Exception, context: str) -> None:
        self.errors.append((error, context))

    async def on_metrics_updated(self, metrics: dict[str, int]) -> None:
        self.metrics.append(metrics)

    async def on_position_updated(self, position: Position) -> None:
        self.positions.append(position)


class FailingCallback(MockCallback):
    """Callback that raises exceptions to test resilience."""

    async def on_signal_generated(self, signal: TradeSignal) -> None:
        raise RuntimeError("Callback failure!")

    async def on_trade_executed(
        self, signal: TradeSignal, result: ExecutionResult
    ) -> None:
        raise RuntimeError("Callback failure!")


class TestCallbackProtocol:
    """Tests for the OrchestratorCallback protocol."""

    def test_mock_callback_implements_protocol(self) -> None:
        """Verify MockCallback satisfies OrchestratorCallback protocol."""
        callback = MockCallback()
        assert isinstance(callback, OrchestratorCallback)

    def test_failing_callback_implements_protocol(self) -> None:
        """Verify FailingCallback satisfies OrchestratorCallback protocol."""
        callback = FailingCallback()
        assert isinstance(callback, OrchestratorCallback)


class TestOrchestratorCallbacks:
    """Tests for callback registration and invocation in Orchestrator."""

    @pytest.fixture
    def mock_ingester(self) -> MagicMock:
        """Create a mock ingester that yields one event then stops."""
        ingester = MagicMock()
        ingester.is_connected = True

        # Create a market event that will trigger a signal
        event = MarketEvent(
            event_type=EventType.PRICE_CHANGE,
            token_id="test_token_123",
            market_id="test_market",
            best_bid=0.10,
            best_ask=0.12,
        )

        async def mock_connect() -> None:
            pass

        async def mock_disconnect() -> None:
            pass

        async def mock_stream():
            yield event

        ingester.connect = mock_connect
        ingester.disconnect = mock_disconnect
        ingester.stream = mock_stream
        return ingester

    @pytest.fixture
    def mock_parser(self) -> MagicMock:
        """Create a mock parser that generates a signal."""
        parser = MagicMock()

        signal = TradeSignal(
            token_id="test_token_123",
            side=Side.BUY,
            size_usdc=100.0,
            reason="Test signal",
        )

        parser.evaluate = MagicMock(return_value=signal)
        return parser

    @pytest.fixture
    def mock_executor(self) -> MagicMock:
        """Create a mock executor that returns a successful result."""
        executor = MagicMock()

        result = ExecutionResult(
            order_id="order_123",
            status=OrderStatus.FILLED,
            filled_price=0.11,
            filled_size=100.0,
            fees_paid=0.5,
        )

        async def mock_setup() -> None:
            pass

        async def mock_execute(signal: TradeSignal) -> ExecutionResult:
            return result

        executor.setup = mock_setup
        executor.execute = mock_execute
        return executor

    @pytest.mark.asyncio
    async def test_register_callback(
        self,
        mock_ingester: MagicMock,
        mock_parser: MagicMock,
        mock_executor: MagicMock,
    ) -> None:
        """Test that callbacks can be registered."""
        orchestrator = Orchestrator(
            ingesters=[mock_ingester],
            parsers=[mock_parser],
            executor=mock_executor,
        )

        callback = MockCallback()
        orchestrator.register_callback(callback)

        # Verify callback is registered (internal state check)
        assert callback in orchestrator._callbacks

    @pytest.mark.asyncio
    async def test_callback_receives_signal_generated(
        self,
        mock_ingester: MagicMock,
        mock_parser: MagicMock,
        mock_executor: MagicMock,
    ) -> None:
        """Test that registered callbacks receive signal_generated events."""
        orchestrator = Orchestrator(
            ingesters=[mock_ingester],
            parsers=[mock_parser],
            executor=mock_executor,
        )

        callback = MockCallback()
        orchestrator.register_callback(callback)

        # Run orchestrator (will process one event then stop)
        await orchestrator.start()

        # Verify callback received the signal
        assert len(callback.signals) == 1
        assert callback.signals[0].token_id == "test_token_123"
        assert callback.signals[0].side == Side.BUY

    @pytest.mark.asyncio
    async def test_callback_receives_trade_executed(
        self,
        mock_ingester: MagicMock,
        mock_parser: MagicMock,
        mock_executor: MagicMock,
    ) -> None:
        """Test that registered callbacks receive trade_executed events."""
        orchestrator = Orchestrator(
            ingesters=[mock_ingester],
            parsers=[mock_parser],
            executor=mock_executor,
        )

        callback = MockCallback()
        orchestrator.register_callback(callback)

        await orchestrator.start()

        # Verify callback received the trade
        assert len(callback.trades) == 1
        signal, result = callback.trades[0]
        assert signal.token_id == "test_token_123"
        assert result.order_id == "order_123"
        assert result.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_callback_receives_metrics_updated(
        self,
        mock_ingester: MagicMock,
        mock_parser: MagicMock,
        mock_executor: MagicMock,
    ) -> None:
        """Test that registered callbacks receive metrics_updated events."""
        orchestrator = Orchestrator(
            ingesters=[mock_ingester],
            parsers=[mock_parser],
            executor=mock_executor,
        )

        callback = MockCallback()
        orchestrator.register_callback(callback)

        await orchestrator.start()

        # Verify callback received metrics
        assert len(callback.metrics) >= 1
        last_metrics = callback.metrics[-1]
        assert last_metrics["events_processed"] == 1
        assert last_metrics["signals_generated"] == 1
        assert last_metrics["trades_executed"] == 1

    @pytest.mark.asyncio
    async def test_failing_callback_does_not_crash_pipeline(
        self,
        mock_ingester: MagicMock,
        mock_parser: MagicMock,
        mock_executor: MagicMock,
    ) -> None:
        """Test that a failing callback doesn't stop trading."""
        orchestrator = Orchestrator(
            ingesters=[mock_ingester],
            parsers=[mock_parser],
            executor=mock_executor,
        )

        failing_callback = FailingCallback()
        working_callback = MockCallback()

        orchestrator.register_callback(failing_callback)
        orchestrator.register_callback(working_callback)

        # Should not raise despite failing callback
        await orchestrator.start()

        # Working callback should still receive events
        assert len(working_callback.trades) == 1
        assert orchestrator.metrics["trades_executed"] == 1

    @pytest.mark.asyncio
    async def test_multiple_callbacks_all_receive_events(
        self,
        mock_ingester: MagicMock,
        mock_parser: MagicMock,
        mock_executor: MagicMock,
    ) -> None:
        """Test that multiple callbacks all receive events."""
        orchestrator = Orchestrator(
            ingesters=[mock_ingester],
            parsers=[mock_parser],
            executor=mock_executor,
        )

        callback1 = MockCallback()
        callback2 = MockCallback()
        callback3 = MockCallback()

        orchestrator.register_callback(callback1)
        orchestrator.register_callback(callback2)
        orchestrator.register_callback(callback3)

        await orchestrator.start()

        # All callbacks should receive the trade
        assert len(callback1.trades) == 1
        assert len(callback2.trades) == 1
        assert len(callback3.trades) == 1
