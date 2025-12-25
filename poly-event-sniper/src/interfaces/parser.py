"""Abstract base class defining the parser interface."""

from abc import ABC, abstractmethod

from src.exceptions import InvalidEventError, ParserError, RuleConfigurationError
from src.models import MarketEvent, TradeSignal

# Re-export exceptions for convenience
__all__ = [
    "BaseParser",
    "InvalidEventError",
    "ParserError",
    "RuleConfigurationError",
]


class BaseParser(ABC):
    """Abstract base class for signal parsing implementations.

    Parsers evaluate MarketEvent objects and optionally emit TradeSignal
    objects when conditions are met.
    """

    @abstractmethod
    def evaluate(self, event: MarketEvent) -> TradeSignal | None:
        """Evaluate a market event and optionally produce a trade signal.

        Args:
            event: The market event to evaluate.

        Returns:
            TradeSignal if conditions are met, None otherwise.

        Raises:
            InvalidEventError: If event data is malformed.
            ParserError: If evaluation fails.
        """
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        """Reset parser state (e.g., cooldowns, tracking variables).

        Should be called when restarting monitoring or switching tokens.
        """
        raise NotImplementedError
