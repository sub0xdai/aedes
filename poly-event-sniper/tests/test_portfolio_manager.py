"""Tests for Phase 7.3 PortfolioManager."""

from pathlib import Path
from time import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.managers.portfolio import PortfolioManager
from src.models import (
    ExecutionResult,
    Order,
    OrderStatus,
    OrderType,
    Position,
    PositionSide,
    Side,
)
from src.persistence import DatabaseManager


@pytest.fixture
async def db(tmp_path: Path) -> DatabaseManager:
    """Create a temporary database for testing."""
    db_path = tmp_path / "test.db"
    db_manager = DatabaseManager(db_path)
    await db_manager.connect()
    yield db_manager
    await db_manager.disconnect()


@pytest.fixture
def mock_executor() -> AsyncMock:
    """Create a mock executor with get_balance."""
    executor = AsyncMock()
    executor.get_balance = AsyncMock(return_value=1000.0)
    return executor


class TestPortfolioManagerInit:
    """Tests for PortfolioManager initialization."""

    @pytest.mark.asyncio
    async def test_init_with_defaults(self, db: DatabaseManager) -> None:
        """Can create PortfolioManager with default limits."""
        pm = PortfolioManager(database=db)
        assert pm._max_position_size == 500.0
        assert pm._max_positions == 10

    @pytest.mark.asyncio
    async def test_init_with_custom_limits(self, db: DatabaseManager) -> None:
        """Can create PortfolioManager with custom limits."""
        pm = PortfolioManager(
            database=db,
            max_position_size=1000.0,
            max_positions=20,
        )
        assert pm._max_position_size == 1000.0
        assert pm._max_positions == 20


class TestPortfolioManagerLoadState:
    """Tests for load_state method."""

    @pytest.mark.asyncio
    async def test_load_state_fetches_balance(
        self, db: DatabaseManager, mock_executor: AsyncMock
    ) -> None:
        """load_state should fetch cash balance from executor."""
        pm = PortfolioManager(database=db)
        await pm.load_state(mock_executor)

        mock_executor.get_balance.assert_called_once()
        assert pm.cash_balance == 1000.0

    @pytest.mark.asyncio
    async def test_load_state_hydrates_positions(
        self, db: DatabaseManager, mock_executor: AsyncMock
    ) -> None:
        """load_state should load positions from database."""
        # Insert positions into database
        pos1 = Position(
            token_id="token_1",
            side=PositionSide.LONG,
            quantity=100.0,
            avg_entry_price=0.50,
            current_price=0.55,
        )
        pos2 = Position(
            token_id="token_2",
            side=PositionSide.SHORT,
            quantity=50.0,
            avg_entry_price=0.70,
            current_price=0.60,
        )
        await db.upsert_position(pos1)
        await db.upsert_position(pos2)

        pm = PortfolioManager(database=db)
        await pm.load_state(mock_executor)

        assert len(pm.positions) == 2
        assert "token_1" in pm.positions
        assert "token_2" in pm.positions


