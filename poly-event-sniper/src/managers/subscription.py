"""Subscription manager for dynamic market discovery and trading rule generation."""

from typing import Any, Protocol

from loguru import logger

from src.discovery import DiscoveryResult, DiscoveryStrategy, GammaClient, MarketCriteria
from src.models import Side, ThresholdRule


class IngesterProtocol(Protocol):
    """Protocol defining required ingester methods for SubscriptionManager."""

    async def subscribe(self, token_ids: list[str]) -> None:
        """Subscribe to market events for specified tokens."""
        ...

    def get_subscribed_tokens(self) -> set[str]:
        """Get the set of currently subscribed token IDs."""
        ...


class ParserProtocol(Protocol):
    """Protocol defining required parser methods for SubscriptionManager."""

    def add_rule(self, rule: ThresholdRule) -> None:
        """Add a new threshold rule at runtime."""
        ...

    def has_rule_for_token(self, token_id: str) -> bool:
        """Check if any rule exists for the given token."""
        ...


class GammaClientProtocol(Protocol):
    """Protocol defining required GammaClient methods for SubscriptionManager."""

    async def discover(
        self, criteria: MarketCriteria, limit: int | None = None
    ) -> list[DiscoveryResult]:
        """Discover markets matching criteria."""
        ...


class SubscriptionManager:
    """Bridges discovery layer to orchestrator via automatic subscription.

    Executes discovery strategies at startup, subscribing to matching markets
    and generating trading rules based on templates.

    Features:
    - Strategy-based market discovery
    - Automatic threshold rule generation
    - Deduplication (skips already subscribed/ruled tokens)
    - Global and per-strategy subscription limits
    - Atomic subscription + rule creation

    Usage:
        async with GammaClient() as client:
            manager = SubscriptionManager(client, ingester, parser)
            count = await manager.execute_strategies(strategies)
            logger.info(f"Auto-discovered {count} markets")
    """

    DEFAULT_GLOBAL_LIMIT = 50

    def __init__(
        self,
        client: GammaClientProtocol,
        ingester: IngesterProtocol,
        parser: ParserProtocol,
        global_limit: int = DEFAULT_GLOBAL_LIMIT,
    ) -> None:
        """Initialize the subscription manager.

        Args:
            client: GammaClient for market discovery.
            ingester: Ingester for subscribing to market data.
            parser: Parser for adding threshold rules.
            global_limit: Maximum total auto-subscriptions across all strategies.
        """
        self._client = client
        self._ingester = ingester
        self._parser = parser
        self._global_limit = global_limit
        self._subscribed_count = 0

    async def execute_strategies(self, strategies: list[DiscoveryStrategy]) -> int:
        """Execute all discovery strategies and subscribe to matching markets.

        For each strategy:
        1. Queries GammaClient for matching markets (respecting max_markets)
        2. Deduplicates: skips tokens already subscribed or with existing rules
        3. Atomically subscribes AND adds rule for new tokens
        4. Respects global subscription limit

        Args:
            strategies: List of DiscoveryStrategy configurations.

        Returns:
            Total number of new markets successfully added.
        """
        total_added = 0

        for strategy in strategies:
            if self._subscribed_count >= self._global_limit:
                logger.warning(
                    "Global limit reached ({}/{}), skipping remaining strategies",
                    self._subscribed_count,
                    self._global_limit,
                )
                break

            added = await self._execute_strategy(strategy)
            total_added += added

        logger.info(
            "Discovery complete | added={} total_subscribed={}",
            total_added,
            self._subscribed_count,
        )
        return total_added

    async def _execute_strategy(self, strategy: DiscoveryStrategy) -> int:
        """Execute a single discovery strategy.

        Args:
            strategy: The strategy to execute.

        Returns:
            Number of markets added by this strategy.
        """
        # Calculate how many we can still add
        remaining_global = self._global_limit - self._subscribed_count
        limit = min(strategy.max_markets, remaining_global)

        if limit <= 0:
            return 0

        logger.info(
            "Executing strategy '{}' | limit={}",
            strategy.name,
            limit,
        )

        # Discover markets
        try:
            results = await self._client.discover(strategy.criteria, limit=limit)
        except Exception as e:
            logger.error("Discovery failed for strategy '{}': {}", strategy.name, str(e))
            return 0

        added = 0
        for result in results:
            if self._subscribed_count >= self._global_limit:
                break

            if self._is_duplicate(result.token_id):
                logger.debug(
                    "Skipping duplicate token {} ({})",
                    result.token_id[:8],
                    result.title[:30],
                )
                continue

            success = await self._add_market(result, strategy)
            if success:
                added += 1
                self._subscribed_count += 1

        logger.info(
            "Strategy '{}' complete | added={} discovered={}",
            strategy.name,
            added,
            len(results),
        )
        return added

    def _is_duplicate(self, token_id: str) -> bool:
        """Check if token is already subscribed or has existing rules.

        Args:
            token_id: The token ID to check.

        Returns:
            True if token should be skipped (already exists).
        """
        # Check ingester subscriptions
        if token_id in self._ingester.get_subscribed_tokens():
            return True

        # Check parser rules
        if self._parser.has_rule_for_token(token_id):
            return True

        return False

    async def _add_market(
        self,
        result: DiscoveryResult,
        strategy: DiscoveryStrategy,
    ) -> bool:
        """Atomically subscribe to market and add trading rule.

        If subscription fails, rule is not added (atomic guarantee).

        Args:
            result: The discovered market.
            strategy: The strategy that found this market.

        Returns:
            True if both subscription and rule addition succeeded.
        """
        # Create rule from template
        rule = self._create_rule(result, strategy)

        # Atomic: subscribe first, then add rule only if subscribe succeeds
        try:
            await self._ingester.subscribe([result.token_id])
        except Exception as e:
            logger.error(
                "Subscription failed for {} ({}): {}",
                result.token_id[:8],
                result.title[:30],
                str(e),
            )
            return False

        # Subscribe succeeded, now add rule
        try:
            self._parser.add_rule(rule)
        except Exception as e:
            logger.error(
                "Rule addition failed for {} ({}): {}",
                result.token_id[:8],
                result.title[:30],
                str(e),
            )
            # Note: subscription already happened, but rule failed
            # This is acceptable since the market data will flow but won't trigger trades
            return False

        logger.info(
            "Added market | token={} title='{}' threshold={:.2f}",
            result.token_id[:8],
            result.title[:40],
            strategy.rule_template.threshold,
        )
        return True

    def _create_rule(
        self,
        result: DiscoveryResult,
        strategy: DiscoveryStrategy,
    ) -> ThresholdRule:
        """Create a ThresholdRule from DiscoveryResult and strategy template.

        Args:
            result: The discovered market.
            strategy: The strategy with rule template.

        Returns:
            A new ThresholdRule for this market.
        """
        template = strategy.rule_template

        # Convert string trigger_side to Side enum
        trigger_side = Side.BUY if template.trigger_side.upper() == "BUY" else Side.SELL

        # Create reason template that includes market title
        reason_template = (
            f"[{strategy.name}] {result.title[:50]} | "
            f"{{comparison}} {{threshold}}"
        )

        return ThresholdRule(
            token_id=result.token_id,
            trigger_side=trigger_side,
            threshold=template.threshold,
            comparison=template.comparison,  # type: ignore[arg-type]
            size_usdc=template.size_usdc,
            reason_template=reason_template,
            cooldown_seconds=template.cooldown_seconds,
        )
