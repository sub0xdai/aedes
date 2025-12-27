"""Main Textual application for Aedes trading bot."""

import asyncio
import random
from typing import TYPE_CHECKING

from loguru import logger
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Label, RichLog
from textual.worker import Worker

from src.callbacks import OrchestratorCallback
from src.models import ExecutionResult, OrderStatus, Position, Side, TradeSignal
from src.tui.widgets.global_header import GlobalHeader
from src.tui.widgets.unlock_modal import UnlockModal
from src.wallet import WalletManager

if TYPE_CHECKING:
    from src.discovery import DiscoveryStrategy
    from src.models import ThresholdRule
    from src.orchestrator import Orchestrator
    from src.parsers.keyword import KeywordRule
    from src.wallet import Wallet


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
    - Modal unlock overlay on startup
    - Global header with wallet info
    - Expanded log panel
    - Compact sidebar (50% stats, 50% trades)
    """

    TITLE = "Aedes"
    SUB_TITLE = "Polymarket Event Sniper"

    CSS = """
    /* Catppuccin Mocha palette */
    Screen {
        background: #1e1e2e;
    }

    /* Main layout */
    #main {
        layout: horizontal;
        height: 1fr;
    }

    /* Log panel - expanded */
    #log-panel {
        width: 1fr;
        min-width: 50%;
        border: round #313244;
        background: #1e1e2e;
        margin: 0 1 0 0;
    }

    /* Compact sidebar */
    #sidebar {
        width: 32;
        max-width: 40;
        height: 100%;
    }

    /* Stats panel - top 50% */
    #stats-panel {
        border: round #313244;
        height: 50%;
        padding: 1;
        background: #1e1e2e;
    }

    /* Trades panel - bottom 50% */
    #trades-panel {
        border: round #313244;
        height: 50%;
        padding: 1;
        background: #1e1e2e;
    }

    .section-title {
        text-style: bold;
        color: #f9e2af;
        margin-bottom: 1;
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

    /* Footer styling */
    Footer {
        background: #181825;
    }

    Footer > .footer--highlight {
        background: #313244;
    }

    Footer > .footer--key {
        color: #cba6f7;
        background: #313244;
    }

    Footer > .footer--highlight-key {
        color: #f9e2af;
        background: #45475a;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("c", "clear_logs", "Clear"),
        ("u", "toggle_lock", "Lock/Unlock"),
        ("w", "manage_wallets", "Wallets"),
    ]

    def __init__(self, demo_mode: bool = False) -> None:
        super().__init__()
        self._demo_mode = demo_mode
        self._orchestrator: "Orchestrator | None" = None
        self._orchestrator_worker: Worker[None] | None = None
        self._tui_callback: TuiCallback | None = None
        self._demo_task: asyncio.Task[None] | None = None
        self._trade_count = 0
        self._wallet_manager = WalletManager()
        self._active_wallet: "Wallet | None" = None

    def compose(self) -> ComposeResult:
        # Global header
        yield GlobalHeader(id="global-header")

        with Horizontal(id="main"):
            # Expanded log panel
            yield RichLog(id="log-panel", highlight=True, markup=True, auto_scroll=True)

            # Compact sidebar (no wallet panel - moved to header)
            with Vertical(id="sidebar"):
                # Stats panel - 50%
                with Vertical(id="stats-panel"):
                    yield Label("STRATEGIES", classes="section-title")
                    yield Label("Threshold: 0", id="threshold-rules", classes="label-value")
                    yield Label("Keyword: 0", id="keyword-rules", classes="label-value")
                    yield Label("")
                    yield Label("METRICS", classes="section-title")
                    yield Label("Events: 0", id="events", classes="label-value")
                    yield Label("Signals: 0", id="signals", classes="label-value")
                    yield Label("Trades: 0", id="trades", classes="label-value")

                # Trades panel - 50%
                with Vertical(id="trades-panel"):
                    yield Label("RECENT TRADES", classes="section-title")
                    yield Label("(none)", id="trade-list", classes="label-muted")

        yield Footer()

    async def on_mount(self) -> None:
        """Initialize on mount."""
        log = self.query_one("#log-panel", RichLog)
        header = self.query_one("#global-header", GlobalHeader)

        if self._demo_mode:
            await self._start_demo_mode(log, header)
        else:
            await self._start_live_mode_init(log, header)

    async def _start_live_mode_init(self, log: RichLog, header: GlobalHeader) -> None:
        """Initialize live mode."""
        from src.config import get_settings

        settings = get_settings()
        header.set_dry_run(settings.bot.dry_run)

        log.write("[bold #f9e2af]AEDES[/] - Polymarket Event Sniper")
        log.write("")

        # Check if wallet needs unlock
        if self._wallet_manager.has_wallets():
            log.write("[#6c7086]Wallet found - showing unlock dialog...[/]")
            # Show unlock modal
            self._show_unlock_modal()
        else:
            log.write("[#6c7086]No wallet - showing create dialog...[/]")
            # Show create modal
            self._show_unlock_modal()

        log.write(f"[#6c7086]Mode: {'DRY RUN' if settings.bot.dry_run else 'LIVE'}[/]")
        log.write("[#6c7086]Starting market feed...[/]")
        log.write("")

        # Start orchestrator (view-only until wallet unlocked)
        await self._start_live_mode(log)

    def _handle_wallet_change(self, wallet: "Wallet | None", env_fallback: bool = False) -> None:
        """Handle wallet change from modal.

        Args:
            wallet: The new wallet, or None if cancelled.
            env_fallback: Whether .env wallet is available as fallback.
        """
        if wallet:
            self._active_wallet = wallet
            header = self.query_one("#global-header", GlobalHeader)
            header.set_wallet(wallet.address, 0.0)

            log = self.query_one("#log-panel", RichLog)
            log.write(f"[#a6e3a1]Wallet active: {wallet.short_address}[/]")

            # Restart orchestrator with wallet
            if self._orchestrator:
                asyncio.create_task(self._restart_with_wallet())
        elif env_fallback:
            # User chose to use .env wallet - executor will use it
            log = self.query_one("#log-panel", RichLog)
            log.write("[#89b4fa]Using .env wallet for trading[/]")

    def _show_unlock_modal(self, initial_view: str | None = None) -> None:
        """Show the unlock/create wallet modal.

        Args:
            initial_view: Optional initial view to show (e.g., "manage").
        """
        from src.config import get_settings

        # Check if .env has a valid private key
        settings = get_settings()
        env_key = settings.polygon.private_key.get_secret_value()
        env_wallet_available = bool(env_key) and len(env_key) >= 64

        def handle_result(wallet: "Wallet | None") -> None:
            self._handle_wallet_change(wallet, env_fallback=env_wallet_available)

        self.push_screen(
            UnlockModal(
                self._wallet_manager,
                env_wallet_available=env_wallet_available,
                initial_view=initial_view,
            ),
            handle_result,
        )

    def action_toggle_lock(self) -> None:
        """Toggle wallet lock state."""
        if self._active_wallet:
            # Lock wallet
            self._active_wallet = None
            self._wallet_manager._active_wallet = None
            header = self.query_one("#global-header", GlobalHeader)
            header.clear_wallet()

            log = self.query_one("#log-panel", RichLog)
            log.write("[#f9e2af]Wallet locked[/]")
        else:
            # Show unlock modal
            self._show_unlock_modal()

    def action_manage_wallets(self) -> None:
        """Open wallet management modal."""
        self._show_unlock_modal(initial_view="manage")

    def on_unlock_modal_wallet_unlocked(self, event: UnlockModal.WalletUnlocked) -> None:
        """Handle wallet unlock from modal."""
        self._active_wallet = event.wallet
        header = self.query_one("#global-header", GlobalHeader)
        header.set_wallet(event.wallet.address, 0.0)

        log = self.query_one("#log-panel", RichLog)
        log.write(f"[#a6e3a1]Wallet unlocked: {event.wallet.short_address}[/]")

    def on_unlock_modal_wallet_created(self, event: UnlockModal.WalletCreated) -> None:
        """Handle wallet creation from modal."""
        self._active_wallet = event.wallet
        header = self.query_one("#global-header", GlobalHeader)
        header.set_wallet(event.wallet.address, 0.0)

        log = self.query_one("#log-panel", RichLog)
        log.write(f"[#a6e3a1]Wallet created: {event.wallet.short_address}[/]")
        log.write(f"[#89b4fa]Deposit address: {event.wallet.address}[/]")
        log.write("[#6c7086]Fund with USDC on Polygon to start trading[/]")

    async def _restart_with_wallet(self) -> None:
        """Restart orchestrator with wallet."""
        log = self.query_one("#log-panel", RichLog)
        log.write("[#6c7086]Restarting with wallet...[/]")

        if self._orchestrator:
            await self._orchestrator.stop()

        if self._orchestrator_worker:
            self._orchestrator_worker.cancel()

        await self._start_live_mode(log)

    async def _start_demo_mode(self, log: RichLog, header: GlobalHeader) -> None:
        """Start demo mode."""
        header.set_connected(True)
        header.set_wallet("0x1234567890abcdef1234567890abcdef12345678", 1337.42)
        header.set_dry_run(False)

        log.write("[bold #f9e2af]AEDES[/] - DEMO MODE")
        log.write("[#cba6f7]Simulated data - no real connections[/]")
        log.write("")

        # Set initial stats
        self.query_one("#threshold-rules", Label).update("Threshold: 3")
        self.query_one("#keyword-rules", Label).update("Keyword: 4")

        self._demo_task = asyncio.create_task(self._run_demo_loop(log))

    async def _run_demo_loop(self, log: RichLog) -> None:
        """Demo loop with fake data."""
        messages = [
            "[#6c7086]RSS: cointelegraph.com[/]",
            "[#6c7086]RSS: coindesk.com[/]",
            "[#6c7086]WebSocket heartbeat[/]",
            "[#a6e3a1]Price: BTC $100k @ 0.847[/]",
            "[#a6e3a1]Price: Epstein files @ 0.312[/]",
            "[#f9e2af]Spread widening: 7276...[/]",
            "[#89b4fa]News: 'Bitcoin surges past $99k'[/]",
            "[#89b4fa]Match: 'Bitcoin' detected[/]",
            "[bold #a6e3a1]Signal: BUY $50 Epstein[/]",
        ]

        demo_markets = [
            ("BTC $100k", "7276..."),
            ("Epstein", "8607..."),
            ("49ers vs Colts", "8545..."),
        ]

        events, signals, trades = 0, 0, 0

        try:
            while True:
                await asyncio.sleep(random.uniform(0.8, 2.5))

                log.write(random.choice(messages))
                events += 1
                self.query_one("#events", Label).update(f"Events: {events:,}")

                if random.random() < 0.12:
                    market_name, _ = random.choice(demo_markets)
                    side = random.choice([Side.BUY, Side.SELL])
                    size = random.uniform(25.0, 100.0)
                    price = random.uniform(0.15, 0.85)

                    signals += 1
                    trades += 1

                    self.query_one("#signals", Label).update(f"Signals: {signals:,}")
                    self.query_one("#trades", Label).update(f"Trades: {trades:,}")

                    color = "#a6e3a1" if side == Side.BUY else "#f38ba8"
                    log.write(f"[bold {color}]TRADE: {side.value} {market_name} ${size:.2f} @ {price:.3f}[/]")

                    self._trade_count += 1
                    trade_label = self.query_one("#trade-list", Label)
                    trade_label.update(f"#{self._trade_count} {side.value} {market_name} @ {price:.3f}")
                    trade_label.set_classes("trade-buy" if side == Side.BUY else "trade-sell")

        except asyncio.CancelledError:
            log.write("[#f38ba8]Demo stopped[/]")

    async def _start_live_mode(self, log: RichLog) -> None:
        """Start live mode."""
        header = self.query_one("#global-header", GlobalHeader)

        try:
            self._orchestrator = await self._build_orchestrator(log)
        except Exception as e:
            log.write(f"[bold #f38ba8]Failed: {e}[/]")
            self.notify(f"Failed: {e}", severity="error")
            return

        header.set_connected(True)

        self._tui_callback = TuiCallback(self)
        self._orchestrator.register_callback(self._tui_callback)

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

        threshold_rules = self._load_threshold_rules()
        keyword_rules = self._load_keyword_rules()
        rss_feeds = self._load_rss_feeds()
        discovery_strategies = self._load_discovery_strategies()

        self.query_one("#threshold-rules", Label).update(f"Threshold: {len(threshold_rules)}")
        self.query_one("#keyword-rules", Label).update(f"Keyword: {len(keyword_rules)}")

        log.write(f"[#6c7086]Rules: {len(threshold_rules)} threshold, {len(keyword_rules)} keyword[/]")

        poly_ingester = PolymarketIngester()

        if threshold_rules:
            token_ids = list({rule.token_id for rule in threshold_rules})
            await poly_ingester.subscribe(token_ids)
            log.write(f"[#6c7086]Subscribed: {len(token_ids)} tokens[/]")

        price_parser = PriceThresholdParser(threshold_rules)

        if discovery_strategies:
            log.write("[#6c7086]Discovery...[/]")
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

        ingesters: list[BaseIngester] = [poly_ingester]

        if rss_feeds:
            rss_ingester = RssIngester(poll_interval=60.0)
            await rss_ingester.configure(rss_feeds)
            ingesters.append(rss_ingester)

        parsers: list[BaseParser] = [price_parser]

        if keyword_rules:
            parsers.append(KeywordParser(keyword_rules))

        private_key = None
        if self._active_wallet:
            private_key = self._active_wallet.private_key
            log.write(f"[#a6e3a1]Wallet: {self._active_wallet.short_address}[/]")

        executor = PolymarketExecutor(
            max_position_size=settings.bot.max_position_size,
            private_key=private_key,
        )
        trade_logger = TradeLogger()

        return Orchestrator(
            ingesters=ingesters,
            parsers=parsers,
            executor=executor,
            trade_logger=trade_logger,
        )

    async def _run_orchestrator(self) -> None:
        """Worker for orchestrator."""
        if self._orchestrator is None:
            return

        try:
            await self._orchestrator.start()
        except Exception as e:
            log = self.query_one("#log-panel", RichLog)
            log.write(f"[bold #f38ba8]Error: {e}[/]")

    def add_trade(self, signal: TradeSignal, result: ExecutionResult) -> None:
        """Add trade to display."""
        self._trade_count += 1
        color = "#a6e3a1" if signal.side == Side.BUY else "#f38ba8"

        log = self.query_one("#log-panel", RichLog)
        log.write(f"[bold {color}]TRADE #{self._trade_count}: {signal.side.value} ${signal.size_usdc:.2f} @ {result.filled_price:.3f}[/]")

        trade_label = self.query_one("#trade-list", Label)
        trade_label.update(f"#{self._trade_count} {signal.side.value} @ {result.filled_price:.3f}")
        trade_label.set_classes("trade-buy" if signal.side == Side.BUY else "trade-sell")

    def update_metrics(self, metrics: dict[str, int]) -> None:
        """Update metrics display."""
        self.query_one("#events", Label).update(f"Events: {metrics.get('events_processed', 0):,}")
        self.query_one("#signals", Label).update(f"Signals: {metrics.get('signals_generated', 0):,}")
        self.query_one("#trades", Label).update(f"Trades: {metrics.get('trades_executed', 0):,}")

    def update_position(self, position: Position) -> None:
        """Update position (Phase 7)."""
        pass

    def action_clear_logs(self) -> None:
        """Clear logs."""
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

    def _load_threshold_rules(self) -> list["ThresholdRule"]:
        from src.models import ThresholdRule

        return [
            ThresholdRule(
                token_id="72764351885425491292910818593903116970287593848365163845719951278848564016561",
                trigger_side=Side.BUY,
                threshold=0.95,
                comparison="below",
                size_usdc=2.0,
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
                size_usdc=1.5,
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
                    size_usdc=1.0,
                    cooldown_seconds=300.0,
                ),
                max_markets=5,
            ),
        ]


# Backward compat
SniperApp = AedesApp
