"""Main Textual application for Aedes trading bot."""

import asyncio
import random
from typing import TYPE_CHECKING

from loguru import logger
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Label, RichLog, Static
from textual.worker import Worker

from src.callbacks import OrchestratorCallback
from src.models import ExecutionResult, OrderStatus, Position, Side, TradeSignal

if TYPE_CHECKING:
    from src.discovery import DiscoveryStrategy
    from src.models import ThresholdRule
    from src.orchestrator import Orchestrator
    from src.parsers.keyword import KeywordRule


class TuiCallback(OrchestratorCallback):
    """Callback implementation that updates TUI widgets."""

    def __init__(self, app: "AedesApp") -> None:
        self._app = app

    async def on_signal_generated(self, signal: TradeSignal) -> None:
        pass

    async def on_trade_executed(
        self,
        signal: TradeSignal,
        result: ExecutionResult,
    ) -> None:
        try:
            self._app.add_trade(signal, result)
        except Exception:
            pass

    async def on_error(self, error: Exception, context: str) -> None:
        pass

    async def on_metrics_updated(self, metrics: dict[str, int]) -> None:
        try:
            self._app.update_metrics(metrics)
        except Exception:
            pass

    async def on_position_updated(self, position: Position) -> None:
        try:
            self._app.update_position(position)
        except Exception:
            pass


