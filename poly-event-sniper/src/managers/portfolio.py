"""Portfolio management with position tracking and risk controls."""

from time import time
from typing import Protocol

from loguru import logger

from src.models import (
    ExecutionResult,
    Order,
    Position,
    PositionSide,
    Side,
)
from src.persistence import DatabaseManager


class ExecutorProtocol(Protocol):
    """Protocol for executor balance fetching."""

    async def get_balance(self) -> float:
        """Get the current cash balance."""
        ...


class PortfolioManager:
    """Portfolio state management and risk controls.

    Tracks positions, cash balance, and validates orders against
    portfolio constraints before execution.

    Example:
        pm = PortfolioManager(database=db)
        await pm.load_state(executor)

        is_valid, reason = pm.check_order(order)
        if is_valid:
            result = await executor.execute(order)
            await pm.on_fill(order, result)
    """

    def __init__(
        self,
        database: DatabaseManager,
        max_position_size: float = 500.0,
        max_positions: int = 10,
    ) -> None:
        """Initialize the portfolio manager.

        Args:
            database: Database manager for persistence.
            max_position_size: Maximum position size in USDC.
            max_positions: Maximum number of concurrent positions.
        """
        self._database = database
        self._max_position_size = max_position_size
        self._max_positions = max_positions

        self._cash_balance: float = 0.0
        self._positions: dict[str, Position] = {}

    @property
    def cash_balance(self) -> float:
        """Current cash balance in USDC."""
        return self._cash_balance

    @property
    def positions(self) -> dict[str, Position]:
        """Current positions by token_id."""
        return self._positions

    @property
    def total_unrealized_pnl(self) -> float:
        """Total unrealized P&L across all positions."""
        return sum(p.unrealized_pnl for p in self._positions.values())

    @property
    def total_market_value(self) -> float:
        """Total market value of all positions."""
        return sum(p.market_value for p in self._positions.values())

    async def load_state(self, executor: ExecutorProtocol) -> None:
        """Load positions from database and fetch cash from exchange.

        Args:
            executor: Executor for fetching cash balance.
        """
        # Fetch cash balance from exchange
        self._cash_balance = await executor.get_balance()
        logger.info("Loaded cash balance: {} USDC", self._cash_balance)

        # Load positions from database
        positions = await self._database.get_all_positions()
        self._positions = {p.token_id: p for p in positions}
        logger.info("Loaded {} positions from database", len(self._positions))

    def check_order(self, order: Order) -> tuple[bool, str]:
        """Validate order against portfolio constraints.

        Args:
            order: The order to validate.

        Returns:
            Tuple of (is_valid, reason). If invalid, reason explains why.
        """
        if order.side == Side.BUY:
            # Check cash sufficiency
            # Use limit_price if set, otherwise assume worst case (1.0)
            price = order.limit_price if order.limit_price is not None else 1.0
            cost = order.quantity * price

            if cost > self._cash_balance:
                return False, f"Insufficient cash: {cost:.2f} > {self._cash_balance:.2f}"

            # Check max positions for new positions
            if order.token_id not in self._positions:
                if len(self._positions) >= self._max_positions:
                    return False, f"Max positions reached: {self._max_positions}"

        elif order.side == Side.SELL:
            # Check position sufficiency
            pos = self._positions.get(order.token_id)
            if pos is None or pos.quantity < order.quantity:
                available = pos.quantity if pos else 0.0
                return False, f"Insufficient position for sell: {order.quantity} > {available}"

        return True, ""

    async def on_fill(self, order: Order, result: ExecutionResult) -> None:
        """Update positions after a fill.

        Args:
            order: The order that was filled.
            result: The execution result.
        """
        token_id = order.token_id
        filled_price = result.filled_price
        filled_size = result.filled_size if result.filled_size > 0 else order.quantity

        if order.side == Side.BUY:
            await self._handle_buy_fill(token_id, filled_size, filled_price)
        else:  # SELL
            await self._handle_sell_fill(token_id, filled_size, filled_price)

        # Update cash balance (approximate)
        if order.side == Side.BUY:
            self._cash_balance -= filled_size * filled_price + result.fees_paid
        else:
            self._cash_balance += filled_size * filled_price - result.fees_paid

    async def _handle_buy_fill(
        self, token_id: str, quantity: float, price: float
    ) -> None:
        """Handle BUY fill - create or add to position."""
        if token_id in self._positions:
            # Add to existing position
            old_pos = self._positions[token_id]
            new_quantity = old_pos.quantity + quantity

            # Calculate new average entry price
            total_cost = (old_pos.quantity * old_pos.avg_entry_price) + (quantity * price)
            new_avg_price = total_cost / new_quantity

            new_pos = Position(
                token_id=token_id,
                side=PositionSide.LONG,
                quantity=new_quantity,
                avg_entry_price=new_avg_price,
                current_price=price,  # Use fill price as current
                opened_at=old_pos.opened_at,
            )
        else:
            # Create new position
            new_pos = Position(
                token_id=token_id,
                side=PositionSide.LONG,
                quantity=quantity,
                avg_entry_price=price,
                current_price=price,
                opened_at=time(),
            )

        self._positions[token_id] = new_pos
        await self._database.upsert_position(new_pos)
        logger.debug("Position updated: {} {} @ {}", token_id, new_pos.quantity, new_pos.avg_entry_price)

    async def _handle_sell_fill(
        self, token_id: str, quantity: float, price: float
    ) -> None:
        """Handle SELL fill - reduce or close position."""
        if token_id not in self._positions:
            logger.warning("Sell fill for unknown position: {}", token_id)
            return

        old_pos = self._positions[token_id]
        new_quantity = old_pos.quantity - quantity

        if new_quantity <= 0:
            # Position closed
            del self._positions[token_id]
            await self._database.delete_position(token_id)
            logger.debug("Position closed: {}", token_id)
        else:
            # Position reduced
            new_pos = Position(
                token_id=token_id,
                side=old_pos.side,
                quantity=new_quantity,
                avg_entry_price=old_pos.avg_entry_price,  # Unchanged on sells
                current_price=price,
                opened_at=old_pos.opened_at,
            )
            self._positions[token_id] = new_pos
            await self._database.upsert_position(new_pos)
            logger.debug("Position reduced: {} to {}", token_id, new_quantity)

    async def on_price_update(self, token_id: str, price: float) -> None:
        """Update mark-to-market for a position.

        Args:
            token_id: The token to update.
            price: The new market price.
        """
        if token_id not in self._positions:
            return

        old_pos = self._positions[token_id]
        new_pos = Position(
            token_id=old_pos.token_id,
            side=old_pos.side,
            quantity=old_pos.quantity,
            avg_entry_price=old_pos.avg_entry_price,
            current_price=price,
            opened_at=old_pos.opened_at,
        )
        self._positions[token_id] = new_pos
