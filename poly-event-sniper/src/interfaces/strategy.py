"""Abstract base class defining the strategy interface."""

from abc import ABC, abstractmethod

from src.models import ExecutionResult, MarketEvent, Order

__all__ = ["BaseStrategy"]


class BaseStrategy(ABC):
    """Abstract base class for stateful trading strategies.

    Strategies process market events, maintain internal state,
    and generate trading orders based on their logic.

    Unlike stateless parsers, strategies can:
    - Track position state across events
    - React to order fills
    - Generate multiple orders from accumulated state
    """

    @abstractmethod
    def on_tick(self, event: MarketEvent) -> None:
        """Process a market event and update internal state.

        Called for every market event. Implementation should update
        internal state tracking (prices, indicators, etc.).

        Args:
            event: The market event to process.
        """
        raise NotImplementedError

    @abstractmethod
    def on_fill(self, order: Order, result: ExecutionResult) -> None:
        """Called when an order is filled.

        Allows strategy to update state based on execution results.
        For example, updating position tracking or adjusting parameters.

        Args:
            order: The order that was filled.
            result: The execution result.
        """
        raise NotImplementedError

    @abstractmethod
    def generate_signals(self) -> list[Order]:
        """Generate trading orders based on current state.

        Called after on_tick to collect any orders the strategy
        wants to execute. Should clear any pending state.

        Returns:
            List of Order objects to execute. May be empty.
        """
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        """Reset strategy state.

        Called when restarting monitoring or switching contexts.
        Should clear all internal state.
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy identifier.

        Returns:
            Human-readable name for this strategy.
        """
        raise NotImplementedError