class AedesApp(App[None]):
    """Aedes - Polymarket Event Sniper TUI.

    Features:
    - Live log display
    - Strategy statistics
    - Recent trades panel
    - Connection status
    """

    TITLE = "Aedes"
    SUB_TITLE = "Polymarket Event Sniper"

    CSS = """
    /* Catppuccin Mocha inspired palette */
    Screen {
        background: #1e1e2e;
    }

    Header {
        dock: top;
        height: 3;
        background: #181825;
        color: #f9e2af;
    }

    Footer {
        dock: bottom;
        height: 1;
        background: #181825;
        color: #6c7086;
    }

    #main {
        layout: horizontal;
    }

    #log-panel {
        width: 60%;
        border: solid #313244;
        height: 100%;
        background: #1e1e2e;
    }

    #right-panel {
        width: 40%;
        height: 100%;
    }

    #status-panel {
        border: solid #313244;
        height: auto;
        padding: 1;
        margin-bottom: 1;
        background: #1e1e2e;
    }

    #stats-panel {
        border: solid #313244;
        height: auto;
        padding: 1;
        margin-bottom: 1;
        background: #1e1e2e;
    }

    #trades-panel {
        border: solid #313244;
        height: 1fr;
        padding: 1;
        background: #1e1e2e;
    }

    .section-title {
        text-style: bold;
        color: #f9e2af;
        margin-bottom: 1;
    }

    .status-connected {
        color: #a6e3a1;
    }

    .status-disconnected {
        color: #f38ba8;
    }

    .label-value {
        color: #cdd6f4;
    }

    .label-muted {
        color: #6c7086;
    }

    .trade-buy {
        color: #a6e3a1;
    }

    .trade-sell {
        color: #f38ba8;
    }

    RichLog {
        background: #1e1e2e;
        color: #cdd6f4;
        scrollbar-color: #cba6f7;
        scrollbar-background: #313244;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("c", "clear_logs", "Clear Logs"),
    ]

    def __init__(self, demo_mode: bool = False) -> None:
        super().__init__()
        self._demo_mode = demo_mode
        self._orchestrator: "Orchestrator | None" = None
        self._orchestrator_worker: Worker[None] | None = None
        self._tui_callback: TuiCallback | None = None
        self._demo_task: asyncio.Task[None] | None = None
        self._trade_count = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            yield RichLog(id="log-panel", highlight=True, markup=True, auto_scroll=True)
            with Vertical(id="right-panel"):
                with Static(id="status-panel"):
                    yield Label("STATUS", classes="section-title")
                    yield Label("○ Disconnected", id="connection-status", classes="status-disconnected")
                    yield Label("Balance: $0.00", id="balance", classes="label-value")

                with Static(id="stats-panel"):
                    yield Label("STRATEGIES", classes="section-title")
                    yield Label("ThresholdRules: 0", id="threshold-rules", classes="label-value")
                    yield Label("KeywordRules: 0", id="keyword-rules", classes="label-value")
                    yield Label("", classes="label-muted")
                    yield Label("METRICS", classes="section-title")
                    yield Label("Events: 0", id="events", classes="label-value")
                    yield Label("Signals: 0", id="signals", classes="label-value")
                    yield Label("Trades: 0", id="trades", classes="label-value")

                with Static(id="trades-panel"):
                    yield Label("RECENT TRADES", classes="section-title")
                    yield Label("(none yet)", id="trade-list", classes="label-muted")
        yield Footer()

    async def on_mount(self) -> None:
        """Initialize on mount."""
        log = self.query_one("#log-panel", RichLog)

        if self._demo_mode:
            await self._start_demo_mode(log)
        else:
            await self._start_live_mode(log)

    async def _start_demo_mode(self, log: RichLog) -> None:
        """Start demo mode with fake data."""
        log.write("[bold #f9e2af]AEDES - DEMO MODE[/]")
        log.write("[#cba6f7]No real connections - simulated data[/]")
        log.write("")

        # Set mock initial state
        self.query_one("#connection-status", Label).update("● Connected (Demo)")
        self.query_one("#connection-status", Label).set_classes("status-connected")
        self.query_one("#balance", Label).update("Balance: $1,337.42")
        self.query_one("#threshold-rules", Label).update("ThresholdRules: 3")
        self.query_one("#keyword-rules", Label).update("KeywordRules: 4")

        self._demo_task = asyncio.create_task(self._run_demo_loop(log))

    async def _run_demo_loop(self, log: RichLog) -> None:
        """Run demo loop with fake data."""
        messages = [
            ("[#6c7086]Polling RSS: cointelegraph.com[/]", "INFO"),
            ("[#6c7086]Polling RSS: coindesk.com[/]", "INFO"),
            ("[#6c7086]WebSocket heartbeat[/]", "DEBUG"),
            ("[#a6e3a1]Price update: BTC $100k market @ 0.847[/]", "INFO"),
            ("[#a6e3a1]Price update: Epstein files @ 0.312[/]", "INFO"),
            ("[#f9e2af]Spread widening on token 7276...[/]", "WARN"),
            ("[#89b4fa]New RSS: 'Bitcoin surges past $99k'[/]", "INFO"),
            ("[#89b4fa]Keyword match: 'Bitcoin' detected[/]", "INFO"),
            ("[bold #a6e3a1]Signal: BUY $50 on Epstein market[/]", "SIGNAL"),
        ]

        demo_markets = [
            ("BTC $100k", "7276..."),
            ("Epstein Files", "8607..."),
            ("49ers vs Colts", "8545..."),
        ]

        events = 0
        signals = 0
        trades = 0

        try:
            while True:
                await asyncio.sleep(random.uniform(0.8, 2.5))

                msg, level = random.choice(messages)
                log.write(msg)
                events += 1
                self.query_one("#events", Label).update(f"Events: {events:,}")

                # Random trade (12% chance)
                if random.random() < 0.12:
                    market_name, token = random.choice(demo_markets)
                    side = random.choice([Side.BUY, Side.SELL])
                    size = random.uniform(25.0, 100.0)
                    price = random.uniform(0.15, 0.85)

                    signals += 1
                    trades += 1

                    self.query_one("#signals", Label).update(f"Signals: {signals:,}")
                    self.query_one("#trades", Label).update(f"Trades: {trades:,}")

                    side_color = "#a6e3a1" if side == Side.BUY else "#f38ba8"
                    log.write(
                        f"[bold {side_color}]TRADE: {side.value} {market_name} "
                        f"${size:.2f} @ {price:.3f}[/]"
                    )

                    # Update trade list
                    self._trade_count += 1
                    trade_class = "trade-buy" if side == Side.BUY else "trade-sell"
                    trade_label = self.query_one("#trade-list", Label)
                    trade_label.update(f"#{self._trade_count} {side.value} {market_name} @ {price:.3f}")
                    trade_label.set_classes(trade_class)

        except asyncio.CancelledError:
            log.write("[#f38ba8]Demo stopped[/]")

    async def _start_live_mode(self, log: RichLog) -> None:
        """Start live mode with real connections."""
        log.write("[bold #f9e2af]AEDES - Starting...[/]")

        try:
            self._orchestrator = await self._build_orchestrator(log)
        except Exception as e:
            log.write(f"[bold #f38ba8]Failed to start: {e}[/]")
            self.notify(f"Failed to start: {e}", severity="error")
            return

        # Update UI
        self.query_one("#connection-status", Label).update("● Connected")
        self.query_one("#connection-status", Label).set_classes("status-connected")
        self.query_one("#balance", Label).update("Balance: $1,000.00")  # Mock for now

        # Register callback
        self._tui_callback = TuiCallback(self)
        self._orchestrator.register_callback(self._tui_callback)

        # Start orchestrator
        self._orchestrator_worker = self.run_worker(
            self._run_orchestrator,
            name="orchestrator",
            exclusive=True,
        )

        log.write("[#a6e3a1]Orchestrator started[/]")

    async def _build_orchestrator(self, log: RichLog) -> "Orchestrator":
        """Build orchestrator with all components."""
        from src.config import get_settings
        from src.discovery import (
            DiscoveryStrategy,
            GammaClient,
            MarketCriteria,
            RuleTemplate,
        )
        from src.executors.polymarket import PolymarketExecutor
        from src.ingesters.polymarket import PolymarketIngester
        from src.ingesters.rss import RssIngester
        from src.interfaces.ingester import BaseIngester
        from src.interfaces.parser import BaseParser
        from src.managers import SubscriptionManager
        from src.models import ThresholdRule
        from src.orchestrator import Orchestrator
        from src.parsers.keyword import KeywordParser, KeywordRule
        from src.parsers.threshold import PriceThresholdParser
        from src.persistence import TradeLogger

        settings = get_settings()
        log.write(f"[#6c7086]Dry run mode: {settings.bot.dry_run}[/]")

        # Load rules
        threshold_rules = self._load_threshold_rules()
        keyword_rules = self._load_keyword_rules()
        rss_feeds = self._load_rss_feeds()
        discovery_strategies = self._load_discovery_strategies()

        self.query_one("#threshold-rules", Label).update(f"ThresholdRules: {len(threshold_rules)}")
        self.query_one("#keyword-rules", Label).update(f"KeywordRules: {len(keyword_rules)}")

        log.write(f"[#6c7086]Loaded {len(threshold_rules)} threshold, {len(keyword_rules)} keyword rules[/]")

        # Initialize ingester
        poly_ingester = PolymarketIngester()

        if threshold_rules:
            token_ids = list({rule.token_id for rule in threshold_rules})
            await poly_ingester.subscribe(token_ids)
            log.write(f"[#6c7086]Subscribed to {len(token_ids)} tokens[/]")

        price_parser = PriceThresholdParser(threshold_rules)

        # Discovery
        if discovery_strategies:
            log.write("[#6c7086]Running market discovery...[/]")
            try:
                async with GammaClient() as gamma_client:
                    manager = SubscriptionManager(
                        client=gamma_client,
                        ingester=poly_ingester,
                        parser=price_parser,
                        global_limit=50,
                    )
                    discovered = await manager.execute_strategies(discovery_strategies)
                    log.write(f"[#a6e3a1]Discovered {discovered} markets[/]")
            except Exception as e:
                log.write(f"[#f9e2af]Discovery failed: {e}[/]")

        # Assemble
        ingesters: list[BaseIngester] = [poly_ingester]

        if rss_feeds:
            rss_ingester = RssIngester(poll_interval=60.0)
            await rss_ingester.configure(rss_feeds)
            ingesters.append(rss_ingester)

        parsers: list[BaseParser] = [price_parser]

        if keyword_rules:
            parsers.append(KeywordParser(keyword_rules))

        executor = PolymarketExecutor(max_position_size=settings.bot.max_position_size)
        trade_logger = TradeLogger()

        return Orchestrator(
            ingesters=ingesters,
            parsers=parsers,
            executor=executor,
            trade_logger=trade_logger,
        )

    async def _run_orchestrator(self) -> None:
        """Worker coroutine for orchestrator."""
        if self._orchestrator is None:
            return

        try:
            await self._orchestrator.start()
        except Exception as e:
            log = self.query_one("#log-panel", RichLog)
            log.write(f"[bold #f38ba8]Orchestrator error: {e}[/]")

    def add_trade(self, signal: TradeSignal, result: ExecutionResult) -> None:
        """Add a trade to the display."""
        self._trade_count += 1
        side_color = "#a6e3a1" if signal.side == Side.BUY else "#f38ba8"

        log = self.query_one("#log-panel", RichLog)
        log.write(
            f"[bold {side_color}]TRADE #{self._trade_count}: {signal.side.value} "
            f"${signal.size_usdc:.2f} @ {result.filled_price:.3f}[/]"
        )

        trade_label = self.query_one("#trade-list", Label)
        trade_class = "trade-buy" if signal.side == Side.BUY else "trade-sell"
        trade_label.update(f"#{self._trade_count} {signal.side.value} @ {result.filled_price:.3f}")
        trade_label.set_classes(trade_class)

    def update_metrics(self, metrics: dict[str, int]) -> None:
        """Update metrics display."""
        self.query_one("#events", Label).update(
            f"Events: {metrics.get('events_processed', 0):,}"
        )
        self.query_one("#signals", Label).update(
            f"Signals: {metrics.get('signals_generated', 0):,}"
        )
        self.query_one("#trades", Label).update(
            f"Trades: {metrics.get('trades_executed', 0):,}"
        )

    def update_position(self, position: Position) -> None:
        """Update a position in the display (Phase 7)."""
        pass  # PositionsPanel integration is optional for now

    def action_clear_logs(self) -> None:
        """Clear the log panel."""
        self.query_one("#log-panel", RichLog).clear()

    async def action_quit(self) -> None:
        """Quit with cleanup."""
        if self._demo_task:
            self._demo_task.cancel()
            try:
                await self._demo_task
            except asyncio.CancelledError:
                pass

        if self._orchestrator:
            await self._orchestrator.stop()

        if self._orchestrator_worker:
            self._orchestrator_worker.cancel()

        self.exit()

    # Rule loaders (same as before)
    def _load_threshold_rules(self) -> list["ThresholdRule"]:
        from src.models import ThresholdRule

        return [
            ThresholdRule(
                token_id="72764351885425491292910818593903116970287593848365163845719951278848564016561",
                trigger_side=Side.BUY,
                threshold=0.95,
                comparison="below",
                size_usdc=100.0,
                reason_template="BTC $100k dip buy",
                cooldown_seconds=300.0,
            ),
        ]

    def _load_keyword_rules(self) -> list["KeywordRule"]:
        from src.parsers.keyword import KeywordRule

        return [
            KeywordRule(
                keyword="Epstein",
                token_id="86076435751570733286369126634541849471627178793773765844822295389135259614946",
                trigger_side=Side.BUY,
                size_usdc=50.0,
                reason_template="Epstein news: {keyword}",
                cooldown_seconds=600.0,
            ),
        ]

    def _load_rss_feeds(self) -> list[str]:
        return [
            "https://cointelegraph.com/rss",
            "https://www.coindesk.com/arc/outboundfeeds/rss/",
        ]

    def _load_discovery_strategies(self) -> list["DiscoveryStrategy"]:
        from src.discovery import DiscoveryStrategy, MarketCriteria, RuleTemplate

        return [
            DiscoveryStrategy(
                name="crypto_dips",
                criteria=MarketCriteria(
                    tags=["crypto"],
                    min_volume=50000.0,
                    min_liquidity=10000.0,
                    active_only=True,
                ),
                rule_template=RuleTemplate(
                    trigger_side="BUY",
                    threshold=0.20,
                    comparison="below",
                    size_usdc=25.0,
                    cooldown_seconds=300.0,
                ),
                max_markets=5,
            ),
        ]


# Keep old name as alias for backward compatibility
SniperApp = AedesApp
