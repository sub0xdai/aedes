"""SQLite database manager for persistent storage."""

from pathlib import Path
from time import time
from typing import Any

import aiosqlite
from loguru import logger

from src.models import (
    ExecutionResult,
    Order,
    OrderStatus,
    Position,
    PositionSide,
)
from src.persistence.schema import SCHEMA_STATEMENTS


class DatabaseManager:
    """Async SQLite database manager for trades, positions, and orders.

    Provides async context manager interface and CRUD operations
    for all persistent data.

    Example:
        async with DatabaseManager(Path("data/trading.db")) as db:
            await db.insert_trade(order, result)
            positions = await db.get_all_positions()
    """

    def __init__(self, db_path: Path) -> None:
        """Initialize the database manager.

        Args:
            db_path: Path to the SQLite database file.
        """
        self._db_path = db_path
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open database connection and create tables if needed."""
        # Ensure parent directory exists
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._connection = await aiosqlite.connect(self._db_path)
        self._connection.row_factory = aiosqlite.Row

        # Create schema
        for statement in SCHEMA_STATEMENTS:
            await self._connection.execute(statement)
        await self._connection.commit()

        logger.debug("Connected to database: {}", self._db_path)

    async def disconnect(self) -> None:
        """Close database connection."""
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
            logger.debug("Disconnected from database: {}", self._db_path)

    async def __aenter__(self) -> "DatabaseManager":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.disconnect()

    async def _table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        if self._connection is None:
            return False

        cursor = await self._connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        row = await cursor.fetchone()
        return row is not None

    # =========================================================================
    # Trade Operations
    # =========================================================================

    async def insert_trade(self, order: Order, result: ExecutionResult) -> None:
        """Insert a trade record.

        Args:
            order: The order that was executed.
            result: The execution result.
        """
        if self._connection is None:
            raise RuntimeError("Database not connected")

        await self._connection.execute(
            """
            INSERT INTO trades (
                order_id, client_order_id, token_id, side,
                quantity, price, fees, executed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.order_id,
                order.client_order_id,
                order.token_id,
                order.side.value,
                result.filled_size if result.filled_size > 0 else order.quantity,
                result.filled_price,
                result.fees_paid,
                result.execution_timestamp,
            ),
        )
        await self._connection.commit()

    async def get_trades(
        self,
        token_id: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get trade records.

        Args:
            token_id: Filter by token ID (optional).
            limit: Maximum number of records to return (optional).

        Returns:
            List of trade records as dictionaries.
        """
        if self._connection is None:
            raise RuntimeError("Database not connected")

        query = "SELECT * FROM trades"
        params: list[Any] = []

        if token_id is not None:
            query += " WHERE token_id = ?"
            params.append(token_id)

        query += " ORDER BY executed_at DESC"

        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        cursor = await self._connection.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # =========================================================================
    # Position Operations
    # =========================================================================

    async def upsert_position(self, position: Position) -> None:
        """Insert or update a position.

        Args:
            position: The position to upsert.
        """
        if self._connection is None:
            raise RuntimeError("Database not connected")

        await self._connection.execute(
            """
            INSERT INTO positions (
                token_id, side, quantity, avg_entry_price,
                current_price, opened_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(token_id) DO UPDATE SET
                side = excluded.side,
                quantity = excluded.quantity,
                avg_entry_price = excluded.avg_entry_price,
                current_price = excluded.current_price,
                updated_at = excluded.updated_at
            """,
            (
                position.token_id,
                position.side.value,
                position.quantity,
                position.avg_entry_price,
                position.current_price,
                position.opened_at,
                time(),
            ),
        )
        await self._connection.commit()

    async def get_position(self, token_id: str) -> Position | None:
        """Get a position by token ID.

        Args:
            token_id: The token ID to look up.

        Returns:
            The Position if found, None otherwise.
        """
        if self._connection is None:
            raise RuntimeError("Database not connected")

        cursor = await self._connection.execute(
            "SELECT * FROM positions WHERE token_id = ?",
            (token_id,),
        )
        row = await cursor.fetchone()

        if row is None:
            return None

        return Position(
            token_id=row["token_id"],
            side=PositionSide(row["side"]),
            quantity=row["quantity"],
            avg_entry_price=row["avg_entry_price"],
            current_price=row["current_price"],
            opened_at=row["opened_at"],
        )

    async def get_all_positions(self) -> list[Position]:
        """Get all positions.

        Returns:
            List of all Position objects.
        """
        if self._connection is None:
            raise RuntimeError("Database not connected")

        cursor = await self._connection.execute("SELECT * FROM positions")
        rows = await cursor.fetchall()

        return [
            Position(
                token_id=row["token_id"],
                side=PositionSide(row["side"]),
                quantity=row["quantity"],
                avg_entry_price=row["avg_entry_price"],
                current_price=row["current_price"],
                opened_at=row["opened_at"],
            )
            for row in rows
        ]

    async def delete_position(self, token_id: str) -> None:
        """Delete a position by token ID.

        Args:
            token_id: The token ID to delete.
        """
        if self._connection is None:
            raise RuntimeError("Database not connected")

        await self._connection.execute(
            "DELETE FROM positions WHERE token_id = ?",
            (token_id,),
        )
        await self._connection.commit()

    # =========================================================================
    # Order Operations
    # =========================================================================

    async def insert_order(self, order: Order, status: OrderStatus) -> None:
        """Insert an order record.

        Args:
            order: The order to insert.
            status: Initial order status.
        """
        if self._connection is None:
            raise RuntimeError("Database not connected")

        await self._connection.execute(
            """
            INSERT INTO orders (
                client_order_id, token_id, side, quantity,
                order_type, limit_price, time_in_force,
                status, reason, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order.client_order_id,
                order.token_id,
                order.side.value,
                order.quantity,
                order.order_type.value,
                order.limit_price,
                order.time_in_force.value,
                status.value,
                order.reason,
                order.created_at,
                time(),
            ),
        )
        await self._connection.commit()

    async def update_order_status(
        self,
        client_order_id: str,
        status: OrderStatus,
        exchange_order_id: str | None = None,
    ) -> None:
        """Update order status and optionally exchange order ID.

        Args:
            client_order_id: The client order ID.
            status: New order status.
            exchange_order_id: Exchange-assigned order ID (optional).
        """
        if self._connection is None:
            raise RuntimeError("Database not connected")

        if exchange_order_id is not None:
            await self._connection.execute(
                """
                UPDATE orders SET status = ?, exchange_order_id = ?, updated_at = ?
                WHERE client_order_id = ?
                """,
                (status.value, exchange_order_id, time(), client_order_id),
            )
        else:
            await self._connection.execute(
                """
                UPDATE orders SET status = ?, updated_at = ?
                WHERE client_order_id = ?
                """,
                (status.value, time(), client_order_id),
            )
        await self._connection.commit()

    async def get_order(self, client_order_id: str) -> dict[str, Any] | None:
        """Get an order by client order ID.

        Args:
            client_order_id: The client order ID.

        Returns:
            The order as a dictionary if found, None otherwise.
        """
        if self._connection is None:
            raise RuntimeError("Database not connected")

        cursor = await self._connection.execute(
            "SELECT * FROM orders WHERE client_order_id = ?",
            (client_order_id,),
        )
        row = await cursor.fetchone()

        if row is None:
            return None

        return dict(row)
