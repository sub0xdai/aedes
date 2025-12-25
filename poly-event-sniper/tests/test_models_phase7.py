"""Tests for Phase 7 foundation models: Position, Order, and new enums."""

import uuid
from time import time

import pytest
from pydantic import ValidationError

from src.models import (
    Order,
    OrderType,
    Position,
    PositionSide,
    Side,
    TimeInForce,
)


class TestPositionSideEnum:
    """Tests for PositionSide enum."""

    def test_long_value(self) -> None:
        """PositionSide.LONG should have value 'LONG'."""
        assert PositionSide.LONG == "LONG"
        assert PositionSide.LONG.value == "LONG"

    def test_short_value(self) -> None:
        """PositionSide.SHORT should have value 'SHORT'."""
        assert PositionSide.SHORT == "SHORT"
        assert PositionSide.SHORT.value == "SHORT"

    def test_flat_value(self) -> None:
        """PositionSide.FLAT should have value 'FLAT'."""
        assert PositionSide.FLAT == "FLAT"
        assert PositionSide.FLAT.value == "FLAT"


class TestOrderTypeEnum:
    """Tests for OrderType enum."""

    def test_market_value(self) -> None:
        """OrderType.MARKET should have value 'MARKET'."""
        assert OrderType.MARKET == "MARKET"
        assert OrderType.MARKET.value == "MARKET"

    def test_limit_value(self) -> None:
        """OrderType.LIMIT should have value 'LIMIT'."""
        assert OrderType.LIMIT == "LIMIT"
        assert OrderType.LIMIT.value == "LIMIT"

    def test_fok_value(self) -> None:
        """OrderType.FOK should have value 'FOK'."""
        assert OrderType.FOK == "FOK"
        assert OrderType.FOK.value == "FOK"


class TestTimeInForceEnum:
    """Tests for TimeInForce enum."""

    def test_gtc_value(self) -> None:
        """TimeInForce.GTC should have value 'GTC'."""
        assert TimeInForce.GTC == "GTC"
        assert TimeInForce.GTC.value == "GTC"

    def test_ioc_value(self) -> None:
        """TimeInForce.IOC should have value 'IOC'."""
        assert TimeInForce.IOC == "IOC"
        assert TimeInForce.IOC.value == "IOC"

    def test_fok_value(self) -> None:
        """TimeInForce.FOK should have value 'FOK'."""
        assert TimeInForce.FOK == "FOK"
        assert TimeInForce.FOK.value == "FOK"


class TestPosition:
    """Tests for Position model."""

    def test_create_long_position(self) -> None:
        """Can create a LONG position with required fields."""
        pos = Position(
            token_id="token_123",
            side=PositionSide.LONG,
            quantity=100.0,
            avg_entry_price=0.50,
            current_price=0.60,
        )
        assert pos.token_id == "token_123"
        assert pos.side == PositionSide.LONG
        assert pos.quantity == 100.0
        assert pos.avg_entry_price == 0.50
        assert pos.current_price == 0.60

    def test_create_short_position(self) -> None:
        """Can create a SHORT position."""
        pos = Position(
            token_id="token_456",
            side=PositionSide.SHORT,
            quantity=50.0,
            avg_entry_price=0.70,
            current_price=0.60,
        )
        assert pos.side == PositionSide.SHORT

    def test_position_is_immutable(self) -> None:
        """Position model should be frozen (immutable)."""
        pos = Position(
            token_id="token_123",
            side=PositionSide.LONG,
            quantity=100.0,
            avg_entry_price=0.50,
            current_price=0.60,
        )
        with pytest.raises(ValidationError):
            pos.quantity = 200.0  # type: ignore[misc]

    def test_position_has_opened_at_default(self) -> None:
        """Position should have opened_at timestamp defaulting to now."""
        before = time()
        pos = Position(
            token_id="token_123",
            side=PositionSide.LONG,
            quantity=100.0,
            avg_entry_price=0.50,
            current_price=0.60,
        )
        after = time()
        assert before <= pos.opened_at <= after

    def test_unrealized_pnl_long_profit(self) -> None:
        """LONG position with price increase should have positive PnL."""
        pos = Position(
            token_id="token_123",
            side=PositionSide.LONG,
            quantity=100.0,
            avg_entry_price=0.50,
            current_price=0.60,
        )
        # PnL = quantity * (current - entry) = 100 * (0.60 - 0.50) = 10.0
        assert pos.unrealized_pnl == pytest.approx(10.0)

    def test_unrealized_pnl_long_loss(self) -> None:
        """LONG position with price decrease should have negative PnL."""
        pos = Position(
            token_id="token_123",
            side=PositionSide.LONG,
            quantity=100.0,
            avg_entry_price=0.50,
            current_price=0.40,
        )
        # PnL = 100 * (0.40 - 0.50) = -10.0
        assert pos.unrealized_pnl == pytest.approx(-10.0)

    def test_unrealized_pnl_short_profit(self) -> None:
        """SHORT position with price decrease should have positive PnL."""
        pos = Position(
            token_id="token_123",
            side=PositionSide.SHORT,
            quantity=100.0,
            avg_entry_price=0.60,
            current_price=0.50,
        )
        # SHORT PnL = -1 * quantity * (current - entry) = -100 * (0.50 - 0.60) = 10.0
        assert pos.unrealized_pnl == pytest.approx(10.0)

    def test_unrealized_pnl_short_loss(self) -> None:
        """SHORT position with price increase should have negative PnL."""
        pos = Position(
            token_id="token_123",
            side=PositionSide.SHORT,
            quantity=100.0,
            avg_entry_price=0.50,
            current_price=0.60,
        )
        # SHORT PnL = -100 * (0.60 - 0.50) = -10.0
        assert pos.unrealized_pnl == pytest.approx(-10.0)

    def test_unrealized_pnl_flat_is_zero(self) -> None:
        """FLAT position should always have zero PnL."""
        pos = Position(
            token_id="token_123",
            side=PositionSide.FLAT,
            quantity=0.0,
            avg_entry_price=0.50,
            current_price=0.60,
        )
        assert pos.unrealized_pnl == 0.0

    def test_market_value(self) -> None:
        """Market value should be quantity * current_price."""
        pos = Position(
            token_id="token_123",
            side=PositionSide.LONG,
            quantity=100.0,
            avg_entry_price=0.50,
            current_price=0.60,
        )
        # market_value = 100 * 0.60 = 60.0
        assert pos.market_value == pytest.approx(60.0)

    def test_quantity_must_be_non_negative(self) -> None:
        """Quantity must be >= 0."""
        with pytest.raises(ValidationError):
            Position(
                token_id="token_123",
                side=PositionSide.LONG,
                quantity=-10.0,
                avg_entry_price=0.50,
                current_price=0.60,
            )

    def test_price_bounds_entry(self) -> None:
        """Entry price must be in [0, 1] for Polymarket binary markets."""
        with pytest.raises(ValidationError):
            Position(
                token_id="token_123",
                side=PositionSide.LONG,
                quantity=100.0,
                avg_entry_price=1.5,  # Invalid: > 1
                current_price=0.60,
            )

    def test_price_bounds_current(self) -> None:
        """Current price must be in [0, 1] for Polymarket binary markets."""
        with pytest.raises(ValidationError):
            Position(
                token_id="token_123",
                side=PositionSide.LONG,
                quantity=100.0,
                avg_entry_price=0.50,
                current_price=-0.1,  # Invalid: < 0
            )


