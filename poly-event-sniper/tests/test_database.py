"""Tests for Phase 7.2 SQLite persistence layer."""

import asyncio
from pathlib import Path
from time import time

import pytest

from src.models import (
    ExecutionResult,
    Order,
    OrderStatus,
    OrderType,
    Position,
    PositionSide,
    Side,
    TimeInForce,
)
from src.persistence import DatabaseManager


class TestDatabaseManagerLifecycle:
    """Tests for DatabaseManager connection lifecycle."""

    @pytest.mark.asyncio
    async def test_connect_creates_database_file(self, tmp_path: Path) -> None:
        """Database file should be created on connect."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)
        await db.connect()
        try:
            assert db_path.exists()
        finally:
            await db.disconnect()

    @pytest.mark.asyncio
    async def test_connect_creates_tables(self, tmp_path: Path) -> None:
        """Database tables should be created on connect."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)
        await db.connect()
        try:
            # Verify tables exist by checking schema
            assert await db._table_exists("trades")
            assert await db._table_exists("positions")
            assert await db._table_exists("orders")
        finally:
            await db.disconnect()

    @pytest.mark.asyncio
    async def test_async_context_manager(self, tmp_path: Path) -> None:
        """DatabaseManager should work as async context manager."""
        db_path = tmp_path / "test.db"
        async with DatabaseManager(db_path) as db:
            assert db_path.exists()
        # After context, connection should be closed gracefully

    @pytest.mark.asyncio
    async def test_disconnect_is_idempotent(self, tmp_path: Path) -> None:
        """Calling disconnect multiple times should not raise."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)
        await db.connect()
        await db.disconnect()
        await db.disconnect()  # Should not raise


class TestTradeOperations:
    """Tests for trade CRUD operations."""

    @pytest.mark.asyncio
    async def test_insert_trade(self, tmp_path: Path) -> None:
        """Should insert a trade record."""
        db_path = tmp_path / "test.db"
        async with DatabaseManager(db_path) as db:
            order = Order(
                client_order_id="order_123",
                token_id="token_abc",
                side=Side.BUY,
                quantity=100.0,
                reason="Test trade",
            )
            result = ExecutionResult(
                order_id="exchange_order_456",
                status=OrderStatus.FILLED,
                filled_price=0.50,
                filled_size=100.0,
                fees_paid=0.50,
            )

            await db.insert_trade(order, result)

            # Verify insertion
            trades = await db.get_trades(token_id="token_abc")
            assert len(trades) == 1
            assert trades[0]["order_id"] == "exchange_order_456"
            assert trades[0]["client_order_id"] == "order_123"
            assert trades[0]["token_id"] == "token_abc"
            assert trades[0]["side"] == "BUY"
            assert trades[0]["quantity"] == 100.0
            assert trades[0]["price"] == 0.50

    @pytest.mark.asyncio
    async def test_get_trades_filters_by_token(self, tmp_path: Path) -> None:
        """get_trades should filter by token_id when specified."""
        db_path = tmp_path / "test.db"
        async with DatabaseManager(db_path) as db:
            # Insert trades for different tokens
            order1 = Order(
                token_id="token_a",
                side=Side.BUY,
                quantity=50.0,
                reason="Trade 1",
            )
            result1 = ExecutionResult(
                order_id="order_1",
                status=OrderStatus.FILLED,
                filled_price=0.30,
            )
            await db.insert_trade(order1, result1)

            order2 = Order(
                token_id="token_b",
                side=Side.SELL,
                quantity=75.0,
                reason="Trade 2",
            )
            result2 = ExecutionResult(
                order_id="order_2",
                status=OrderStatus.FILLED,
                filled_price=0.70,
            )
            await db.insert_trade(order2, result2)

            # Filter by token
            trades_a = await db.get_trades(token_id="token_a")
            trades_b = await db.get_trades(token_id="token_b")

            assert len(trades_a) == 1
            assert trades_a[0]["token_id"] == "token_a"
            assert len(trades_b) == 1
            assert trades_b[0]["token_id"] == "token_b"

    @pytest.mark.asyncio
    async def test_get_trades_returns_all_without_filter(self, tmp_path: Path) -> None:
        """get_trades should return all trades when no filter specified."""
        db_path = tmp_path / "test.db"
        async with DatabaseManager(db_path) as db:
            for i in range(3):
                order = Order(
                    token_id=f"token_{i}",
                    side=Side.BUY,
                    quantity=10.0,
                    reason=f"Trade {i}",
                )
                result = ExecutionResult(
                    order_id=f"order_{i}",
                    status=OrderStatus.FILLED,
                    filled_price=0.50,
                )
                await db.insert_trade(order, result)

            all_trades = await db.get_trades()
            assert len(all_trades) == 3


class TestPositionOperations:
    """Tests for position CRUD operations."""

    @pytest.mark.asyncio
    async def test_upsert_position_creates(self, tmp_path: Path) -> None:
        """upsert_position should create new position if not exists."""
        db_path = tmp_path / "test.db"
        async with DatabaseManager(db_path) as db:
            position = Position(
                token_id="token_123",
                side=PositionSide.LONG,
                quantity=100.0,
                avg_entry_price=0.50,
                current_price=0.55,
                opened_at=time(),
            )

            await db.upsert_position(position)

            stored = await db.get_position("token_123")
            assert stored is not None
            assert stored.token_id == "token_123"
            assert stored.side == PositionSide.LONG
            assert stored.quantity == 100.0
            assert stored.avg_entry_price == 0.50

    @pytest.mark.asyncio
    async def test_upsert_position_updates(self, tmp_path: Path) -> None:
        """upsert_position should update existing position."""
        db_path = tmp_path / "test.db"
        async with DatabaseManager(db_path) as db:
            # Create initial position
            position1 = Position(
                token_id="token_123",
                side=PositionSide.LONG,
                quantity=100.0,
                avg_entry_price=0.50,
                current_price=0.55,
            )
            await db.upsert_position(position1)

            # Update with new quantity
            position2 = Position(
                token_id="token_123",
                side=PositionSide.LONG,
                quantity=150.0,
                avg_entry_price=0.52,
                current_price=0.60,
            )
            await db.upsert_position(position2)

            stored = await db.get_position("token_123")
            assert stored is not None
            assert stored.quantity == 150.0
            assert stored.avg_entry_price == 0.52

    @pytest.mark.asyncio
    async def test_get_position_returns_none_if_not_exists(self, tmp_path: Path) -> None:
        """get_position should return None for non-existent token."""
        db_path = tmp_path / "test.db"
        async with DatabaseManager(db_path) as db:
            result = await db.get_position("nonexistent_token")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_all_positions(self, tmp_path: Path) -> None:
        """get_all_positions should return all positions."""
        db_path = tmp_path / "test.db"
        async with DatabaseManager(db_path) as db:
            for i in range(3):
                position = Position(
                    token_id=f"token_{i}",
                    side=PositionSide.LONG,
                    quantity=float(i * 10 + 10),
                    avg_entry_price=0.50,
                    current_price=0.55,
                )
                await db.upsert_position(position)

            positions = await db.get_all_positions()
            assert len(positions) == 3
            token_ids = {p.token_id for p in positions}
            assert token_ids == {"token_0", "token_1", "token_2"}

    @pytest.mark.asyncio
    async def test_delete_position(self, tmp_path: Path) -> None:
        """delete_position should remove position by token_id."""
        db_path = tmp_path / "test.db"
        async with DatabaseManager(db_path) as db:
            position = Position(
                token_id="token_to_delete",
                side=PositionSide.LONG,
                quantity=100.0,
                avg_entry_price=0.50,
                current_price=0.55,
            )
            await db.upsert_position(position)

            # Verify exists
            assert await db.get_position("token_to_delete") is not None

            # Delete
            await db.delete_position("token_to_delete")

            # Verify deleted
            assert await db.get_position("token_to_delete") is None

    @pytest.mark.asyncio
    async def test_delete_position_nonexistent_does_not_raise(
        self, tmp_path: Path
    ) -> None:
        """delete_position should not raise for non-existent token."""
        db_path = tmp_path / "test.db"
        async with DatabaseManager(db_path) as db:
            # Should not raise
            await db.delete_position("nonexistent_token")


class TestOrderOperations:
    """Tests for order lifecycle operations."""

    @pytest.mark.asyncio
    async def test_insert_order(self, tmp_path: Path) -> None:
        """Should insert an order record."""
        db_path = tmp_path / "test.db"
        async with DatabaseManager(db_path) as db:
            order = Order(
                client_order_id="client_123",
                token_id="token_abc",
                side=Side.BUY,
                quantity=100.0,
                order_type=OrderType.LIMIT,
                limit_price=0.50,
                time_in_force=TimeInForce.GTC,
                reason="Limit buy order",
            )

            await db.insert_order(order, status=OrderStatus.PENDING)

            stored = await db.get_order("client_123")
            assert stored is not None
            assert stored["client_order_id"] == "client_123"
            assert stored["token_id"] == "token_abc"
            assert stored["side"] == "BUY"
            assert stored["status"] == "PENDING"

    @pytest.mark.asyncio
    async def test_update_order_status(self, tmp_path: Path) -> None:
        """Should update order status and exchange_order_id."""
        db_path = tmp_path / "test.db"
        async with DatabaseManager(db_path) as db:
            order = Order(
                client_order_id="client_456",
                token_id="token_xyz",
                side=Side.SELL,
                quantity=50.0,
                reason="Test order",
            )
            await db.insert_order(order, status=OrderStatus.PENDING)

            # Update status to FILLED with exchange order ID
            await db.update_order_status(
                client_order_id="client_456",
                status=OrderStatus.FILLED,
                exchange_order_id="exchange_789",
            )

            stored = await db.get_order("client_456")
            assert stored is not None
            assert stored["status"] == "FILLED"
            assert stored["exchange_order_id"] == "exchange_789"

    @pytest.mark.asyncio
    async def test_get_order_returns_none_if_not_exists(self, tmp_path: Path) -> None:
        """get_order should return None for non-existent order."""
        db_path = tmp_path / "test.db"
        async with DatabaseManager(db_path) as db:
            result = await db.get_order("nonexistent_order")
            assert result is None


class TestConcurrentAccess:
    """Tests for concurrent database access."""

    @pytest.mark.asyncio
    async def test_concurrent_inserts(self, tmp_path: Path) -> None:
        """Multiple concurrent inserts should not corrupt database."""
        db_path = tmp_path / "test.db"
        async with DatabaseManager(db_path) as db:
            async def insert_trade(i: int) -> None:
                order = Order(
                    token_id=f"token_{i}",
                    side=Side.BUY,
                    quantity=float(i + 1),  # Start at 1, quantity must be > 0
                    reason=f"Trade {i}",
                )
                result = ExecutionResult(
                    order_id=f"order_{i}",
                    status=OrderStatus.FILLED,
                    filled_price=0.50,
                )
                await db.insert_trade(order, result)

            # Run 10 concurrent inserts
            await asyncio.gather(*[insert_trade(i) for i in range(10)])

            # Verify all trades were inserted
            trades = await db.get_trades()
            assert len(trades) == 10
