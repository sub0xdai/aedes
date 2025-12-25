"""Trade logging to JSONL files."""

import json
from datetime import date
from pathlib import Path
from time import time

import aiofiles
from loguru import logger

from src.models import ExecutionResult, TradeSignal


class TradeLogger:
    """Append-only JSONL logger for trade signals and execution results.

    Provides non-blocking persistence of trade data for audit and analysis.
    Uses daily file rotation for manageable file sizes.

    Example output (trades_2025-12-23.jsonl):
        {"logged_at": 1703347200.0, "signal": {...}, "result": {...}}
        {"logged_at": 1703347260.0, "signal": {...}, "result": {...}}
    """

    def __init__(self, data_dir: Path = Path("data")) -> None:
        """Initialize the trade logger.

        Args:
            data_dir: Directory for storing trade logs. Created if not exists.
        """
        self._data_dir = data_dir
        self._ensure_data_dir()

    def _ensure_data_dir(self) -> None:
        """Create data directory if it doesn't exist."""
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error("Failed to create data directory {}: {}", self._data_dir, e)

    def _get_daily_filepath(self) -> Path:
        """Get the filepath for today's trade log."""
        return self._data_dir / f"trades_{date.today().isoformat()}.jsonl"

    async def log_execution(
        self,
        signal: TradeSignal,
        result: ExecutionResult,
    ) -> None:
        """Log a trade signal and its execution result.

        Appends a single JSONL record containing both the signal that triggered
        the trade and the resulting execution details.

        Args:
            signal: The trade signal that triggered execution.
            result: The result of the trade execution.

        Note:
            IO errors are logged but do not raise exceptions.
            Trading should not be interrupted by logging failures.
        """
        filepath = self._get_daily_filepath()

        record = {
            "logged_at": time(),
            "signal": signal.model_dump(),
            "result": result.model_dump(),
        }

        try:
            async with aiofiles.open(filepath, "a") as f:
                await f.write(json.dumps(record) + "\n")
        except OSError as e:
            # Log error but don't crash the bot
            logger.error("Failed to persist trade to {}: {}", filepath, e)