class TestPortfolioManagerCheckOrder:
    """Tests for check_order validation."""

    @pytest.mark.asyncio
    async def test_check_order_buy_sufficient_cash(
        self, db: DatabaseManager, mock_executor: AsyncMock
    ) -> None:
        """BUY order with sufficient cash should be valid."""
        pm = PortfolioManager(database=db)
        await pm.load_state(mock_executor)  # 1000 USDC balance

        order = Order(
            token_id="token_new",
            side=Side.BUY,
            quantity=100.0,
            limit_price=0.50,
            reason="Test buy",
        )

        is_valid, reason = pm.check_order(order)
        assert is_valid is True
        assert reason == ""

    @pytest.mark.asyncio
    async def test_check_order_buy_insufficient_cash(
        self, db: DatabaseManager, mock_executor: AsyncMock
    ) -> None:
        """BUY order exceeding cash should be rejected."""
        mock_executor.get_balance.return_value = 100.0  # Only 100 USDC
        pm = PortfolioManager(database=db)
        await pm.load_state(mock_executor)

        order = Order(
            token_id="token_new",
            side=Side.BUY,
            quantity=500.0,  # 500 * 0.50 = 250 > 100
            limit_price=0.50,
            reason="Test buy",
        )

        is_valid, reason = pm.check_order(order)
        assert is_valid is False
        assert "Insufficient cash" in reason

    @pytest.mark.asyncio
    async def test_check_order_sell_with_position(
        self, db: DatabaseManager, mock_executor: AsyncMock
    ) -> None:
        """SELL order with sufficient position should be valid."""
        # Create position first
        pos = Position(
            token_id="token_with_pos",
            side=PositionSide.LONG,
            quantity=100.0,
            avg_entry_price=0.50,
            current_price=0.55,
        )
        await db.upsert_position(pos)

        pm = PortfolioManager(database=db)
        await pm.load_state(mock_executor)

        order = Order(
            token_id="token_with_pos",
            side=Side.SELL,
            quantity=50.0,  # Selling 50 of 100
            reason="Test sell",
        )

        is_valid, reason = pm.check_order(order)
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_check_order_sell_insufficient_position(
        self, db: DatabaseManager, mock_executor: AsyncMock
    ) -> None:
        """SELL order exceeding position should be rejected."""
        pos = Position(
            token_id="token_small",
            side=PositionSide.LONG,
            quantity=50.0,
            avg_entry_price=0.50,
            current_price=0.55,
        )
        await db.upsert_position(pos)

        pm = PortfolioManager(database=db)
        await pm.load_state(mock_executor)

        order = Order(
            token_id="token_small",
            side=Side.SELL,
            quantity=100.0,  # Selling 100 but only have 50
            reason="Test sell",
        )

        is_valid, reason = pm.check_order(order)
        assert is_valid is False
        assert "Insufficient position" in reason

    @pytest.mark.asyncio
    async def test_check_order_sell_no_position(
        self, db: DatabaseManager, mock_executor: AsyncMock
    ) -> None:
        """SELL order with no position should be rejected."""
        pm = PortfolioManager(database=db)
        await pm.load_state(mock_executor)

        order = Order(
            token_id="token_no_pos",
            side=Side.SELL,
            quantity=50.0,
            reason="Test sell",
        )

        is_valid, reason = pm.check_order(order)
        assert is_valid is False
        assert "Insufficient position" in reason

    @pytest.mark.asyncio
    async def test_check_order_max_positions_reached(
        self, db: DatabaseManager, mock_executor: AsyncMock
    ) -> None:
        """BUY order for new token when max positions reached should be rejected."""
        # Create max_positions existing positions
        for i in range(10):  # Default max is 10
            pos = Position(
                token_id=f"token_{i}",
                side=PositionSide.LONG,
                quantity=10.0,
                avg_entry_price=0.50,
                current_price=0.55,
            )
            await db.upsert_position(pos)

        pm = PortfolioManager(database=db, max_positions=10)
        await pm.load_state(mock_executor)

        order = Order(
            token_id="token_new",  # New token
            side=Side.BUY,
            quantity=10.0,
            limit_price=0.50,
            reason="Test buy",
        )

        is_valid, reason = pm.check_order(order)
        assert is_valid is False
        assert "Max positions reached" in reason

    @pytest.mark.asyncio
    async def test_check_order_buy_existing_position_ok(
        self, db: DatabaseManager, mock_executor: AsyncMock
    ) -> None:
        """BUY order for existing position at max positions should be valid."""
        # Create max positions including the one we want to add to
        for i in range(10):
            pos = Position(
                token_id=f"token_{i}",
                side=PositionSide.LONG,
                quantity=10.0,
                avg_entry_price=0.50,
                current_price=0.55,
            )
            await db.upsert_position(pos)

        pm = PortfolioManager(database=db, max_positions=10)
        await pm.load_state(mock_executor)

        order = Order(
            token_id="token_0",  # Existing position
            side=Side.BUY,
            quantity=10.0,
            limit_price=0.50,
            reason="Add to position",
        )

        is_valid, reason = pm.check_order(order)
        assert is_valid is True


