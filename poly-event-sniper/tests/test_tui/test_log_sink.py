"""Tests for the TUI log sink (loguru -> RichLog bridge)."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from loguru import logger

from src.tui.log_sink import TuiLogSink


class TestTuiLogSink:
    """Tests for TuiLogSink."""

    def test_install_adds_handler(self) -> None:
        """Test that install() adds a loguru handler."""
        mock_app = MagicMock()
        sink = TuiLogSink(mock_app)

        # Initially no handler ID
        assert sink._handler_id is None

        sink.install()

        # Now has a handler ID
        assert sink._handler_id is not None

        # Cleanup
        sink.uninstall()

    def test_uninstall_removes_handler(self) -> None:
        """Test that uninstall() removes the loguru handler."""
        mock_app = MagicMock()
        sink = TuiLogSink(mock_app)

        sink.install()
        handler_id = sink._handler_id
        assert handler_id is not None

        sink.uninstall()

        # Handler ID is cleared
        assert sink._handler_id is None

    def test_write_posts_to_app(self) -> None:
        """Test that log messages are posted to the app via call_from_thread."""
        mock_app = MagicMock()
        sink = TuiLogSink(mock_app)

        # Simulate a log write
        sink._write("Test log message\n")

        # Verify call_from_thread was called
        mock_app.call_from_thread.assert_called_once()

        # Get the arguments
        args = mock_app.call_from_thread.call_args
        callback_fn = args[0][0]  # First positional arg is the callback
        text = args[0][1]  # Second positional arg is the text

        # Verify text was stripped of newline
        assert text == "Test log message"

    def test_write_strips_trailing_newline(self) -> None:
        """Test that trailing newlines are stripped from log messages."""
        mock_app = MagicMock()
        sink = TuiLogSink(mock_app)

        sink._write("Message with newline\n\n")

        args = mock_app.call_from_thread.call_args
        text = args[0][1]
        assert text == "Message with newline"

    def test_log_message_flows_through_loguru(self) -> None:
        """Test that loguru messages reach the sink."""
        mock_app = MagicMock()
        sink = TuiLogSink(mock_app)

        sink.install()

        try:
            # Log a message
            logger.info("Test message from loguru")

            # Verify the app received it
            assert mock_app.call_from_thread.called
        finally:
            sink.uninstall()

    def test_multiple_log_messages(self) -> None:
        """Test that multiple log messages all flow through."""
        mock_app = MagicMock()
        sink = TuiLogSink(mock_app)

        sink.install()

        try:
            logger.info("Message 1")
            logger.warning("Message 2")
            logger.error("Message 3")

            # Should have 3 calls
            assert mock_app.call_from_thread.call_count == 3
        finally:
            sink.uninstall()

    def test_sink_does_not_crash_on_failure(self) -> None:
        """Test that the sink handles errors gracefully."""
        mock_app = MagicMock()
        mock_app.call_from_thread.side_effect = RuntimeError("App error")
        sink = TuiLogSink(mock_app)

        # Should not raise even if app fails
        try:
            sink._write("Test message\n")
        except RuntimeError:
            pytest.fail("Sink should not propagate exceptions")
