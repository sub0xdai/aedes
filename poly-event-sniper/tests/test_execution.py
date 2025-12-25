"""Unit tests for the execution layer."""

import sys
from io import StringIO

import pytest
from pydantic import ValidationError
from loguru import logger

from src.exceptions import (
    ExecutionError,
    OrderBookError,
    PositionSizeError,
    PriceValidationError,
)
from src.executors.polymarket import PolymarketExecutor
from src.models import ExecutionResult, OrderStatus, Side, TradeSignal


@pytest.fixture
def dry_run_executor() -> PolymarketExecutor:
    """Create a PolymarketExecutor with dry_run=True."""
    executor = PolymarketExecutor()
    return executor


@pytest.fixture
def executor_with_low_limit() -> PolymarketExecutor:
    """Create a PolymarketExecutor with a low position size limit."""
    return PolymarketExecutor(max_position_size=50.0)


@pytest.fixture
def dummy_signal() -> TradeSignal:
    """Create a dummy trade signal for testing."""
    return TradeSignal(
        token_id="test_token_123",
        side=Side.BUY,
        size_usdc=100.0,
        reason="Test signal for unit testing",
    )


@pytest.fixture
def small_signal() -> TradeSignal:
    """Create a small trade signal that fits within low limits."""
    return TradeSignal(
        token_id="test_token_123",
        side=Side.BUY,
        size_usdc=25.0,
        reason="Small test signal",
    )


class TestPolymarketExecutorDryRun:
    """Test suite for PolymarketExecutor in dry_run mode."""

    @pytest.mark.asyncio
    async def test_executor_initializes_with_dry_run(
        self, dry_run_executor: PolymarketExecutor
    ) -> None:
        """Test 1: Initialize PolymarketExecutor with dry_run=True."""
        assert dry_run_executor._settings.bot.dry_run is True

    @pytest.mark.asyncio
    async def test_execute_dry_run_returns_mock_success(
        self, dry_run_executor: PolymarketExecutor, dummy_signal: TradeSignal
    ) -> None:
        """Test 2: Call execute() with a dummy TradeSignal."""
        result = await dry_run_executor.execute(dummy_signal)

        # Assert: Returns valid ExecutionResult
        assert isinstance(result, ExecutionResult)
        assert result.status == OrderStatus.FILLED
        assert result.order_id.startswith("dry_run_")
        assert result.filled_price == 0.50
        assert result.filled_size == 200.0  # 100 USDC / 0.50 price
        assert result.fees_paid == 0.0

    @pytest.mark.asyncio
    async def test_execute_dry_run_logs_correctly(
        self, dry_run_executor: PolymarketExecutor, dummy_signal: TradeSignal
    ) -> None:
        """Assert: No network call is made, logs contain 'DRY RUN'."""
        # Capture loguru output using a string sink
        log_output = StringIO()
        handler_id = logger.add(log_output, format="{message}", level="WARNING")

        try:
            await dry_run_executor.execute(dummy_signal)
            log_content = log_output.getvalue()
            # Check logs contain DRY RUN message
            assert "DRY RUN TRIGGERED" in log_content
        finally:
            logger.remove(handler_id)

    @pytest.mark.asyncio
    async def test_execute_dry_run_no_network_call(
        self, dry_run_executor: PolymarketExecutor, dummy_signal: TradeSignal
    ) -> None:
        """Verify no actual network calls are made in dry_run mode."""
        # The client is never initialized in dry_run, so _client should be None
        assert dry_run_executor._client is None

        # Execute should still work without network
        result = await dry_run_executor.execute(dummy_signal)
        assert result.status == OrderStatus.FILLED

        # Client should still be None (no setup called, no network needed)
        assert dry_run_executor._client is None


class TestPositionSizeLimits:
    """Test suite for position size validation."""

    @pytest.mark.asyncio
    async def test_position_size_within_limit_succeeds(
        self, executor_with_low_limit: PolymarketExecutor, small_signal: TradeSignal
    ) -> None:
        """Position size within limit should succeed."""
        result = await executor_with_low_limit.execute(small_signal)
        assert result.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_position_size_exceeds_limit_raises(
        self, executor_with_low_limit: PolymarketExecutor, dummy_signal: TradeSignal
    ) -> None:
        """Position size exceeding limit should raise PositionSizeError."""
        with pytest.raises(PositionSizeError) as exc_info:
            await executor_with_low_limit.execute(dummy_signal)

        assert "100.0 USDC exceeds maximum 50.0 USDC" in str(exc_info.value)

    def test_custom_max_position_size(self) -> None:
        """Verify custom max position size is applied."""
        executor = PolymarketExecutor(max_position_size=500.0)
        assert executor._max_position_size == 500.0

    def test_default_max_position_size(self) -> None:
        """Verify default max position size."""
        executor = PolymarketExecutor()
        assert executor._max_position_size == 1000.0


