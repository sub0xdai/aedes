"""Orchestrator connecting ingestion, parsing, and execution layers."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import TYPE_CHECKING

from loguru import logger

from src.callbacks import OrchestratorCallback
from src.interfaces.executor import BaseExecutor
from src.interfaces.ingester import BaseIngester
from src.interfaces.parser import BaseParser
from src.interfaces.strategy import BaseStrategy
from src.models import ExecutionResult, MarketEvent, Order, TradeSignal
from src.persistence import TradeLogger

if TYPE_CHECKING:
    from src.managers.portfolio import PortfolioManager
    from src.persistence import DatabaseManager


class Orchestrator:
    """Central orchestrator for the trading bot.

    Connects ingesters, parsers, and executors into a unified pipeline.
    Handles graceful shutdown, error recovery, and metrics collection.

    Supports N:N ingestion/parsing - multiple ingesters feed into a shared
    queue, and each event is evaluated by all parsers.
    """

    def __init__(
        self,
        ingester_or_executor: BaseIngester | BaseExecutor | None = None,
        parser_or_logger: BaseParser | TradeLogger | None = None,
        executor_legacy: BaseExecutor | None = None,
        trade_logger: TradeLogger | None = None,
        *,
        # New multi-source parameters (Sequence for covariance)
        ingesters: Sequence[BaseIngester] | None = None,
        parsers: Sequence[BaseParser] | None = None,
        executor: BaseExecutor | None = None,
        # Legacy single-source parameters (keyword form)
        ingester: BaseIngester | None = None,
        parser: BaseParser | None = None,
        # Phase 7 parameters
        strategies: Sequence[BaseStrategy] | None = None,
        portfolio: PortfolioManager | None = None,
        database: DatabaseManager | None = None,
    ) -> None:
        """Initialize the orchestrator.

        Supports multiple calling conventions:
        1. Legacy: Orchestrator(ingester, parser, executor, trade_logger?)
        2. Multi-source: Orchestrator(executor=..., ingesters=[...], parsers=[...])
        3. Strategy-based: Orchestrator(executor=..., ingesters=[...], strategies=[...])

        Args:
            executor: Order execution implementation.
            trade_logger: Optional trade persistence logger (JSONL).
            ingesters: List of data source implementations.
            parsers: List of signal parsing implementations.
            ingester: (Legacy) Single data source implementation.
            parser: (Legacy) Single signal parsing implementation.
            strategies: List of strategy implementations (Phase 7).
            portfolio: Portfolio manager for position tracking (Phase 7).
            database: Database manager for SQLite persistence (Phase 7).
        """
        # Detect legacy positional call pattern: (ingester, parser, executor, ...)
        if (ingester_or_executor is not None
                and isinstance(ingester_or_executor, BaseIngester)):
            # Legacy positional: Orchestrator(ingester, parser, executor, trade_logger?)
            ingester = ingester_or_executor
            if isinstance(parser_or_logger, BaseParser):
                parser = parser_or_logger
            if executor_legacy is not None:
                executor = executor_legacy
            if trade_logger is None and isinstance(parser_or_logger, TradeLogger):
                trade_logger = parser_or_logger
        elif ingester_or_executor is not None and isinstance(ingester_or_executor, BaseExecutor):
            # New style with executor as first positional
            executor = ingester_or_executor
            if isinstance(parser_or_logger, TradeLogger):
                trade_logger = parser_or_logger

        # Resolve ingesters (convert Sequence to list for internal storage)
        if ingesters is not None:
            self._ingesters: list[BaseIngester] = list(ingesters)
        elif ingester is not None:
            self._ingesters = [ingester]
        else:
            raise ValueError("Either 'ingesters' or 'ingester' must be provided")

        # Resolve strategies (Phase 7)
        if strategies is not None:
            self._strategies: list[BaseStrategy] = list(strategies)
            self._parsers: list[BaseParser] = []
        elif parsers is not None:
            self._parsers = list(parsers)
            self._strategies = []
        elif parser is not None:
            self._parsers = [parser]
            self._strategies = []
        else:
            raise ValueError("Either 'strategies', 'parsers', or 'parser' must be provided")

        # Resolve executor
        if executor is None:
            raise ValueError("'executor' must be provided")

        self._executor = executor
        self._trade_logger = trade_logger
        self._portfolio = portfolio
        self._database = database
        self._is_running = False
        self._event_queue: asyncio.Queue[MarketEvent] = asyncio.Queue()
        self._ingester_tasks: list[asyncio.Task[None]] = []

        # Metrics
        self._events_processed = 0
        self._signals_generated = 0
        self._trades_executed = 0
        self._errors_encountered = 0

        # Callbacks for TUI/external observers
        self._callbacks: list[OrchestratorCallback] = []

    def register_callback(self, callback: OrchestratorCallback) -> None:
        """Register a callback for orchestrator events.

        Callbacks are invoked asynchronously during event processing.
        Failing callbacks are caught and logged - they never crash the pipeline.

        Args:
            callback: An object implementing OrchestratorCallback protocol.
        """
        self._callbacks.append(callback)

    async def _forward_stream(self, ingester: BaseIngester) -> None:
        """Forward events from an ingester to the shared queue."""
        try:
            async for event in ingester.stream():
                if not self._is_running:
                    break
                await self._event_queue.put(event)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Ingester stream error: {}", str(e))

    async def start(self) -> None:
        """Start the trading pipeline.

        Note:
            Ingesters must be configured (subscribe/configure called) before starting.
            This is done in main.py to handle different ingester types appropriately.
        """
        logger.info("Starting orchestrator with {} ingesters and {} parsers",
                    len(self._ingesters), len(self._parsers))

        # Setup executor
        await self._executor.setup()

        # Connect all ingesters
        for ingester in self._ingesters:
            await ingester.connect()

        self._is_running = True

        # Launch forwarding tasks for each ingester
        for ingester in self._ingesters:
            task = asyncio.create_task(self._forward_stream(ingester))
            self._ingester_tasks.append(task)

        # Main event loop - consume from shared queue
        try:
            while self._is_running:
                # Use wait_for with timeout to allow checking _is_running
                try:
                    event = await asyncio.wait_for(
                        self._event_queue.get(), timeout=0.1
                    )
                    await self._process_event(event)
                except asyncio.TimeoutError:
                    # Check if all ingester tasks are done
                    if all(task.done() for task in self._ingester_tasks):
                        # Drain remaining events from queue
                        while not self._event_queue.empty():
                            event = self._event_queue.get_nowait()
                            await self._process_event(event)
                        break

        except asyncio.CancelledError:
            logger.info("Orchestrator cancelled")
        finally:
            await self.stop()

    async def _process_event(self, event: MarketEvent) -> None:
        """Process a single market event through strategies or parsers."""
        self._events_processed += 1

        # Update portfolio with price if available (Phase 7)
        if self._portfolio and event.token_id and event.last_price:
            await self._portfolio.on_price_update(event.token_id, event.last_price)

        # Use strategies if available (Phase 7), otherwise fall back to parsers
        if self._strategies:
            await self._process_with_strategies(event)
        else:
            await self._process_with_parsers(event)

        # Emit metrics_updated callback after processing
        await self._emit_metrics_updated()

    async def _process_with_strategies(self, event: MarketEvent) -> None:
        """Process event using Phase 7 strategy-based approach."""
        for strategy in self._strategies:
            try:
                # Call on_tick
                strategy.on_tick(event)

                # Collect generated orders
                orders = strategy.generate_signals()

                for order in orders:
                    await self._execute_order(order, strategy)

            except Exception as e:
                self._errors_encountered += 1
                logger.error("Error in strategy {}: {}", strategy.name, str(e), exc_info=True)
                await self._emit_error(e, f"strategy={strategy.name}")

    async def _execute_order(self, order: Order, strategy: BaseStrategy) -> None:
        """Execute an order with portfolio validation (Phase 7)."""
        # Validate against portfolio if available
        if self._portfolio:
            is_valid, reason = self._portfolio.check_order(order)
            if not is_valid:
                logger.warning("Order rejected: {}", reason)
                return

        self._signals_generated += 1
        logger.info(
            "Order generated | token={} side={} qty={}",
            order.token_id,
            order.side.value,
            order.quantity,
        )

        # Execute order
        try:
            result = await self._execute_order_impl(order)
            self._trades_executed += 1

            logger.info(
                "Order executed | order_id={} status={} price={}",
                result.order_id,
                result.status.value,
                result.filled_price,
            )

            # Update portfolio
            if self._portfolio:
                await self._portfolio.on_fill(order, result)

            # Notify strategy
            strategy.on_fill(order, result)

            # Emit callback (convert Order to TradeSignal for compatibility)
            signal = TradeSignal(
                token_id=order.token_id,
                side=order.side,
                size_usdc=order.quantity * result.filled_price,
                reason=order.reason,
            )
            await self._emit_trade_executed(signal, result)

            # Persist to JSONL
            if self._trade_logger:
                await self._trade_logger.log_execution(signal, result)

            # Persist to SQLite (Phase 7)
            if self._database:
                await self._database.insert_trade(order, result)

        except Exception as e:
            self._errors_encountered += 1
            logger.error("Order execution failed: {}", str(e), exc_info=True)
            await self._emit_error(e, f"order={order.client_order_id}")

    async def _execute_order_impl(self, order: Order) -> ExecutionResult:
        """Execute an order, supporting both Order and TradeSignal execution."""
        # Check if executor has execute_order method (Phase 7)
        if hasattr(self._executor, "execute_order"):
            execute_order = getattr(self._executor, "execute_order")
            result: ExecutionResult = await execute_order(order)
            return result

        # Fall back to TradeSignal-based execution
        signal = TradeSignal(
            token_id=order.token_id,
            side=order.side,
            size_usdc=order.quantity * 0.5,  # Estimate using mid-price
            reason=order.reason,
        )
        return await self._executor.execute(signal)

    async def _process_with_parsers(self, event: MarketEvent) -> None:
        """Process event using legacy parser-based approach."""
        for parser in self._parsers:
            try:
                signal = parser.evaluate(event)

                if signal is None:
                    continue

                self._signals_generated += 1
                logger.info(
                    "Signal generated | token={} side={} size={}",
                    signal.token_id,
                    signal.side.value,
                    signal.size_usdc,
                )

                # Emit signal_generated callback
                await self._emit_signal_generated(signal)

                # Execute trade
                result = await self._executor.execute(signal)
                self._trades_executed += 1

                logger.info(
                    "Trade executed | order_id={} status={} price={}",
                    result.order_id,
                    result.status.value,
                    result.filled_price,
                )

                # Emit trade_executed callback
                await self._emit_trade_executed(signal, result)

                # Persist trade data
                if self._trade_logger:
                    await self._trade_logger.log_execution(signal, result)

            except Exception as e:
                self._errors_encountered += 1
                logger.error("Error processing event: {}", str(e), exc_info=True)

                # Emit error callback
                await self._emit_error(e, f"parser={parser.__class__.__name__}")

    async def _emit_signal_generated(self, signal: TradeSignal) -> None:
        """Emit signal_generated to all callbacks (fail-safe)."""
        for callback in self._callbacks:
            try:
                await callback.on_signal_generated(signal)
            except Exception as e:
                logger.debug("Callback error in on_signal_generated: {}", str(e))

    async def _emit_trade_executed(
        self, signal: TradeSignal, result: ExecutionResult
    ) -> None:
        """Emit trade_executed to all callbacks (fail-safe)."""
        for callback in self._callbacks:
            try:
                await callback.on_trade_executed(signal, result)
            except Exception as e:
                logger.debug("Callback error in on_trade_executed: {}", str(e))

    async def _emit_error(self, error: Exception, context: str) -> None:
        """Emit error to all callbacks (fail-safe)."""
        for callback in self._callbacks:
            try:
                await callback.on_error(error, context)
            except Exception as e:
                logger.debug("Callback error in on_error: {}", str(e))

    async def _emit_metrics_updated(self) -> None:
        """Emit metrics_updated to all callbacks (fail-safe)."""
        metrics = self.metrics
        for callback in self._callbacks:
            try:
                await callback.on_metrics_updated(metrics)
            except Exception as e:
                logger.debug("Callback error in on_metrics_updated: {}", str(e))

    async def stop(self) -> None:
        """Gracefully stop the trading pipeline."""
        logger.info("Stopping orchestrator")
        self._is_running = False

        # Cancel all ingester forwarding tasks
        for task in self._ingester_tasks:
            task.cancel()

        # Wait for tasks to complete
        if self._ingester_tasks:
            await asyncio.gather(*self._ingester_tasks, return_exceptions=True)

        # Disconnect all ingesters
        for ingester in self._ingesters:
            await ingester.disconnect()

        # Log final metrics
        logger.info(
            "Final metrics: events={} signals={} trades={} errors={}",
            self._events_processed,
            self._signals_generated,
            self._trades_executed,
            self._errors_encountered,
        )

    @property
    def metrics(self) -> dict[str, int]:
        """Get current metrics."""
        return {
            "events_processed": self._events_processed,
            "signals_generated": self._signals_generated,
            "trades_executed": self._trades_executed,
            "errors_encountered": self._errors_encountered,
        }
