"""Global header bar for Aedes TUI.

Full-width header containing:
- Left: App title + status + mode
- Right: Wallet address + balance
"""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Label, Static


class GlobalHeader(Static):
    """Global header bar with title, status, mode, and wallet info.

    Layout:
    ┌──────────────────────────────────────────────────────────────────────┐
    │ AEDES  ● Connected  DRY RUN          │  Wallet: 0x1234...5678 $0.00  │
    └──────────────────────────────────────────────────────────────────────┘
    """

    DEFAULT_CSS = """
    GlobalHeader {
        dock: top;
        height: 3;
        background: #181825;
        border-bottom: solid #313244;
    }

    GlobalHeader > Horizontal {
        width: 100%;
        height: 100%;
    }

    GlobalHeader .header-left {
        width: 1fr;
        height: 100%;
        padding: 1 2;
    }

    GlobalHeader .header-left > Horizontal {
        height: 1;
        width: auto;
    }

    GlobalHeader .header-right {
        width: auto;
        height: 100%;
        padding: 1 2;
        content-align: right middle;
    }

    GlobalHeader #app-title {
        text-style: bold;
        color: #f9e2af;
        margin-right: 2;
    }

    GlobalHeader #status-indicator {
        margin-right: 1;
    }

    GlobalHeader #status-text {
        margin-right: 2;
    }

    GlobalHeader #mode-badge {
        text-style: bold;
        padding: 0 1;
    }

    GlobalHeader .status-connected {
        color: #a6e3a1;
    }

    GlobalHeader .status-disconnected {
        color: #f38ba8;
    }

    GlobalHeader .mode-dry-run {
        color: #1e1e2e;
        background: #f9e2af;
    }

    GlobalHeader .mode-live {
        color: #1e1e2e;
        background: #a6e3a1;
    }

    GlobalHeader .separator {
        color: #313244;
        margin: 0 1;
    }

    GlobalHeader #wallet-label {
        color: #6c7086;
        margin-right: 1;
    }

    GlobalHeader #wallet-address {
        color: #a6e3a1;
        margin-right: 1;
    }

    GlobalHeader #wallet-balance {
        color: #f9e2af;
    }

    GlobalHeader .no-wallet {
        color: #6c7086;
    }
    """

    # Reactive properties
    is_connected: reactive[bool] = reactive(False)
    wallet_address: reactive[str] = reactive("")
    wallet_balance: reactive[float] = reactive(0.0)
    is_dry_run: reactive[bool] = reactive(True)

    def compose(self) -> ComposeResult:
        with Horizontal():
            # Left side: App title + status + mode
            with Static(classes="header-left"):
                with Horizontal():
                    yield Label("AEDES", id="app-title")
                    yield Label("○", id="status-indicator", classes="status-disconnected")
                    yield Label("Disconnected", id="status-text", classes="status-disconnected")
                    yield Label("DRY RUN", id="mode-badge", classes="mode-dry-run")

            # Right side: Wallet info
            with Static(classes="header-right"):
                with Horizontal():
                    yield Label("|", classes="separator")
                    yield Label("Wallet:", id="wallet-label")
                    yield Label("Not connected", id="wallet-address", classes="no-wallet")
                    yield Label("", id="wallet-balance")

    def watch_is_connected(self, connected: bool) -> None:
        """Update connection indicator."""
        indicator = self.query_one("#status-indicator", Label)
        text = self.query_one("#status-text", Label)
        if connected:
            indicator.update("●")
            indicator.set_classes("status-connected")
            text.update("Connected")
            text.set_classes("status-connected")
        else:
            indicator.update("○")
            indicator.set_classes("status-disconnected")
            text.update("Disconnected")
            text.set_classes("status-disconnected")

    def watch_wallet_address(self, address: str) -> None:
        """Update wallet display when address changes."""
        self._update_wallet_display()

    def watch_wallet_balance(self, balance: float) -> None:
        """Update wallet display when balance changes."""
        self._update_wallet_display()

    def watch_is_dry_run(self, dry_run: bool) -> None:
        """Update run mode indicator."""
        mode_label = self.query_one("#mode-badge", Label)
        if dry_run:
            mode_label.update("DRY RUN")
            mode_label.set_classes("mode-dry-run")
        else:
            mode_label.update("LIVE")
            mode_label.set_classes("mode-live")

    def _update_wallet_display(self) -> None:
        """Update the wallet info display."""
        addr_label = self.query_one("#wallet-address", Label)
        balance_label = self.query_one("#wallet-balance", Label)

        if not self.wallet_address:
            addr_label.update("Not connected")
            addr_label.set_classes("no-wallet")
            balance_label.update("")
            return

        # Truncate address: 0x1234...5678
        short_addr = f"{self.wallet_address[:6]}...{self.wallet_address[-4:]}"
        addr_label.update(short_addr)
        addr_label.set_classes("")
        balance_label.update(f"${self.wallet_balance:,.2f}")

    def set_wallet(self, address: str, balance: float = 0.0) -> None:
        """Set wallet info."""
        self.wallet_address = address
        self.wallet_balance = balance

    def clear_wallet(self) -> None:
        """Clear wallet info (locked state)."""
        self.wallet_address = ""
        self.wallet_balance = 0.0

    def set_connected(self, connected: bool) -> None:
        """Set connection status."""
        self.is_connected = connected

    def set_dry_run(self, dry_run: bool) -> None:
        """Set run mode."""
        self.is_dry_run = dry_run

    def set_balance(self, balance: float) -> None:
        """Update just the balance."""
        self.wallet_balance = balance