class TestOrder:
    """Tests for Order model."""

    def test_create_order_with_required_fields(self) -> None:
        """Can create Order with required fields."""
        order = Order(
            token_id="token_123",
            side=Side.BUY,
            quantity=100.0,
            reason="Test order",
        )
        assert order.token_id == "token_123"
        assert order.side == Side.BUY
        assert order.quantity == 100.0
        assert order.reason == "Test order"

    def test_order_has_client_order_id_default(self) -> None:
        """Order should generate unique client_order_id by default."""
        order1 = Order(
            token_id="token_123",
            side=Side.BUY,
            quantity=100.0,
            reason="Test order",
        )
        order2 = Order(
            token_id="token_123",
            side=Side.BUY,
            quantity=100.0,
            reason="Test order",
        )
        # Each order gets unique ID
        assert order1.client_order_id != order2.client_order_id
        # ID is hex string (UUID hex format)
        assert len(order1.client_order_id) == 32  # UUID hex is 32 chars

    def test_order_type_defaults_to_fok(self) -> None:
        """OrderType should default to FOK."""
        order = Order(
            token_id="token_123",
            side=Side.BUY,
            quantity=100.0,
            reason="Test order",
        )
        assert order.order_type == OrderType.FOK

    def test_time_in_force_defaults_to_fok(self) -> None:
        """TimeInForce should default to FOK."""
        order = Order(
            token_id="token_123",
            side=Side.BUY,
            quantity=100.0,
            reason="Test order",
        )
        assert order.time_in_force == TimeInForce.FOK

    def test_order_is_immutable(self) -> None:
        """Order model should be frozen (immutable)."""
        order = Order(
            token_id="token_123",
            side=Side.BUY,
            quantity=100.0,
            reason="Test order",
        )
        with pytest.raises(ValidationError):
            order.quantity = 200.0  # type: ignore[misc]

    def test_order_has_created_at_default(self) -> None:
        """Order should have created_at timestamp defaulting to now."""
        before = time()
        order = Order(
            token_id="token_123",
            side=Side.BUY,
            quantity=100.0,
            reason="Test order",
        )
        after = time()
        assert before <= order.created_at <= after

    def test_quantity_must_be_positive(self) -> None:
        """Quantity must be > 0."""
        with pytest.raises(ValidationError):
            Order(
                token_id="token_123",
                side=Side.BUY,
                quantity=0.0,  # Invalid: must be > 0
                reason="Test order",
            )

    def test_limit_price_optional(self) -> None:
        """Limit price should be optional (None for market orders)."""
        order = Order(
            token_id="token_123",
            side=Side.BUY,
            quantity=100.0,
            reason="Test order",
        )
        assert order.limit_price is None

    def test_limit_price_bounds(self) -> None:
        """Limit price must be in [0, 1] when specified."""
        # Valid limit price
        order = Order(
            token_id="token_123",
            side=Side.BUY,
            quantity=100.0,
            limit_price=0.50,
            reason="Test order",
        )
        assert order.limit_price == 0.50

        # Invalid: > 1
        with pytest.raises(ValidationError):
            Order(
                token_id="token_123",
                side=Side.BUY,
                quantity=100.0,
                limit_price=1.5,
                reason="Test order",
            )

    def test_order_with_all_fields(self) -> None:
        """Can create Order with all fields specified."""
        order = Order(
            client_order_id="custom_id_123",
            token_id="token_456",
            side=Side.SELL,
            quantity=50.0,
            order_type=OrderType.LIMIT,
            limit_price=0.75,
            time_in_force=TimeInForce.GTC,
            reason="Limit sell order",
        )
        assert order.client_order_id == "custom_id_123"
        assert order.token_id == "token_456"
        assert order.side == Side.SELL
        assert order.quantity == 50.0
        assert order.order_type == OrderType.LIMIT
        assert order.limit_price == 0.75
        assert order.time_in_force == TimeInForce.GTC
        assert order.reason == "Limit sell order"
