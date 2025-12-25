"""Live log panel widget wrapping RichLog."""

from textual.app import ComposeResult
from textual.widgets import RichLog, Static


class LiveLogPanel(Static):
    """Live log panel displaying system logs.

    Wraps a RichLog widget with auto-scroll enabled.
    Logs are written via the TuiLogSink.
    """

    def compose(self) -> ComposeResult:
        """Compose the log panel."""
        yield RichLog(
            id="live-log",
            auto_scroll=True,
            wrap=True,
            markup=True,
            highlight=True,
        )

    def write(self, text: str) -> None:
        """Write a line to the log.

        Args:
            text: The text to write.
        """
        log = self.query_one("#live-log", RichLog)
        log.write(text)

    def clear(self) -> None:
        """Clear all log entries."""
        log = self.query_one("#live-log", RichLog)
        log.clear()
