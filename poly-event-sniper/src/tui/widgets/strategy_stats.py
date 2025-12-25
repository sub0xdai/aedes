"""Strategy statistics panel widget."""

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Label, Static


class StrategyStatsPanel(Static):
    """Panel displaying active strategy statistics.

    Shows:
    - Number of active ThresholdRules
    - Number of active KeywordRules
    - Events processed
    - Signals generated
    - Trades executed

    Attributes:
        threshold_rules: Count of active threshold rules.
        keyword_rules: Count of active keyword rules.
        events_processed: Total events processed.
        signals_generated: Total signals generated.
        trades_executed: Total trades executed.
    """

    threshold_rules: reactive[int] = reactive(0)
    keyword_rules: reactive[int] = reactive(0)
    events_processed: reactive[int] = reactive(0)
    signals_generated: reactive[int] = reactive(0)
    trades_executed: reactive[int] = reactive(0)

    def compose(self) -> ComposeResult:
        """Compose the stats panel."""
        yield Label("Active Strategies", classes="stats-title")
        yield Label("", id="threshold-count")
        yield Label("", id="keyword-count")
        yield Label("", classes="stats-title")
        yield Label("Metrics", classes="stats-title")
        yield Label("", id="events-count")
        yield Label("", id="signals-count")
        yield Label("", id="trades-count")

    def on_mount(self) -> None:
        """Update display on mount."""
        self._update_all()

    def watch_threshold_rules(self, count: int) -> None:
        """React to threshold rule count changes."""
        self._update_threshold_count()

    def watch_keyword_rules(self, count: int) -> None:
        """React to keyword rule count changes."""
        self._update_keyword_count()

    def watch_events_processed(self, count: int) -> None:
        """React to events processed changes."""
        self._update_events_count()

    def watch_signals_generated(self, count: int) -> None:
        """React to signals generated changes."""
        self._update_signals_count()

    def watch_trades_executed(self, count: int) -> None:
        """React to trades executed changes."""
        self._update_trades_count()

    def _update_all(self) -> None:
        """Update all displays."""
        self._update_threshold_count()
        self._update_keyword_count()
        self._update_events_count()
        self._update_signals_count()
        self._update_trades_count()

    def _update_threshold_count(self) -> None:
        """Update threshold rules display."""
        label = self.query_one("#threshold-count", Label)
        label.update(f"  ThresholdRules: {self.threshold_rules}")

    def _update_keyword_count(self) -> None:
        """Update keyword rules display."""
        label = self.query_one("#keyword-count", Label)
        label.update(f"  KeywordRules: {self.keyword_rules}")

    def _update_events_count(self) -> None:
        """Update events processed display."""
        label = self.query_one("#events-count", Label)
        label.update(f"  Events: {self.events_processed:,}")

    def _update_signals_count(self) -> None:
        """Update signals generated display."""
        label = self.query_one("#signals-count", Label)
        label.update(f"  Signals: {self.signals_generated:,}")

    def _update_trades_count(self) -> None:
        """Update trades executed display."""
        label = self.query_one("#trades-count", Label)
        label.update(f"  Trades: {self.trades_executed:,}")

    def update_metrics(self, metrics: dict[str, int]) -> None:
        """Update all metrics from orchestrator.

        Args:
            metrics: Dictionary with events_processed, signals_generated,
                     trades_executed, errors_encountered.
        """
        self.events_processed = metrics.get("events_processed", 0)
        self.signals_generated = metrics.get("signals_generated", 0)
        self.trades_executed = metrics.get("trades_executed", 0)
