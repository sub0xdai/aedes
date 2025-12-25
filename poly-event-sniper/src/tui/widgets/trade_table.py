"""Recent trades table widget."""

from datetime import datetime
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.widgets import DataTable, Static

if TYPE_CHECKING:
    from src.models import ExecutionResult, TradeSignal


class RecentTradesTable(Static):
    """Table displaying recent trade executions.

    Shows the last N trades with:
    - Time
    - Token (truncated)
    - Side (BUY/SELL)
    - Size (USDC)
    - Status (FILLED/FAILED/etc)

    Attributes:
        max_rows: Maximum number of trades to display.
    """

    DEFAULT_CSS = """
    RecentTradesTable {
        height: 100%;
    }
    """

    def __init__(
        self,
        max_rows: int = 10,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the trades table.

        Args:
            max_rows: Maximum number of trades to display.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._max_rows = max_rows
        self._trades: list[tuple["TradeSignal", "ExecutionResult"]] = []

    def compose(self) -> ComposeResult:
        """Compose the table."""
        table: DataTable[str] = DataTable(id="trades-table")
        table.add_columns("Time", "Token", "Side", "Size", "Status")
        yield table

    def add_trade(self, signal: "TradeSignal", result: "ExecutionResult") -> None:
        """Add a trade to the table.

        Args:
            signal: The trade signal.
            result: The execution result.
        """
        self._trades.append((signal, result))

        # Keep only max_rows trades
        if len(self._trades) > self._max_rows:
            self._trades = self._trades[-self._max_rows :]

        self._refresh_table()

    def _refresh_table(self) -> None:
        """Refresh the table display."""
        table = self.query_one("#trades-table", DataTable)
        table.clear()

        for signal, result in reversed(self._trades):
            # Format time
            time_str = datetime.fromtimestamp(signal.timestamp).strftime("%H:%M:%S")

            # Truncate token ID
            token_short = signal.token_id[:8] + "..."

            # Format side with color class
            side = signal.side.value

            # Format size
            size = f"${signal.size_usdc:.2f}"

            # Format status
            status = result.status.value

            table.add_row(time_str, token_short, side, size, status)

    def clear(self) -> None:
        """Clear all trades from the table."""
        self._trades.clear()
        table = self.query_one("#trades-table", DataTable)
        table.clear()
