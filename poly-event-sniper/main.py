"""Main entry point for the poly-event-sniper trading bot."""

import argparse
import asyncio
import signal
import sys
from pathlib import Path

from loguru import logger

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
from src.managers.subscription import SubscriptionManager
from src.models import Side, ThresholdRule
from src.orchestrator import Orchestrator
from src.parsers.keyword import KeywordParser, KeywordRule
from src.parsers.threshold import PriceThresholdParser
from src.persistence import TradeLogger


def setup_logging() -> None:
    """Configure loguru logging."""
    logger.remove()  # Remove default handler
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO",
    )
    logger.add(
        "logs/sniper_{time}.log",
        rotation="100 MB",
        retention="7 days",
        level="DEBUG",
    )


def load_threshold_rules() -> list[ThresholdRule]:
    """Load threshold rules for price-based trading.

    In production, this would load from a config file or database.
    """
    return [
        # Strategy 1: Bitcoin $100k Dip Buy
        # Market: "Will Bitcoin reach $100,000 by December 31, 2025?"
        # Logic: Buy YES if probability dips below 95% (high confidence long-term)
        ThresholdRule(
            token_id="72764351885425491292910818593903116970287593848365163845719951278848564016561",
            trigger_side=Side.BUY,
            threshold=0.95,
            comparison="below",
            size_usdc=2.0,  # $2 for testing
            reason_template="BTC $100k dip buy: probability dropped below {threshold}",
            cooldown_seconds=300.0,  # 5 min cooldown to avoid rapid-fire buys
        ),
    ]


def load_keyword_rules() -> list[KeywordRule]:
    """Load keyword rules for news/social-based trading.

    In production, this would load from a config file or database.
    """
    return [
        # Strategy 2: Epstein Files Release
        # Market: "Will Trump release more Epstein files by December 22?"
        # Logic: Buy YES if news mentions Epstein + Release/Trump
        KeywordRule(
            keyword="Epstein",
            token_id="86076435751570733286369126634541849471627178793773765844822295389135259614946",
            trigger_side=Side.BUY,
            size_usdc=1.5,  # $1.50 for testing
            reason_template="Epstein news detected: {keyword}",
            cooldown_seconds=600.0,  # 10 min cooldown
        ),
        KeywordRule(
            keyword="Trump release",
            token_id="86076435751570733286369126634541849471627178793773765844822295389135259614946",
            trigger_side=Side.BUY,
            size_usdc=1.5,  # $1.50 for testing
            reason_template="Trump release news detected: {keyword}",
            cooldown_seconds=600.0,
        ),
        # Strategy 3: NFL 49ers vs Colts
        # Market: "49ers vs Colts Winner"
        # Logic: Buy 49ers shares on touchdown/score news
        KeywordRule(
            keyword="49ers touchdown",
            token_id="85455113016431049626358535958294679323212801434936446670950500092521192392446",
            trigger_side=Side.BUY,
            size_usdc=1.0,  # $1 for testing
            reason_template="49ers scored: {keyword}",
            cooldown_seconds=120.0,  # 2 min cooldown (fast-moving game)
        ),
        KeywordRule(
            keyword="San Francisco score",
            token_id="85455113016431049626358535958294679323212801434936446670950500092521192392446",
            trigger_side=Side.BUY,
            size_usdc=1.0,  # $1 for testing
            reason_template="49ers scored: {keyword}",
            cooldown_seconds=120.0,
        ),
    ]


def load_rss_feeds() -> list[str]:
    """Load RSS feed URLs for news monitoring.

    In production, this would load from a config file or database.
    """
    return [
        # Crypto feeds (Strategy 1: Bitcoin)
        "https://cointelegraph.com/rss",
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        # Politics feeds (Strategy 2: Epstein/Trump)
        "https://feeds.nbcnews.com/nbcnews/public/politics",
        "https://rss.politico.com/politics-news.xml",
        # Sports feeds (Strategy 3: NFL/49ers)
        "https://www.espn.com/espn/rss/nfl/news",
        "https://api.foxsports.com/v1/rss?partnerKey=MB0Wehpmuj2lUhuRhQaafhBjAJqaPU244mlTDK1i&tag=nfl",
    ]


def load_discovery_strategies() -> list[DiscoveryStrategy]:
    """Load discovery strategies for automatic market discovery.

    In production, this would load from a config file or database.
    Set to empty list to disable discovery.
    """
    return [
        # Strategy: High Volume Crypto Dips
        # Find crypto markets with > $50k volume, buy if price drops below 0.20
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
                size_usdc=1.5,  # $1.50 for testing
                cooldown_seconds=300.0,
            ),
            max_markets=5,
        ),
        # Strategy: High Volume Politics Sells
        # Find politics markets with > $100k volume, sell if price rises above 0.80
        DiscoveryStrategy(
            name="politics_high_prob",
            criteria=MarketCriteria(
                tags=["politics"],
                min_volume=100000.0,
                min_liquidity=20000.0,
                active_only=True,
            ),
            rule_template=RuleTemplate(
                trigger_side="SELL",
                threshold=0.80,
                comparison="above",
                size_usdc=1.5,  # $1.50 for testing
                cooldown_seconds=600.0,
            ),
            max_markets=3,
        ),
    ]


