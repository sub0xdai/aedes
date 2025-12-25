"""Abstract base class defining the executor interface."""

from abc import ABC, abstractmethod

from src.exceptions import (
    AuthenticationError,
    ExecutionError,
    OrderBookError,
    PositionSizeError,
    PriceValidationError,
    RateLimitError,
)
from src.models import ExecutionResult, TradeSignal

# Re-export exceptions for convenience
__all__ = [
    "BaseExecutor",
    "AuthenticationError",
    "ExecutionError",
    "OrderBookError",
    "PositionSizeError",
    "PriceValidationError",
    "RateLimitError",
]


class BaseExecutor(ABC):
    """Abstract base class for trade execution implementations.

    All executor implementations must inherit from this class and provide
    concrete implementations for the abstract methods.
    """

    @abstractmethod
    async def setup(self) -> None:
        """Initialize connection and authenticate with the exchange.

        Should be called before any execute() calls. Implementations should
        handle connection pooling, API authentication, and any necessary
        warm-up operations.

        Raises:
            ConnectionError: If unable to connect to the exchange.
            AuthenticationError: If credentials are invalid.
        """
        raise NotImplementedError

    @abstractmethod
    async def execute(self, signal: TradeSignal) -> ExecutionResult:
        """Execute a trade based on the provided signal.

        Args:
            signal: The trade signal containing token, side, and size information.

        Returns:
            ExecutionResult containing order ID, status, and fill information.

        Raises:
            ExecutionError: If the order fails to execute.
            PositionSizeError: If position size exceeds limits.
            PriceValidationError: If price calculation fails validation.
            OrderBookError: If order book data is unavailable.
            RateLimitError: If rate limit is exceeded.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_balance(self) -> float:
        """Get the current cash balance from the exchange.

        Returns:
            The available cash balance in USDC.

        Raises:
            ConnectionError: If unable to connect to the exchange.
            AuthenticationError: If credentials are invalid.
        """
        raise NotImplementedError
