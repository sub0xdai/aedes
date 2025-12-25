"""Integration tests for the event sniping pipeline.

Tests the full flow: External Event -> KeywordParser -> Executor -> TradeLogger
"""

import asyncio
import json
from pathlib import Path

import pytest

from src.ingesters.external import ManualEventIngester
from src.models import EventType, MarketEvent, OrderStatus, Side
from src.orchestrator import Orchestrator
from src.parsers.keyword import KeywordParser, KeywordRule
from src.persistence import TradeLogger
from tests.test_orchestrator import MockExecutor


class AutoDisconnectIngester(ManualEventIngester):
    """ManualEventIngester that auto-disconnects after processing all events."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._expected_count = 0
        self._processed_count = 0

    def set_expected_events(self, count: int) -> None:
        """Set expected number of events to process before disconnecting."""
        self._expected_count = count

    async def stream(self):
        """Stream events and auto-disconnect after expected count."""
        async for event in super().stream():
            yield event
            self._processed_count += 1
            if self._processed_count >= self._expected_count:
                await self.disconnect()
                break


class TestEventSnipingPipeline:
    """Integration tests for the complete event sniping flow."""

    @pytest.fixture
    def keyword_rules(self) -> list[KeywordRule]:
        """Sample keyword rules for testing."""
        return [
            KeywordRule(
                keyword="FED HIKE",
                token_id="token_fed_rates",
                trigger_side=Side.BUY,
                size_usdc=100.0,
                reason_template="FED rate hike detected: {keyword}",
                cooldown_seconds=0.0,  # No cooldown for tests
            ),
            KeywordRule(
                keyword="RECESSION",
                token_id="token_recession",
                trigger_side=Side.SELL,
                size_usdc=75.0,
                reason_template="Recession signal: {keyword}",
                cooldown_seconds=0.0,
            ),
        ]

    @pytest.fixture
    def trade_logger(self, tmp_path: Path) -> TradeLogger:
        """Create trade logger with temp directory."""
        return TradeLogger(data_dir=tmp_path / "data")

    @pytest.mark.asyncio
    async def test_inject_fed_hike_generates_signal_and_trade(
        self,
        keyword_rules: list[KeywordRule],
        trade_logger: TradeLogger,
        tmp_path: Path,
    ) -> None:
        """Full flow: Inject 'FED HIKE' -> KeywordParser -> Execute -> Log."""
        # Setup components
        ingester = AutoDisconnectIngester(default_source="test")
        ingester.set_expected_events(1)
        parser = KeywordParser(keyword_rules)
        executor = MockExecutor()

        orchestrator = Orchestrator(
            ingester=ingester,
            parser=parser,
            executor=executor,
            trade_logger=trade_logger,
        )

        # Inject the event before connecting
        await ingester.inject_event(
            "Breaking: FED HIKE of 25 basis points announced today",
            source="reuters",
        )

        # Run orchestrator (will process injected event then auto-disconnect)
        await orchestrator.start()

        # Verify signal was generated and executed
        assert len(executor.executed_signals) == 1
        signal = executor.executed_signals[0]
        assert signal.token_id == "token_fed_rates"
        assert signal.side == Side.BUY
        assert signal.size_usdc == 100.0
        assert "FED rate hike detected" in signal.reason

        # Verify metrics
        metrics = orchestrator.metrics
        assert metrics["events_processed"] == 1
        assert metrics["signals_generated"] == 1
        assert metrics["trades_executed"] == 1

        # Verify trade was logged
        from datetime import date

        log_file = tmp_path / "data" / f"trades_{date.today().isoformat()}.jsonl"
        assert log_file.exists()

        record = json.loads(log_file.read_text().strip())
        assert record["signal"]["token_id"] == "token_fed_rates"
        assert record["result"]["status"] == "FILLED"

    @pytest.mark.asyncio
    async def test_no_match_no_trade(
        self,
        keyword_rules: list[KeywordRule],
        trade_logger: TradeLogger,
    ) -> None:
        """Events without keyword matches should not generate trades."""
        ingester = AutoDisconnectIngester()
        ingester.set_expected_events(1)
        parser = KeywordParser(keyword_rules)
        executor = MockExecutor()

        orchestrator = Orchestrator(
            ingester=ingester,
            parser=parser,
            executor=executor,
            trade_logger=trade_logger,
        )

        # Inject non-matching event
        await ingester.inject_event(
            "Weather forecast: sunny skies expected",
            source="weather_api",
        )

        await orchestrator.start()

        # No trades should be executed
        assert len(executor.executed_signals) == 0
        assert orchestrator.metrics["events_processed"] == 1
        assert orchestrator.metrics["signals_generated"] == 0
        assert orchestrator.metrics["trades_executed"] == 0

    @pytest.mark.asyncio
    async def test_multiple_events_processed(
        self,
        keyword_rules: list[KeywordRule],
        trade_logger: TradeLogger,
    ) -> None:
        """Multiple events should be processed in sequence."""
        ingester = AutoDisconnectIngester()
        ingester.set_expected_events(3)
        parser = KeywordParser(keyword_rules)
        executor = MockExecutor()

        orchestrator = Orchestrator(
            ingester=ingester,
            parser=parser,
            executor=executor,
            trade_logger=trade_logger,
        )

        # Inject multiple events
        await ingester.inject_event("Breaking: FED HIKE announced", source="reuters")
        await ingester.inject_event("Analysts warn of RECESSION risk", source="bloomberg")
        await ingester.inject_event("Stocks rally on earnings", source="cnbc")

        await orchestrator.start()

        # Two matching events should generate trades
        assert len(executor.executed_signals) == 2
        assert orchestrator.metrics["events_processed"] == 3
        assert orchestrator.metrics["signals_generated"] == 2
        assert orchestrator.metrics["trades_executed"] == 2

        # Verify both trades
        tokens_traded = {s.token_id for s in executor.executed_signals}
        assert "token_fed_rates" in tokens_traded
        assert "token_recession" in tokens_traded

    @pytest.mark.asyncio
    async def test_social_event_triggers_trade(
        self,
        keyword_rules: list[KeywordRule],
        trade_logger: TradeLogger,
    ) -> None:
        """SOCIAL events should also trigger keyword matching."""
        ingester = AutoDisconnectIngester()
        ingester.set_expected_events(1)
        parser = KeywordParser(keyword_rules)
        executor = MockExecutor()

        orchestrator = Orchestrator(
            ingester=ingester,
            parser=parser,
            executor=executor,
            trade_logger=trade_logger,
        )

        # Inject SOCIAL event
        await ingester.inject_event(
            "@fed_watcher: FED HIKE coming tomorrow!",
            source="twitter",
            event_type=EventType.SOCIAL,
        )

        await orchestrator.start()

        assert len(executor.executed_signals) == 1
        assert executor.executed_signals[0].token_id == "token_fed_rates"


class TestEventSnipingErrorHandling:
    """Tests for error handling in event sniping pipeline."""

    @pytest.mark.asyncio
    async def test_executor_error_does_not_crash_pipeline(self) -> None:
        """Executor errors should be logged but not crash the pipeline."""
        from src.interfaces.executor import BaseExecutor
        from src.models import ExecutionResult, TradeSignal

        class FailingExecutor(BaseExecutor):
            async def setup(self) -> None:
                pass

            async def execute(self, signal: TradeSignal) -> ExecutionResult:
                raise ValueError("Simulated execution failure")

            async def get_balance(self) -> float:
                return 10000.0

        rules = [
            KeywordRule(
                keyword="test",
                token_id="token_test",
                trigger_side=Side.BUY,
                size_usdc=50.0,
                cooldown_seconds=0.0,
            ),
        ]

        ingester = AutoDisconnectIngester()
        ingester.set_expected_events(1)
        parser = KeywordParser(rules)
        executor = FailingExecutor()

        orchestrator = Orchestrator(
            ingester=ingester,
            parser=parser,
            executor=executor,
        )

        await ingester.inject_event("test message")
        await orchestrator.start()

        # Signal was generated but execution failed
        assert orchestrator.metrics["signals_generated"] == 1
        assert orchestrator.metrics["trades_executed"] == 0
        assert orchestrator.metrics["errors_encountered"] == 1
