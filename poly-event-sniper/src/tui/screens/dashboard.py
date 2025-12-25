"""Dashboard screen - main view with logs and stats."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from src.tui.widgets import (
    LiveLogPanel,
    RecentTradesTable,
    StatusHeader,
    StrategyStatsPanel,
)


class DashboardScreen(Screen[None]):
    """Main dashboard screen showing live logs and trading stats.

    Layout:
    ```
    ┌─────────────────────────────────────────────────────────┐
    │ Header: [SNIPER] poly-event-sniper                      │
    ├────────────────────────────────┬────────────────────────┤
    │                                │ StatusHeader           │
    │                                ├────────────────────────┤
    │   LiveLogPanel (60%)           │ StrategyStatsPanel     │
    │   RichLog with live logs       ├────────────────────────┤
    │                                │ RecentTradesTable      │
    │                                │                        │
    ├────────────────────────────────┴────────────────────────┤
    │ Footer: Keybindings                                     │
    └─────────────────────────────────────────────────────────┘
    ```
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("c", "clear_logs", "Clear Logs"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the dashboard layout."""
        yield Header()

        with Horizontal(id="main-container"):
            # Left panel - logs (60%)
            with Container(id="left-panel"):
                yield LiveLogPanel(id="log-panel")

            # Right panel - stats and trades (40%)
            with Vertical(id="right-panel"):
                yield StatusHeader(id="status-header")
                yield StrategyStatsPanel(id="strategy-stats")
                yield RecentTradesTable(id="trades-panel", max_rows=10)

        yield Footer()

    def action_clear_logs(self) -> None:
        """Clear the log panel."""
        log_panel = self.query_one("#log-panel", LiveLogPanel)
        log_panel.clear()

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit()
