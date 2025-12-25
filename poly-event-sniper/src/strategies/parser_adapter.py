"""Adapter to wrap existing parsers as strategies."""

from src.interfaces.parser import BaseParser
from src.interfaces.strategy import BaseStrategy
from src.models import ExecutionResult, MarketEvent, Order, OrderType, TradeSignal


class ParserStrategyAdapter(BaseStrategy):
    """Adapts existing BaseParser to BaseStrategy interface.

    Provides backward compatibility by wrapping stateless parsers
    in the stateful strategy interface.

    Example:
        parser = PriceThresholdParser(rules)
        strategy = ParserStrategyAdapter(parser)
        orchestrator = Orchestrator(strategies=[strategy], ...)
    """

    def __init__(self, parser: BaseParser) -> None:
        """Initialize the adapter.

        Args:
            parser: The parser to wrap.
        """
        self._parser = parser
        self._pending_signal: TradeSignal | None = None
        self._last_event: MarketEvent | None = None

    def on_tick(self, event: MarketEvent) -> None:
        """Evaluate parser on event and store any signal.

        Args:
            event: The market event to evaluate.
        """
        self._last_event = event
        signal = self._parser.evaluate(event)
        if signal is not None:
            self._pending_signal = signal

    def on_fill(self, order: Order, result: ExecutionResult) -> None:
        """No-op for wrapped parsers (they are stateless)."""
        pass

    def generate_signals(self) -> list[Order]:
        """Convert pending signal to Order and clear.

        Returns:
            List containing one Order if signal pending, empty otherwise.
        """
        if self._pending_signal is None:
            return []

        signal = self._pending_signal
        self._pending_signal = None

        # Calculate quantity from size_usdc and price
        price = self._get_price()
        quantity = signal.size_usdc / price

        order = Order(
            token_id=signal.token_id,
            side=signal.side,
            quantity=quantity,
            order_type=OrderType.FOK,
            reason=signal.reason,
        )

        return [order]

    def _get_price(self) -> float:
        """Get price from last event or default.

        Returns:
            Mid price if available, 0.5 otherwise.
        """
        if self._last_event is None:
            return 0.5

        # Try to get mid price from bid/ask
        if self._last_event.best_bid is not None and self._last_event.best_ask is not None:
            return (self._last_event.best_bid + self._last_event.best_ask) / 2

        # Fall back to last price
        if self._last_event.last_price is not None:
            return self._last_event.last_price

        # Default to 0.5 (mid of binary market range)
        return 0.5

    def reset(self) -> None:
        """Reset parser and clear pending signal."""
        self._parser.reset()
        self._pending_signal = None
        self._last_event = None

    @property
    def name(self) -> str:
        """Strategy name based on wrapped parser."""
        return f"adapted_{self._parser.__class__.__name__}"
