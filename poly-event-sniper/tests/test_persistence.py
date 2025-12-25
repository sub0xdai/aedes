"""Tests for the persistence layer (TradeLogger)."""

import json
from datetime import date
from pathlib import Path

import pytest

from src.models import ExecutionResult, OrderStatus, Side, TradeSignal
from src.persistence import TradeLogger


@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory for tests."""
    return tmp_path / "data"


@pytest.fixture
def trade_logger(temp_data_dir: Path) -> TradeLogger:
    """Create a TradeLogger instance with temporary directory."""
    return TradeLogger(data_dir=temp_data_dir)


@pytest.fixture
def sample_signal() -> TradeSignal:
    """Create a sample trade signal for testing."""
    return TradeSignal(
        token_id="test_token_123",
        side=Side.BUY,
        size_usdc=100.0,
        reason="Test threshold triggered",
        timestamp=1234567890.0,
    )


@pytest.fixture
def sample_result() -> ExecutionResult:
    """Create a sample execution result for testing."""
    return ExecutionResult(
        order_id="order_abc_123",
        status=OrderStatus.FILLED,
        filled_price=0.55,
        filled_size=181.82,
        fees_paid=0.50,
        execution_timestamp=1234567891.0,
    )


class TestTradeLoggerInit:
    """Tests for TradeLogger initialization."""

    def test_creates_data_directory(self, temp_data_dir: Path) -> None:
        """TradeLogger should create the data directory if it doesn't exist."""
        assert not temp_data_dir.exists()
        TradeLogger(data_dir=temp_data_dir)
        assert temp_data_dir.exists()
        assert temp_data_dir.is_dir()

    def test_uses_existing_directory(self, temp_data_dir: Path) -> None:
        """TradeLogger should work with an existing directory."""
        temp_data_dir.mkdir(parents=True)
        # Should not raise
        TradeLogger(data_dir=temp_data_dir)

    def test_default_data_directory(self) -> None:
        """TradeLogger should default to 'data' directory."""
        logger = TradeLogger()
        assert logger._data_dir == Path("data")


class TestTradeLoggerLogExecution:
    """Tests for TradeLogger.log_execution method."""

    @pytest.mark.asyncio
    async def test_creates_daily_file(
        self,
        trade_logger: TradeLogger,
        temp_data_dir: Path,
        sample_signal: TradeSignal,
        sample_result: ExecutionResult,
    ) -> None:
        """log_execution should create a daily JSONL file."""
        await trade_logger.log_execution(sample_signal, sample_result)

        expected_file = temp_data_dir / f"trades_{date.today().isoformat()}.jsonl"
        assert expected_file.exists()

    @pytest.mark.asyncio
    async def test_appends_to_existing_file(
        self,
        trade_logger: TradeLogger,
        temp_data_dir: Path,
        sample_signal: TradeSignal,
        sample_result: ExecutionResult,
    ) -> None:
        """Multiple log_execution calls should append to the same file."""
        await trade_logger.log_execution(sample_signal, sample_result)
        await trade_logger.log_execution(sample_signal, sample_result)
        await trade_logger.log_execution(sample_signal, sample_result)

        filepath = temp_data_dir / f"trades_{date.today().isoformat()}.jsonl"
        lines = filepath.read_text().strip().split("\n")
        assert len(lines) == 3

    @pytest.mark.asyncio
    async def test_record_contains_signal_and_result(
        self,
        trade_logger: TradeLogger,
        temp_data_dir: Path,
        sample_signal: TradeSignal,
        sample_result: ExecutionResult,
    ) -> None:
        """Each record should contain both signal and result data."""
        await trade_logger.log_execution(sample_signal, sample_result)

        filepath = temp_data_dir / f"trades_{date.today().isoformat()}.jsonl"
        record = json.loads(filepath.read_text().strip())

        assert "signal" in record
        assert "result" in record
        assert "logged_at" in record

    @pytest.mark.asyncio
    async def test_signal_serialization(
        self,
        trade_logger: TradeLogger,
        temp_data_dir: Path,
        sample_signal: TradeSignal,
        sample_result: ExecutionResult,
    ) -> None:
        """Signal should be serialized correctly."""
        await trade_logger.log_execution(sample_signal, sample_result)

        filepath = temp_data_dir / f"trades_{date.today().isoformat()}.jsonl"
        record = json.loads(filepath.read_text().strip())

        assert record["signal"]["token_id"] == "test_token_123"
        assert record["signal"]["side"] == "BUY"
        assert record["signal"]["size_usdc"] == 100.0
        assert record["signal"]["reason"] == "Test threshold triggered"

    @pytest.mark.asyncio
    async def test_result_serialization(
        self,
        trade_logger: TradeLogger,
        temp_data_dir: Path,
        sample_signal: TradeSignal,
        sample_result: ExecutionResult,
    ) -> None:
        """Result should be serialized correctly."""
        await trade_logger.log_execution(sample_signal, sample_result)

        filepath = temp_data_dir / f"trades_{date.today().isoformat()}.jsonl"
        record = json.loads(filepath.read_text().strip())

        assert record["result"]["order_id"] == "order_abc_123"
        assert record["result"]["status"] == "FILLED"
        assert record["result"]["filled_price"] == 0.55
        assert record["result"]["filled_size"] == 181.82
        assert record["result"]["fees_paid"] == 0.50

    @pytest.mark.asyncio
    async def test_logged_at_timestamp(
        self,
        trade_logger: TradeLogger,
        temp_data_dir: Path,
        sample_signal: TradeSignal,
        sample_result: ExecutionResult,
    ) -> None:
        """logged_at should be a valid timestamp."""
        import time

        before = time.time()
        await trade_logger.log_execution(sample_signal, sample_result)
        after = time.time()

        filepath = temp_data_dir / f"trades_{date.today().isoformat()}.jsonl"
        record = json.loads(filepath.read_text().strip())

        assert before <= record["logged_at"] <= after

    @pytest.mark.asyncio
    async def test_valid_jsonl_format(
        self,
        trade_logger: TradeLogger,
        temp_data_dir: Path,
        sample_signal: TradeSignal,
        sample_result: ExecutionResult,
    ) -> None:
        """Each line should be valid JSON (JSONL format)."""
        # Log multiple entries
        for _ in range(5):
            await trade_logger.log_execution(sample_signal, sample_result)

        filepath = temp_data_dir / f"trades_{date.today().isoformat()}.jsonl"
        lines = filepath.read_text().strip().split("\n")

        # Each line should parse as valid JSON
        for line in lines:
            record = json.loads(line)
            assert isinstance(record, dict)
            assert "signal" in record
            assert "result" in record


class TestTradeLoggerErrorHandling:
    """Tests for TradeLogger error handling."""

    @pytest.mark.asyncio
    async def test_handles_io_error_gracefully(
        self,
        sample_signal: TradeSignal,
        sample_result: ExecutionResult,
    ) -> None:
        """TradeLogger should not crash on IO errors."""
        # Use an invalid path that can't be created
        logger = TradeLogger(data_dir=Path("/nonexistent/readonly/path"))

        # Should not raise - just log the error
        await logger.log_execution(sample_signal, sample_result)
