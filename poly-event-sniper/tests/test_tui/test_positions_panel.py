"""Tests for Phase 7.6 TUI PositionsPanel widget."""

import pytest

from src.models import Position, PositionSide


class TestPositionsPanel:
    """Tests for PositionsPanel widget."""

    def test_positions_panel_exists(self) -> None:
        """PositionsPanel should be importable."""
        from src.tui.widgets.positions import PositionsPanel

        panel = PositionsPanel()
        assert panel is not None

    def test_has_add_position_method(self) -> None:
        """PositionsPanel should have add_position method."""
        from src.tui.widgets.positions import PositionsPanel

        panel = PositionsPanel()
        assert hasattr(panel, "add_position")

    def test_has_update_position_method(self) -> None:
        """PositionsPanel should have update_position method."""
        from src.tui.widgets.positions import PositionsPanel

        panel = PositionsPanel()
        assert hasattr(panel, "update_position")

    def test_has_remove_position_method(self) -> None:
        """PositionsPanel should have remove_position method."""
        from src.tui.widgets.positions import PositionsPanel

        panel = PositionsPanel()
        assert hasattr(panel, "remove_position")


class TestCallbackProtocolExtension:
    """Tests for OrchestratorCallback extension."""

    def test_on_position_updated_in_protocol(self) -> None:
        """OrchestratorCallback should have on_position_updated method."""
        from src.callbacks import OrchestratorCallback

        # Check the protocol has the method
        assert hasattr(OrchestratorCallback, "on_position_updated")

    @pytest.mark.asyncio
    async def test_callback_receives_position_update(self) -> None:
        """Callback should receive position updates."""
        from src.callbacks import OrchestratorCallback
        from src.models import ExecutionResult, OrderStatus, TradeSignal

        class MockCallback:
            """Mock callback that records position updates."""

            def __init__(self) -> None:
                self.positions_received: list[Position] = []
                self.signals_received: list[TradeSignal] = []

            async def on_signal_generated(self, signal: TradeSignal) -> None:
                self.signals_received.append(signal)

            async def on_trade_executed(
                self, signal: TradeSignal, result: ExecutionResult
            ) -> None:
                pass

            async def on_error(self, error: Exception, context: str) -> None:
                pass

            async def on_metrics_updated(self, metrics: dict[str, int]) -> None:
                pass

            async def on_position_updated(self, position: Position) -> None:
                self.positions_received.append(position)

        callback = MockCallback()

        # Verify it's a valid OrchestratorCallback
        assert isinstance(callback, OrchestratorCallback)

        # Verify on_position_updated works
        pos = Position(
            token_id="token_123",
            side=PositionSide.LONG,
            quantity=100.0,
            avg_entry_price=0.50,
            current_price=0.60,
        )
        await callback.on_position_updated(pos)

        assert len(callback.positions_received) == 1
        assert callback.positions_received[0].token_id == "token_123"
