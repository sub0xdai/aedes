"""Positions panel widget for displaying open positions."""

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.widgets import DataTable, Static

if TYPE_CHECKING:
    from src.models import Position


class PositionsPanel(Static):
    """Table displaying open positions with P&L.

    Shows all open positions with:
    - Token (truncated)
    - Side (LONG/SHORT)
    - Quantity
    - Entry Price
    - Current Price
    - Unrealized P&L (color-coded)

    Attributes:
        _positions: Internal position storage keyed by token_id.
    """

    DEFAULT_CSS = """
    PositionsPanel {
        height: 100%;
    }

    PositionsPanel DataTable {
        height: 100%;
    }

    .pnl-positive {
        color: $success;
    }

    .pnl-negative {
        color: $error;
    }
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the positions panel.

        Args:
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._positions: dict[str, "Position"] = {}

    def compose(self) -> ComposeResult:
        """Compose the table."""
        table: DataTable[str] = DataTable(id="positions-table")
        table.add_columns("Token", "Side", "Qty", "Entry", "Current", "PnL")
        yield table

    def add_position(self, position: "Position") -> None:
        """Add or update a position in the table.

        Args:
            position: The position to add/update.
        """
        self._positions[position.token_id] = position
        self._refresh_table()

    def update_position(self, position: "Position") -> None:
        """Update an existing position.

        Args:
            position: The updated position.
        """
        self._positions[position.token_id] = position
        self._refresh_table()

    def remove_position(self, token_id: str) -> None:
        """Remove a position from the table.

        Args:
            token_id: Token ID of the position to remove.
        """
        if token_id in self._positions:
            del self._positions[token_id]
            self._refresh_table()

    def _refresh_table(self) -> None:
        """Refresh the table display."""
        table = self.query_one("#positions-table", DataTable)
        table.clear()

        for position in self._positions.values():
            # Truncate token ID
            token_short = position.token_id[:8] + "..."

            # Format side
            side = position.side.value

            # Format quantity
            qty = f"{position.quantity:.2f}"

            # Format prices
            entry = f"{position.avg_entry_price:.3f}"
            current = f"{position.current_price:.3f}"

            # Format PnL with color indicator
            pnl = position.unrealized_pnl
            pnl_str = f"${pnl:+.2f}"

            table.add_row(token_short, side, qty, entry, current, pnl_str)

    def clear(self) -> None:
        """Clear all positions from the table."""
        self._positions.clear()
        table = self.query_one("#positions-table", DataTable)
        table.clear()