class TestPortfolioManagerOnFill:
    """Tests for on_fill position updates."""

    @pytest.mark.asyncio
    async def test_on_fill_creates_new_position(
        self, db: DatabaseManager, mock_executor: AsyncMock
    ) -> None:
        """on_fill should create new position for BUY of new token."""
        pm = PortfolioManager(database=db)
        await pm.load_state(mock_executor)

        order = Order(
            token_id="token_new",
            side=Side.BUY,
            quantity=100.0,
            reason="New position",
        )
        result = ExecutionResult(
            order_id="order_123",
            status=OrderStatus.FILLED,
            filled_price=0.50,
            filled_size=100.0,
            fees_paid=0.50,
        )

        await pm.on_fill(order, result)

        assert "token_new" in pm.positions
        pos = pm.positions["token_new"]
        assert pos.side == PositionSide.LONG
        assert pos.quantity == 100.0
        assert pos.avg_entry_price == 0.50

    @pytest.mark.asyncio
    async def test_on_fill_adds_to_existing_position(
        self, db: DatabaseManager, mock_executor: AsyncMock
    ) -> None:
        """on_fill should add to existing position and update avg price."""
        # Create initial position
        pos = Position(
            token_id="token_add",
            side=PositionSide.LONG,
            quantity=100.0,
            avg_entry_price=0.40,
            current_price=0.45,
        )
        await db.upsert_position(pos)

        pm = PortfolioManager(database=db)
        await pm.load_state(mock_executor)

        order = Order(
            token_id="token_add",
            side=Side.BUY,
            quantity=100.0,
            reason="Add to position",
        )
        result = ExecutionResult(
            order_id="order_456",
            status=OrderStatus.FILLED,
            filled_price=0.60,
            filled_size=100.0,
            fees_paid=0.50,
        )

        await pm.on_fill(order, result)

        pos = pm.positions["token_add"]
        assert pos.quantity == 200.0
        # Avg price: (100*0.40 + 100*0.60) / 200 = 0.50
        assert pos.avg_entry_price == pytest.approx(0.50)

    @pytest.mark.asyncio
    async def test_on_fill_reduces_position(
        self, db: DatabaseManager, mock_executor: AsyncMock
    ) -> None:
        """on_fill SELL should reduce position quantity."""
        pos = Position(
            token_id="token_reduce",
            side=PositionSide.LONG,
            quantity=100.0,
            avg_entry_price=0.50,
            current_price=0.55,
        )
        await db.upsert_position(pos)

        pm = PortfolioManager(database=db)
        await pm.load_state(mock_executor)

        order = Order(
            token_id="token_reduce",
            side=Side.SELL,
            quantity=40.0,
            reason="Partial close",
        )
        result = ExecutionResult(
            order_id="order_789",
            status=OrderStatus.FILLED,
            filled_price=0.60,
            filled_size=40.0,
            fees_paid=0.20,
        )

        await pm.on_fill(order, result)

        pos = pm.positions["token_reduce"]
        assert pos.quantity == 60.0
        # Avg entry price unchanged on sells
        assert pos.avg_entry_price == 0.50

    @pytest.mark.asyncio
    async def test_on_fill_closes_position(
        self, db: DatabaseManager, mock_executor: AsyncMock
    ) -> None:
        """on_fill SELL of entire position should remove it."""
        pos = Position(
            token_id="token_close",
            side=PositionSide.LONG,
            quantity=100.0,
            avg_entry_price=0.50,
            current_price=0.60,
        )
        await db.upsert_position(pos)

        pm = PortfolioManager(database=db)
        await pm.load_state(mock_executor)

        order = Order(
            token_id="token_close",
            side=Side.SELL,
            quantity=100.0,
            reason="Close position",
        )
        result = ExecutionResult(
            order_id="order_close",
            status=OrderStatus.FILLED,
            filled_price=0.60,
            filled_size=100.0,
            fees_paid=0.50,
        )

        await pm.on_fill(order, result)

        assert "token_close" not in pm.positions

    @pytest.mark.asyncio
    async def test_on_fill_persists_to_database(
        self, db: DatabaseManager, mock_executor: AsyncMock
    ) -> None:
        """on_fill should persist position changes to database."""
        pm = PortfolioManager(database=db)
        await pm.load_state(mock_executor)

        order = Order(
            token_id="token_persist",
            side=Side.BUY,
            quantity=100.0,
            reason="Test persistence",
        )
        result = ExecutionResult(
            order_id="order_persist",
            status=OrderStatus.FILLED,
            filled_price=0.50,
            filled_size=100.0,
            fees_paid=0.50,
        )

        await pm.on_fill(order, result)

        # Read directly from database
        stored = await db.get_position("token_persist")
        assert stored is not None
        assert stored.quantity == 100.0