class TestPriceValidation:
    """Test suite for price validation logic."""

    def test_validate_price_zero_raises(self, dry_run_executor: PolymarketExecutor) -> None:
        """Zero price should raise PriceValidationError."""
        with pytest.raises(PriceValidationError) as exc_info:
            dry_run_executor._validate_price(0.0, Side.BUY)
        assert "must be positive" in str(exc_info.value)

    def test_validate_price_negative_raises(self, dry_run_executor: PolymarketExecutor) -> None:
        """Negative price should raise PriceValidationError."""
        with pytest.raises(PriceValidationError) as exc_info:
            dry_run_executor._validate_price(-0.5, Side.BUY)
        assert "must be positive" in str(exc_info.value)

    def test_validate_price_below_minimum_raises(
        self, dry_run_executor: PolymarketExecutor
    ) -> None:
        """Price below minimum should raise PriceValidationError."""
        with pytest.raises(PriceValidationError) as exc_info:
            dry_run_executor._validate_price(0.005, Side.BUY)
        assert "below minimum" in str(exc_info.value)

    def test_validate_price_above_maximum_raises(
        self, dry_run_executor: PolymarketExecutor
    ) -> None:
        """Price above maximum should raise PriceValidationError."""
        with pytest.raises(PriceValidationError) as exc_info:
            dry_run_executor._validate_price(0.995, Side.SELL)
        assert "above maximum" in str(exc_info.value)

    def test_validate_price_valid_passes(self, dry_run_executor: PolymarketExecutor) -> None:
        """Valid price should not raise."""
        # Should not raise
        dry_run_executor._validate_price(0.50, Side.BUY)
        dry_run_executor._validate_price(0.01, Side.SELL)
        dry_run_executor._validate_price(0.99, Side.BUY)


class TestSpreadValidation:
    """Test suite for spread validation logic."""

    def test_validate_spread_wide_raises(self, dry_run_executor: PolymarketExecutor) -> None:
        """Wide spread should raise PriceValidationError."""
        with pytest.raises(PriceValidationError) as exc_info:
            dry_run_executor._validate_spread(0.20, 0.80)  # 75% spread
        assert "Spread too wide" in str(exc_info.value)
        assert "illiquid" in str(exc_info.value)

    def test_validate_spread_acceptable_passes(
        self, dry_run_executor: PolymarketExecutor
    ) -> None:
        """Acceptable spread should not raise."""
        # 10% spread - should pass
        dry_run_executor._validate_spread(0.45, 0.50)

    def test_validate_spread_zero_bid_skips(
        self, dry_run_executor: PolymarketExecutor
    ) -> None:
        """Zero bid should skip validation (no raise)."""
        # Should not raise
        dry_run_executor._validate_spread(0.0, 0.50)


class TestSafeParsing:
    """Test suite for safe parsing utilities."""

    def test_safe_parse_price_valid(self, dry_run_executor: PolymarketExecutor) -> None:
        """Valid price string should parse correctly."""
        assert dry_run_executor._safe_parse_price("0.55") == 0.55
        assert dry_run_executor._safe_parse_price(0.55) == 0.55
        assert dry_run_executor._safe_parse_price("1.0") == 1.0

    def test_safe_parse_price_none(self, dry_run_executor: PolymarketExecutor) -> None:
        """None should return None."""
        assert dry_run_executor._safe_parse_price(None) is None

    def test_safe_parse_price_invalid(self, dry_run_executor: PolymarketExecutor) -> None:
        """Invalid values should return None."""
        assert dry_run_executor._safe_parse_price("invalid") is None
        assert dry_run_executor._safe_parse_price({}) is None
        assert dry_run_executor._safe_parse_price([]) is None

    def test_safe_parse_price_zero(self, dry_run_executor: PolymarketExecutor) -> None:
        """Zero should return None (invalid price)."""
        assert dry_run_executor._safe_parse_price(0) is None
        assert dry_run_executor._safe_parse_price("0") is None

    def test_safe_parse_price_negative(self, dry_run_executor: PolymarketExecutor) -> None:
        """Negative should return None (invalid price)."""
        assert dry_run_executor._safe_parse_price(-0.5) is None


