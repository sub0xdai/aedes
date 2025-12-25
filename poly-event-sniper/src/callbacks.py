"""Callback protocols for orchestrator event notifications."""

from typing import Protocol, runtime_checkable

from src.models import ExecutionResult, Position, TradeSignal


@runtime_checkable
class OrchestratorCallback(Protocol):
    """Protocol defining the callback interface for Orchestrator events.

    All methods are async and may be called from the orchestrator's
    event processing loop. Implementations MUST NOT block.

    Callbacks are wrapped in try/except by the orchestrator - a failing
    callback will never crash the trading pipeline.
    """

    async def on_signal_generated(self, signal: TradeSignal) -> None:
        """Called when a parser generates a trade signal.

        Args:
            signal: The generated trade signal.
        """
        ...

    async def on_trade_executed(
        self,
        signal: TradeSignal,
        result: ExecutionResult,
    ) -> None:
        """Called when a trade is executed (success or failure).

        Args:
            signal: The trade signal that was executed.
            result: The execution result.
        """
        ...

    async def on_error(self, error: Exception, context: str) -> None:
        """Called when an error occurs during processing.

        Args:
            error: The exception that occurred.
            context: Description of where the error occurred.
        """
        ...

    async def on_metrics_updated(self, metrics: dict[str, int]) -> None:
        """Called when metrics change (after each event).

        Args:
            metrics: Current orchestrator metrics.
        """
        ...

    async def on_position_updated(self, position: Position) -> None:
        """Called when a position is created, updated, or closed (Phase 7).

        Args:
            position: The updated position.
        """
        ...