class TestPortfolioManagerOnPriceUpdate:
    """Tests for on_price_update mark-to-market."""

    @pytest.mark.asyncio
    async def test_on_price_update_updates_current_price(
        self, db: DatabaseManager, mock_executor: AsyncMock
    ) -> None:
        """on_price_update should update position's current_price."""
        pos = Position(
            token_id="token_mtm",
            side=PositionSide.LONG,
            quantity=100.0,
            avg_entry_price=0.50,
            current_price=0.50,
        )
        await db.upsert_position(pos)

        pm = PortfolioManager(database=db)
        await pm.load_state(mock_executor)

        await pm.on_price_update("token_mtm", 0.65)

        assert pm.positions["token_mtm"].current_price == 0.65

    @pytest.mark.asyncio
    async def test_on_price_update_ignores_unknown_token(
        self, db: DatabaseManager, mock_executor: AsyncMock
    ) -> None:
        """on_price_update for unknown token should not raise."""
        pm = PortfolioManager(database=db)
        await pm.load_state(mock_executor)

        # Should not raise
        await pm.on_price_update("unknown_token", 0.50)

    @pytest.mark.asyncio
    async def test_on_price_update_affects_pnl(
        self, db: DatabaseManager, mock_executor: AsyncMock
    ) -> None:
        """on_price_update should affect unrealized_pnl calculation."""
        pos = Position(
            token_id="token_pnl",
            side=PositionSide.LONG,
            quantity=100.0,
            avg_entry_price=0.50,
            current_price=0.50,
        )
        await db.upsert_position(pos)

        pm = PortfolioManager(database=db)
        await pm.load_state(mock_executor)

        # Initial PnL should be 0
        assert pm.positions["token_pnl"].unrealized_pnl == pytest.approx(0.0)

        # Update price
        await pm.on_price_update("token_pnl", 0.60)

        # PnL should now be 100 * (0.60 - 0.50) = 10.0
        assert pm.positions["token_pnl"].unrealized_pnl == pytest.approx(10.0)


class TestPortfolioManagerProperties:
    """Tests for PortfolioManager properties."""

    @pytest.mark.asyncio
    async def test_total_unrealized_pnl(
        self, db: DatabaseManager, mock_executor: AsyncMock
    ) -> None:
        """total_unrealized_pnl should sum all position PnLs."""
        pos1 = Position(
            token_id="token_1",
            side=PositionSide.LONG,
            quantity=100.0,
            avg_entry_price=0.50,
            current_price=0.60,  # +10 PnL
        )
        pos2 = Position(
            token_id="token_2",
            side=PositionSide.SHORT,
            quantity=100.0,
            avg_entry_price=0.70,
            current_price=0.60,  # +10 PnL (short)
        )
        await db.upsert_position(pos1)
        await db.upsert_position(pos2)

        pm = PortfolioManager(database=db)
        await pm.load_state(mock_executor)

        # Total should be 10 + 10 = 20
        assert pm.total_unrealized_pnl == pytest.approx(20.0)

    @pytest.mark.asyncio
    async def test_total_market_value(
        self, db: DatabaseManager, mock_executor: AsyncMock
    ) -> None:
        """total_market_value should sum all position market values."""
        pos1 = Position(
            token_id="token_1",
            side=PositionSide.LONG,
            quantity=100.0,
            avg_entry_price=0.50,
            current_price=0.60,  # 60 USDC
        )
        pos2 = Position(
            token_id="token_2",
            side=PositionSide.LONG,
            quantity=50.0,
            avg_entry_price=0.40,
            current_price=0.80,  # 40 USDC
        )
        await db.upsert_position(pos1)
        await db.upsert_position(pos2)

        pm = PortfolioManager(database=db)
        await pm.load_state(mock_executor)

        # Total should be 60 + 40 = 100
        assert pm.total_market_value == pytest.approx(100.0)
