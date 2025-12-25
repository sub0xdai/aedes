"""Status header widget showing connection status and wallet balance."""

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Label, Static


class StatusHeader(Static):
    """Status header showing connection status and wallet balance.

    Displays:
    - Connection status indicator (green/red dot)
    - Wallet balance (mocked for now)

    Attributes:
        is_connected: Whether the bot is connected to Polymarket.
        balance: Current wallet balance in USDC.
    """

    is_connected: reactive[bool] = reactive(False)
    balance: reactive[float] = reactive(0.0)

    def compose(self) -> ComposeResult:
        """Compose the header layout."""
        yield Label("", id="connection-status")
        yield Label("", id="balance-label", classes="balance-label")

    def on_mount(self) -> None:
        """Update display on mount."""
        self._update_connection_status()
        self._update_balance()

    def watch_is_connected(self, is_connected: bool) -> None:
        """React to connection status changes."""
        self._update_connection_status()

    def watch_balance(self, balance: float) -> None:
        """React to balance changes."""
        self._update_balance()

    def _update_connection_status(self) -> None:
        """Update the connection status display."""
        label = self.query_one("#connection-status", Label)
        if self.is_connected:
            label.update("● Connected")
            label.set_classes("status-connected")
        else:
            label.update("○ Disconnected")
            label.set_classes("status-disconnected")

    def _update_balance(self) -> None:
        """Update the balance display."""
        label = self.query_one("#balance-label", Label)
        label.update(f"Balance: ${self.balance:,.2f} USDC")