async def main() -> None:
    """Run the trading bot."""
    setup_logging()
    logger.info("Starting poly-event-sniper")

    settings = get_settings()
    logger.info("Dry run mode: {}", settings.bot.dry_run)

    # ==========================================================================
    # Phase 1: Load Static Configuration
    # ==========================================================================
    threshold_rules = load_threshold_rules()
    keyword_rules = load_keyword_rules()
    rss_feeds = load_rss_feeds()
    discovery_strategies = load_discovery_strategies()

    logger.info(
        "Loaded {} threshold rules, {} keyword rules, {} RSS feeds, {} discovery strategies",
        len(threshold_rules),
        len(keyword_rules),
        len(rss_feeds),
        len(discovery_strategies),
    )

    # ==========================================================================
    # Phase 2: Initialize Core Components
    # ==========================================================================

    # Market data ingester (always needed for threshold rules or discovery)
    poly_ingester = PolymarketIngester()

    # Subscribe to static threshold rule tokens
    if threshold_rules:
        token_ids = list({rule.token_id for rule in threshold_rules})
        await poly_ingester.subscribe(token_ids)
        logger.info("Pre-subscribed to {} static tokens", len(token_ids))

    # Initialize price parser with static rules
    price_parser = PriceThresholdParser(threshold_rules)

    # ==========================================================================
    # Phase 3: Startup Discovery (Dynamic Market Subscription)
    # ==========================================================================
    if discovery_strategies:
        logger.info("Starting market discovery...")
        try:
            async with GammaClient() as gamma_client:
                manager = SubscriptionManager(
                    client=gamma_client,
                    ingester=poly_ingester,
                    parser=price_parser,
                    global_limit=50,
                )
                discovered_count = await manager.execute_strategies(discovery_strategies)
                logger.info("Discovery complete: {} markets auto-subscribed", discovered_count)
        except Exception as e:
            logger.error("Discovery failed: {} - continuing with static rules", str(e))

    # ==========================================================================
    # Phase 4: Assemble Ingesters and Parsers
    # ==========================================================================
    ingesters: list[BaseIngester] = [poly_ingester]

    # RSS ingester (for news-based trading)
    if rss_feeds:
        rss_ingester = RssIngester(poll_interval=60.0)
        await rss_ingester.configure(rss_feeds)
        ingesters.append(rss_ingester)

    # Assemble parsers
    parsers: list[BaseParser] = [price_parser]

    if keyword_rules:
        keyword_parser = KeywordParser(keyword_rules)
        parsers.append(keyword_parser)

    # Verify we have at least one parser with rules
    total_rules = len(threshold_rules) + len(price_parser._rules_by_token)
    if total_rules == 0 and not keyword_rules:
        logger.error("No rules configured (static or discovered). Exiting.")
        return

    # ==========================================================================
    # Phase 5: Initialize Executor and Orchestrator
    # ==========================================================================
    executor = PolymarketExecutor(max_position_size=settings.bot.max_position_size)
    trade_logger = TradeLogger()

    orchestrator = Orchestrator(
        ingesters=ingesters,
        parsers=parsers,
        executor=executor,
        trade_logger=trade_logger,
    )

    logger.info(
        "Orchestrator ready | ingesters={} parsers={} subscribed_tokens={}",
        len(ingesters),
        len(parsers),
        len(poly_ingester.get_subscribed_tokens()),
    )

    # Setup graceful shutdown
    shutdown_event = asyncio.Event()

    def shutdown_handler(sig: signal.Signals) -> None:
        logger.info("Received signal {}, initiating shutdown...", sig.name)
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_handler, sig)

    # Run orchestrator with shutdown handling
    try:
        # Start in background task so we can monitor shutdown_event
        orchestrator_task = asyncio.create_task(orchestrator.start())

        # Wait for either orchestrator to finish or shutdown signal
        done, pending = await asyncio.wait(
            [orchestrator_task, asyncio.create_task(shutdown_event.wait())],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # If shutdown event triggered, cancel orchestrator
        if shutdown_event.is_set() and orchestrator_task in pending:
            orchestrator_task.cancel()
            try:
                await orchestrator_task
            except asyncio.CancelledError:
                pass

    except Exception as e:
        logger.error("Fatal error: {}", str(e), exc_info=True)
    finally:
        await orchestrator.stop()
        logger.info("Shutdown complete")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Poly-Event Sniper - Polymarket Trading Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--tui",
        action="store_true",
        help="Launch with Terminal User Interface (default: headless)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run TUI in demo mode (no real connections, fake data)",
    )
    return parser.parse_args()


async def main_tui(demo: bool = False) -> None:
    """Run the bot with TUI.

    Args:
        demo: If True, run in demo mode with fake data (no real connections).
    """
    from src.tui import AedesApp

    app = AedesApp(demo_mode=demo)
    await app.run_async()


if __name__ == "__main__":
    # Create logs directory if it doesn't exist
    Path("logs").mkdir(exist_ok=True)

    args = parse_args()

    if args.tui or args.demo:
        # Run with TUI (--demo implies --tui)
        asyncio.run(main_tui(demo=args.demo))
    else:
        # Run headless
        asyncio.run(main())
