"""Loguru sink that forwards logs to Textual RichLog widget."""

from typing import Any

from loguru import logger


class TuiLogSink:
    """Loguru sink that forwards logs to Textual RichLog widget.

    This sink bridges loguru logging to Textual's RichLog widget,
    enabling live log display in the TUI.

    Thread Safety:
        Loguru sinks may run in arbitrary threads. This sink uses
        Textual's call_from_thread() to safely post messages to the
        main UI thread.

    Usage:
        sink = TuiLogSink(app)
        sink.install()  # Start forwarding logs
        # ... run app ...
        sink.uninstall()  # Stop forwarding
    """

    def __init__(self, app: Any) -> None:
        """Initialize the log sink.

        Args:
            app: The Textual App instance to forward logs to.
        """
        self._app = app
        self._handler_id: int | None = None

    def install(self) -> None:
        """Install this sink into loguru.

        Adds a new handler that forwards log messages to the TUI.
        The handler uses Rich-compatible formatting.
        """
        # Remove default stderr handler to avoid duplicate logs
        logger.remove()

        self._handler_id = logger.add(
            self._write,
            format="{time:HH:mm:ss} | {level: <7} | {message}",
            level="DEBUG",
            colorize=False,
        )

    def uninstall(self) -> None:
        """Remove this sink from loguru."""
        if self._handler_id is not None:
            logger.remove(self._handler_id)
            self._handler_id = None

    def _write(self, message: str) -> None:
        """Write a log message to the RichLog widget.

        This runs in the loguru thread. Uses call_from_thread
        to safely post to the Textual app.

        Args:
            message: The formatted log message from loguru.
        """
        # Strip trailing newline from loguru
        text = message.rstrip("\n")

        try:
            # Thread-safe posting to Textual
            self._app.call_from_thread(self._post_log, text)
        except Exception:
            # Silently ignore errors - logging should never crash the app
            pass

    def _post_log(self, text: str) -> None:
        """Post log to RichLog widget (runs in Textual thread).

        Args:
            text: The log message text.
        """
        try:
            from textual.widgets import RichLog

            log_widget = self._app.query_one("#live-log", RichLog)
            log_widget.write(text)
        except Exception:
            # Widget may not exist yet or query may fail
            pass
