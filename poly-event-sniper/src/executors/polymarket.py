"""Polymarket CLOB executor implementation."""

import asyncio
import time
import uuid
from typing import Any

from loguru import logger
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType

from src.config import BotConfig, get_settings
from src.exceptions import (
    AuthenticationError,
    ExecutionError,
    OrderBookError,
    PositionSizeError,
    PriceValidationError,
    RateLimitError,
)
from src.interfaces.executor import BaseExecutor
from src.models import ExecutionResult, OrderStatus, Side, TradeSignal


class PolymarketExecutor(BaseExecutor):
    """Executor implementation for Polymarket CLOB.

    Handles order creation, signing, and submission to the Polymarket
    Central Limit Order Book.

    Features:
    - Dry-run mode for safe testing
    - Rate limiting to prevent API bans
    - Position size limits for risk management
    - Price validation with sanity checks
    - Proper exception handling (fail-fast, no silent swallowing)
    """

    # Spread crossing multiplier (1% above best ask for buys)
    SPREAD_CROSS_MULTIPLIER = 1.01
    # Spread crossing divisor (1% below best bid for sells)
    SPREAD_CROSS_DIVISOR = 0.99
    # Polymarket host
    HOST = "https://clob.polymarket.com"
    # Chain ID for Polygon
    CHAIN_ID = 137
    # Minimum interval between API requests (100ms)
    MIN_REQUEST_INTERVAL = 0.1
    # Default maximum position size in USDC
    DEFAULT_MAX_POSITION_SIZE = 1000.0
    # Maximum allowed spread percentage (50% = illiquid market)
    MAX_SPREAD_PERCENT = 0.50
    # Price bounds
    MIN_VALID_PRICE = 0.01
    MAX_VALID_PRICE = 0.99

    def __init__(
        self,
        max_position_size: float | None = None,
    ) -> None:
        """Initialize the executor.

        Args:
            max_position_size: Maximum allowed position size in USDC.
                              Defaults to DEFAULT_MAX_POSITION_SIZE.
        """
        self._client: ClobClient | None = None
        self._settings = get_settings()
        self._max_position_size = max_position_size or self.DEFAULT_MAX_POSITION_SIZE
        self._last_request_time: float = 0.0

    async def setup(self) -> None:
        """Initialize CLOB client with API credentials.

        Creates the ClobClient and sets up authentication using
        the configured API credentials.

        Raises:
            AuthenticationError: If API credentials are invalid or missing.
        """
        logger.info("Initializing Polymarket CLOB client")

        try:
            creds = ApiCreds(
                api_key=self._settings.clob.api_key.get_secret_value(),
                api_secret=self._settings.clob.api_secret.get_secret_value(),
                api_passphrase=self._settings.clob.api_passphrase.get_secret_value(),
            )

            self._client = ClobClient(
                host=self.HOST,
                chain_id=self.CHAIN_ID,
                key=self._settings.polygon.private_key.get_secret_value(),
                creds=creds,
            )

            logger.info("Polymarket CLOB client initialized successfully")

        except Exception as e:
            logger.error("Failed to initialize CLOB client: {}", str(e))
            raise AuthenticationError(f"Failed to initialize CLOB client: {e}") from e

    async def execute(self, signal: TradeSignal) -> ExecutionResult:
        """Execute a trade on Polymarket.

        In dry_run mode, logs the intended trade and returns a mock success.
        In live mode, validates the signal, calculates price, and submits order.

        Args:
            signal: Trade signal with token, side, and size information.

        Returns:
            ExecutionResult with order status and fill information.

        Raises:
            PositionSizeError: If position size exceeds configured limits.
            ExecutionError: If the order fails to execute (live mode only).
        """
        # Validate position size first (applies to both dry-run and live)
        self._validate_position_size(signal.size_usdc)

        if self._settings.bot.dry_run:
            return self._execute_dry_run(signal)

        return await self._execute_live(signal)

    def _validate_position_size(self, size_usdc: float) -> None:
        """Validate that position size is within limits.

        Args:
            size_usdc: Position size to validate.

        Raises:
            PositionSizeError: If size exceeds maximum.
        """
        if size_usdc > self._max_position_size:
            raise PositionSizeError(
                f"Position size {size_usdc} USDC exceeds maximum "
                f"{self._max_position_size} USDC"
            )

    async def _throttle(self) -> None:
        """Ensure minimum time between API requests to avoid rate limits."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.MIN_REQUEST_INTERVAL:
            await asyncio.sleep(self.MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def _execute_dry_run(self, signal: TradeSignal) -> ExecutionResult:
        """Execute a simulated trade for testing.

        Args:
            signal: The trade signal to simulate.

        Returns:
            Mock ExecutionResult indicating success.
        """
        logger.warning(
            "DRY RUN TRIGGERED | token_id={} side={} size_usdc={} reason={}",
            signal.token_id,
            signal.side.value,
            signal.size_usdc,
            signal.reason,
        )

        return ExecutionResult(
            order_id=f"dry_run_{uuid.uuid4().hex[:8]}",
            status=OrderStatus.FILLED,
            filled_price=0.50,
            filled_size=signal.size_usdc / 0.50,  # Mock fill at mid-price
            fees_paid=0.0,
        )

    async def _execute_live(self, signal: TradeSignal) -> ExecutionResult:
        """Execute a live trade on Polymarket.

        Args:
            signal: The trade signal to execute.

        Returns:
            ExecutionResult with actual order status.

        Raises:
            RuntimeError: If client not initialized.
            OrderBookError: If order book data is unavailable.
            PriceValidationError: If calculated price fails validation.
            ExecutionError: If order submission fails.
        """
        if self._client is None:
            raise RuntimeError("Client not initialized. Call setup() first.")

        logger.info(
            "Executing live order | token_id={} side={} size_usdc={}",
            signal.token_id,
            signal.side.value,
            signal.size_usdc,
        )

        # Rate limiting
        await self._throttle()

        # Calculate aggressive price to cross spread (may raise)
        price = await self._calculate_price(signal.token_id, signal.side)

        # Validate price
        self._validate_price(price, signal.side)

        # Calculate size in shares based on price
        size = signal.size_usdc / price

        # Build order arguments
        order_args = OrderArgs(
            token_id=signal.token_id,
            price=price,
            size=size,
            side="BUY" if signal.side == Side.BUY else "SELL",
            fee_rate_bps=0,  # Maker fee
            nonce=int(time.time() * 1000),
            expiration=0,  # No expiration for FOK
            taker="",
        )

        # Execute order with proper async handling
        try:
            # Use asyncio.to_thread for blocking CLOB client call
            response: dict[str, Any] = await asyncio.to_thread(
                self._client.create_and_post_order,
                order_args,
                OrderType.FOK,
            )

            # Parse response with safe type handling
            result = self._parse_order_response(response, price, size)

            logger.info(
                "Order executed | order_id={} status={} filled_price={}",
                result.order_id,
                result.status.value,
                result.filled_price,
            )

            return result

        except KeyboardInterrupt:
            # Never swallow interrupt signals
            raise
        except (
            OrderBookError,
            PriceValidationError,
            PositionSizeError,
            RateLimitError,
        ):
            # Re-raise our own exceptions
            raise
        except Exception as e:
            logger.error("Order execution failed: {}", str(e), exc_info=True)
            raise ExecutionError(f"Failed to execute order: {e}") from e

    def _validate_price(self, price: float, side: Side) -> None:
        """Validate calculated price is within acceptable bounds.

        Args:
            price: The calculated price.
            side: Trade direction.

        Raises:
            PriceValidationError: If price is invalid.
        """
        if price <= 0:
            raise PriceValidationError(f"Invalid price: {price} (must be positive)")

        if price < self.MIN_VALID_PRICE:
            raise PriceValidationError(
                f"Price {price} below minimum {self.MIN_VALID_PRICE}"
            )

        if price > self.MAX_VALID_PRICE:
            raise PriceValidationError(
                f"Price {price} above maximum {self.MAX_VALID_PRICE}"
            )

    async def _calculate_price(self, token_id: str, side: Side) -> float:
        """Calculate aggressive price to cross the spread.

        For buys: Best Ask * 1.01 (pay 1% more to ensure fill)
        For sells: Best Bid * 0.99 (accept 1% less to ensure fill)

        Args:
            token_id: The token to get price for.
            side: Trade direction.

        Returns:
            Calculated aggressive price.

        Raises:
            OrderBookError: If order book is unavailable or empty.
            PriceValidationError: If spread is too wide (illiquid market).
        """
        if self._client is None:
            raise RuntimeError("Client not initialized. Call setup() first.")

        # Rate limiting for order book request
        await self._throttle()

        try:
            # Use asyncio.to_thread for blocking CLOB client call
            order_book = await asyncio.to_thread(
                self._client.get_order_book,
                token_id,
            )
        except Exception as e:
            raise OrderBookError(
                f"Failed to fetch order book for {token_id}: {e}"
            ) from e

        bids = order_book.get("bids", [])
        asks = order_book.get("asks", [])

        if side == Side.BUY:
            if not asks:
                raise OrderBookError(f"No asks available for {token_id}")

            best_ask = self._safe_parse_price(asks[0].get("price"))
            if best_ask is None:
                raise OrderBookError(f"Invalid ask price in order book for {token_id}")

            # Check spread if bids available
            if bids:
                best_bid = self._safe_parse_price(bids[0].get("price"))
                if best_bid is not None:
                    self._validate_spread(best_bid, best_ask)

            return min(best_ask * self.SPREAD_CROSS_MULTIPLIER, self.MAX_VALID_PRICE)

        else:  # SELL
            if not bids:
                raise OrderBookError(f"No bids available for {token_id}")

            best_bid = self._safe_parse_price(bids[0].get("price"))
            if best_bid is None:
                raise OrderBookError(f"Invalid bid price in order book for {token_id}")

            # Check spread if asks available
            if asks:
                best_ask = self._safe_parse_price(asks[0].get("price"))
                if best_ask is not None:
                    self._validate_spread(best_bid, best_ask)

            return max(best_bid * self.SPREAD_CROSS_DIVISOR, self.MIN_VALID_PRICE)

    def _validate_spread(self, best_bid: float, best_ask: float) -> None:
        """Validate that spread is not too wide (illiquid market).

        Args:
            best_bid: Best bid price.
            best_ask: Best ask price.

        Raises:
            PriceValidationError: If spread exceeds maximum allowed.
        """
        if best_bid <= 0 or best_ask <= 0:
            return  # Skip validation if prices are invalid

        spread_percent = (best_ask - best_bid) / best_ask
        if spread_percent > self.MAX_SPREAD_PERCENT:
            raise PriceValidationError(
                f"Spread too wide: {spread_percent:.1%} (max: {self.MAX_SPREAD_PERCENT:.0%}). "
                f"Market may be illiquid."
            )

    @staticmethod
    def _safe_parse_price(value: Any) -> float | None:
        """Safely parse a price value from API response.

        Args:
            value: The value to parse.

        Returns:
            Parsed float or None if parsing fails.
        """
        if value is None:
            return None
        try:
            price = float(value)
            return price if price > 0 else None
        except (TypeError, ValueError):
            return None

    def _parse_order_response(
        self, response: dict[str, Any], expected_price: float, expected_size: float
    ) -> ExecutionResult:
        """Parse order response with safe type handling.

        Args:
            response: Raw API response dict.
            expected_price: The price we submitted.
            expected_size: The size we submitted.

        Returns:
            Parsed ExecutionResult.
        """
        # Safe order ID extraction
        order_id = str(
            response.get("orderID") or response.get("id") or f"unknown_{uuid.uuid4().hex[:8]}"
        )

        # Safe status parsing
        status = self._parse_order_status(response)

        # Safe price parsing with fallback to expected
        filled_price = self._safe_parse_price(response.get("price")) or expected_price

        # Safe size parsing with fallback
        filled_size = self._safe_parse_price(response.get("size")) or (
            expected_size if status == OrderStatus.FILLED else 0.0
        )

        # Extract fees if available
        fees_paid = self._safe_parse_price(response.get("fee")) or 0.0

        # Error message for non-success statuses
        error_message = None
        if status in (OrderStatus.REJECTED, OrderStatus.FAILED, OrderStatus.CANCELLED):
            error_message = str(response.get("error") or response.get("message") or "Unknown error")

        return ExecutionResult(
            order_id=order_id,
            status=status,
            filled_price=filled_price,
            filled_size=filled_size,
            fees_paid=fees_paid,
            error_message=error_message,
        )

    @staticmethod
    def _parse_order_status(response: dict[str, Any]) -> OrderStatus:
        """Parse order status from API response.

        Args:
            response: Raw API response dict.

        Returns:
            Mapped OrderStatus enum value.
        """
        status_str = str(response.get("status", "")).upper()

        status_map = {
            "FILLED": OrderStatus.FILLED,
            "MATCHED": OrderStatus.FILLED,
            "PARTIAL": OrderStatus.PARTIAL,
            "CANCELLED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
        }

        return status_map.get(status_str, OrderStatus.PENDING)

    async def get_balance(self) -> float:
        """Get the current USDC balance from Polymarket.

        Returns:
            The available USDC balance.

        Raises:
            RuntimeError: If client not initialized.
            AuthenticationError: If API credentials are invalid.
        """
        if self._settings.bot.dry_run:
            # Return mock balance in dry-run mode
            logger.debug("Dry-run mode: returning mock balance of 10000 USDC")
            return 10000.0

        if self._client is None:
            raise RuntimeError("Client not initialized. Call setup() first.")

        # Rate limiting
        await self._throttle()

        try:
            # Use asyncio.to_thread for blocking CLOB client call
            # The CLOB client returns balance info via get_balance_allowance
            response = await asyncio.to_thread(
                self._client.get_balance_allowance,
            )

            # Parse balance from response
            balance = self._safe_parse_price(response.get("balance")) or 0.0

            logger.debug("Fetched balance: {} USDC", balance)
            return balance

        except Exception as e:
            logger.error("Failed to fetch balance: {}", str(e))
            raise AuthenticationError(f"Failed to fetch balance: {e}") from e