class TestOrderResponseParsing:
    """Test suite for order response parsing."""

    def test_parse_order_response_success(
        self, dry_run_executor: PolymarketExecutor
    ) -> None:
        """Successful order response should parse correctly."""
        response = {
            "orderID": "order_123",
            "status": "FILLED",
            "price": "0.55",
            "size": "100.0",
            "fee": "0.50",
        }
        result = dry_run_executor._parse_order_response(response, 0.50, 100.0)

        assert result.order_id == "order_123"
        assert result.status == OrderStatus.FILLED
        assert result.filled_price == 0.55
        assert result.filled_size == 100.0
        assert result.fees_paid == 0.50
        assert result.error_message is None

    def test_parse_order_response_failed(
        self, dry_run_executor: PolymarketExecutor
    ) -> None:
        """Failed order response should include error message."""
        response = {
            "id": "order_456",
            "status": "REJECTED",
            "error": "Insufficient balance",
        }
        result = dry_run_executor._parse_order_response(response, 0.50, 100.0)

        assert result.order_id == "order_456"
        assert result.status == OrderStatus.REJECTED
        assert result.error_message == "Insufficient balance"

    def test_parse_order_response_missing_fields(
        self, dry_run_executor: PolymarketExecutor
    ) -> None:
        """Missing fields should use fallbacks."""
        response = {"status": "FILLED"}
        result = dry_run_executor._parse_order_response(response, 0.50, 100.0)

        assert result.order_id.startswith("unknown_")
        assert result.status == OrderStatus.FILLED
        assert result.filled_price == 0.50  # Fallback to expected
        assert result.filled_size == 100.0  # Fallback to expected


class TestOrderStatusParsing:
    """Test suite for order status parsing."""

    def test_parse_filled_status(self, dry_run_executor: PolymarketExecutor) -> None:
        """FILLED status should parse correctly."""
        assert (
            dry_run_executor._parse_order_status({"status": "FILLED"})
            == OrderStatus.FILLED
        )
        assert (
            dry_run_executor._parse_order_status({"status": "filled"})
            == OrderStatus.FILLED
        )

    def test_parse_matched_status(self, dry_run_executor: PolymarketExecutor) -> None:
        """MATCHED status should map to FILLED."""
        assert (
            dry_run_executor._parse_order_status({"status": "MATCHED"})
            == OrderStatus.FILLED
        )

    def test_parse_unknown_status(self, dry_run_executor: PolymarketExecutor) -> None:
        """Unknown status should default to PENDING."""
        assert (
            dry_run_executor._parse_order_status({"status": "UNKNOWN"})
            == OrderStatus.PENDING
        )
        assert (
            dry_run_executor._parse_order_status({}) == OrderStatus.PENDING
        )


class TestTradeSignal:
    """Test suite for TradeSignal model."""

    def test_trade_signal_immutability(self, dummy_signal: TradeSignal) -> None:
        """Verify TradeSignal is immutable."""
        with pytest.raises(ValidationError):
            dummy_signal.size_usdc = 200.0  # type: ignore[misc]

    def test_trade_signal_requires_positive_size(self) -> None:
        """Verify size_usdc must be positive."""
        with pytest.raises(ValidationError):
            TradeSignal(
                token_id="test",
                side=Side.BUY,
                size_usdc=-100.0,  # Invalid: negative
                reason="Test",
            )

    def test_trade_signal_requires_nonzero_size(self) -> None:
        """Verify size_usdc must be non-zero."""
        with pytest.raises(ValidationError):
            TradeSignal(
                token_id="test",
                side=Side.BUY,
                size_usdc=0.0,  # Invalid: zero
                reason="Test",
            )


class TestExecutionResult:
    """Test suite for ExecutionResult model."""

    def test_execution_result_immutability(self) -> None:
        """Verify ExecutionResult is immutable."""
        result = ExecutionResult(
            order_id="test_order",
            status=OrderStatus.FILLED,
            filled_price=0.55,
        )
        with pytest.raises(ValidationError):
            result.filled_price = 0.60  # type: ignore[misc]

    def test_execution_result_with_all_fields(self) -> None:
        """Verify ExecutionResult accepts all fields."""
        result = ExecutionResult(
            order_id="test_order",
            status=OrderStatus.FILLED,
            filled_price=0.55,
            filled_size=100.0,
            fees_paid=0.50,
            error_message=None,
        )
        assert result.filled_size == 100.0
        assert result.fees_paid == 0.50

    def test_execution_result_default_fields(self) -> None:
        """Verify ExecutionResult has sensible defaults."""
        result = ExecutionResult(
            order_id="test_order",
            status=OrderStatus.FILLED,
            filled_price=0.55,
        )
        assert result.filled_size == 0.0
        assert result.fees_paid == 0.0
        assert result.error_message is None
