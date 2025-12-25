"""Tests for SubscriptionManager - Phase 5b."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.discovery import (
    DiscoveryResult,
    DiscoveryStrategy,
    GammaClient,
    MarketCriteria,
    RuleTemplate,
)
from src.managers.subscription import SubscriptionManager
from src.models import Side, ThresholdRule


# =============================================================================
# Mock Classes
# =============================================================================


class MockIngester:
    """Mock ingester for testing subscription."""

    def __init__(self) -> None:
        self._subscribed_tokens: set[str] = set()

    async def subscribe(self, token_ids: list[str]) -> None:
        self._subscribed_tokens.update(token_ids)

    def get_subscribed_tokens(self) -> set[str]:
        return self._subscribed_tokens.copy()


class MockParser:
    """Mock parser for testing rule addition."""

    def __init__(self) -> None:
        self._rules_by_token: dict[str, list[ThresholdRule]] = {}

    def add_rule(self, rule: ThresholdRule) -> None:
        if rule.token_id not in self._rules_by_token:
            self._rules_by_token[rule.token_id] = []
        self._rules_by_token[rule.token_id].append(rule)

    def has_rule_for_token(self, token_id: str) -> bool:
        return token_id in self._rules_by_token


class MockGammaClient:
    """Mock GammaClient for testing discovery."""

    def __init__(self, results: list[DiscoveryResult]) -> None:
        self._results = results

    async def discover(
        self, criteria: MarketCriteria, limit: int | None = None
    ) -> list[DiscoveryResult]:
        if limit:
            return self._results[:limit]
        return self._results

    async def __aenter__(self) -> "MockGammaClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_results() -> list[DiscoveryResult]:
    """Create sample discovery results."""
    return [
        DiscoveryResult(
            market_id="market_1",
            token_id="token_1",
            title="Will BTC hit $100k?",
            volume=50000.0,
            tags=["crypto"],
        ),
        DiscoveryResult(
            market_id="market_2",
            token_id="token_2",
            title="Will ETH hit $5k?",
            volume=30000.0,
            tags=["crypto"],
        ),
        DiscoveryResult(
            market_id="market_3",
            token_id="token_3",
            title="Will Trump win?",
            volume=100000.0,
            tags=["politics"],
        ),
    ]


@pytest.fixture
def sample_strategy() -> DiscoveryStrategy:
    """Create sample discovery strategy."""
    return DiscoveryStrategy(
        name="crypto_dips",
        criteria=MarketCriteria(tags=["crypto"], min_volume=10000.0),
        rule_template=RuleTemplate(
            trigger_side="BUY",
            threshold=0.25,
            comparison="below",
            size_usdc=50.0,
        ),
        max_markets=10,
    )


# =============================================================================
# SubscriptionManager Initialization Tests
# =============================================================================


class TestSubscriptionManagerInit:
    """Tests for SubscriptionManager initialization."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default global limit."""
        client = MockGammaClient([])
        ingester = MockIngester()
        parser = MockParser()

        manager = SubscriptionManager(client, ingester, parser)

        assert manager._global_limit == 50

    def test_init_with_custom_limit(self) -> None:
        """Test initialization with custom global limit."""
        client = MockGammaClient([])
        ingester = MockIngester()
        parser = MockParser()

        manager = SubscriptionManager(client, ingester, parser, global_limit=25)

        assert manager._global_limit == 25


# =============================================================================
# Strategy Execution Tests
# =============================================================================


class TestSubscriptionManagerExecute:
    """Tests for execute_strategies method."""

    @pytest.mark.asyncio
    async def test_execute_single_strategy(
        self, sample_results: list[DiscoveryResult], sample_strategy: DiscoveryStrategy
    ) -> None:
        """Test executing a single strategy."""
        # Only return first 2 (crypto) results
        crypto_results = [r for r in sample_results if "crypto" in r.tags]
        client = MockGammaClient(crypto_results)
        ingester = MockIngester()
        parser = MockParser()

        manager = SubscriptionManager(client, ingester, parser)
        count = await manager.execute_strategies([sample_strategy])

        assert count == 2
        assert "token_1" in ingester.get_subscribed_tokens()
        assert "token_2" in ingester.get_subscribed_tokens()
        assert parser.has_rule_for_token("token_1")
        assert parser.has_rule_for_token("token_2")

    @pytest.mark.asyncio
    async def test_execute_respects_max_markets(
        self, sample_results: list[DiscoveryResult]
    ) -> None:
        """Test that max_markets limit is respected."""
        client = MockGammaClient(sample_results)
        ingester = MockIngester()
        parser = MockParser()

        strategy = DiscoveryStrategy(
            name="limited",
            criteria=MarketCriteria(),
            rule_template=RuleTemplate(
                trigger_side="BUY",
                threshold=0.30,
                comparison="below",
                size_usdc=25.0,
            ),
            max_markets=1,  # Only allow 1 market
        )

        manager = SubscriptionManager(client, ingester, parser)
        count = await manager.execute_strategies([strategy])

        assert count == 1
        assert len(ingester.get_subscribed_tokens()) == 1

    @pytest.mark.asyncio
    async def test_execute_respects_global_limit(
        self, sample_results: list[DiscoveryResult], sample_strategy: DiscoveryStrategy
    ) -> None:
        """Test that global limit is respected across strategies."""
        client = MockGammaClient(sample_results)
        ingester = MockIngester()
        parser = MockParser()

        manager = SubscriptionManager(client, ingester, parser, global_limit=2)
        count = await manager.execute_strategies([sample_strategy])

        assert count == 2
        assert len(ingester.get_subscribed_tokens()) == 2


# =============================================================================
# Deduplication Tests
# =============================================================================


class TestSubscriptionManagerDeduplication:
    """Tests for deduplication logic."""

    @pytest.mark.asyncio
    async def test_skips_already_subscribed_tokens(
        self, sample_results: list[DiscoveryResult], sample_strategy: DiscoveryStrategy
    ) -> None:
        """Test that already subscribed tokens are skipped."""
        client = MockGammaClient(sample_results[:2])
        ingester = MockIngester()
        parser = MockParser()

        # Pre-subscribe token_1
        await ingester.subscribe(["token_1"])

        manager = SubscriptionManager(client, ingester, parser)
        count = await manager.execute_strategies([sample_strategy])

        # Only token_2 should be added
        assert count == 1
        assert parser.has_rule_for_token("token_2")
        assert not parser.has_rule_for_token("token_1")

    @pytest.mark.asyncio
    async def test_skips_tokens_with_existing_rules(
        self, sample_results: list[DiscoveryResult], sample_strategy: DiscoveryStrategy
    ) -> None:
        """Test that tokens with existing rules are skipped."""
        client = MockGammaClient(sample_results[:2])
        ingester = MockIngester()
        parser = MockParser()

        # Pre-add rule for token_1
        existing_rule = ThresholdRule(
            token_id="token_1",
            trigger_side=Side.SELL,
            threshold=0.80,
            comparison="above",
            size_usdc=100.0,
        )
        parser.add_rule(existing_rule)

        manager = SubscriptionManager(client, ingester, parser)
        count = await manager.execute_strategies([sample_strategy])

        # Only token_2 should be added
        assert count == 1
        assert len(parser._rules_by_token.get("token_1", [])) == 1  # Still only 1 rule

    @pytest.mark.asyncio
    async def test_no_duplicates_across_strategies(
        self, sample_results: list[DiscoveryResult]
    ) -> None:
        """Test that same market isn't added twice by different strategies."""
        # Both strategies will match token_1
        client = MockGammaClient(sample_results[:1])
        ingester = MockIngester()
        parser = MockParser()

        strategy1 = DiscoveryStrategy(
            name="strategy1",
            criteria=MarketCriteria(tags=["crypto"]),
            rule_template=RuleTemplate(
                trigger_side="BUY",
                threshold=0.25,
                comparison="below",
                size_usdc=50.0,
            ),
        )
        strategy2 = DiscoveryStrategy(
            name="strategy2",
            criteria=MarketCriteria(tags=["crypto"]),
            rule_template=RuleTemplate(
                trigger_side="SELL",
                threshold=0.75,
                comparison="above",
                size_usdc=50.0,
            ),
        )

        manager = SubscriptionManager(client, ingester, parser)
        count = await manager.execute_strategies([strategy1, strategy2])

        # Token should only be added once (by first strategy)
        assert count == 1
        assert len(parser._rules_by_token.get("token_1", [])) == 1


# =============================================================================
# Rule Generation Tests
# =============================================================================


class TestSubscriptionManagerRuleGeneration:
    """Tests for rule generation from templates."""

    @pytest.mark.asyncio
    async def test_generates_correct_rule(
        self, sample_results: list[DiscoveryResult]
    ) -> None:
        """Test that generated rules have correct values."""
        client = MockGammaClient(sample_results[:1])
        ingester = MockIngester()
        parser = MockParser()

        strategy = DiscoveryStrategy(
            name="test",
            criteria=MarketCriteria(),
            rule_template=RuleTemplate(
                trigger_side="BUY",
                threshold=0.30,
                comparison="below",
                size_usdc=75.0,
                cooldown_seconds=120.0,
            ),
        )

        manager = SubscriptionManager(client, ingester, parser)
        await manager.execute_strategies([strategy])

        # Check generated rule
        rules = parser._rules_by_token.get("token_1", [])
        assert len(rules) == 1
        rule = rules[0]
        assert rule.token_id == "token_1"
        assert rule.trigger_side == Side.BUY
        assert rule.threshold == 0.30
        assert rule.comparison == "below"
        assert rule.size_usdc == 75.0
        assert rule.cooldown_seconds == 120.0

    @pytest.mark.asyncio
    async def test_reason_template_includes_title(
        self, sample_results: list[DiscoveryResult]
    ) -> None:
        """Test that reason template includes market title."""
        client = MockGammaClient(sample_results[:1])
        ingester = MockIngester()
        parser = MockParser()

        strategy = DiscoveryStrategy(
            name="test",
            criteria=MarketCriteria(),
            rule_template=RuleTemplate(
                trigger_side="BUY",
                threshold=0.25,
                comparison="below",
                size_usdc=50.0,
            ),
        )

        manager = SubscriptionManager(client, ingester, parser)
        await manager.execute_strategies([strategy])

        rule = parser._rules_by_token["token_1"][0]
        assert "BTC" in rule.reason_template or "100k" in rule.reason_template


# =============================================================================
# Atomicity Tests
# =============================================================================


class TestSubscriptionManagerAtomicity:
    """Tests for atomic subscription + rule creation."""

    @pytest.mark.asyncio
    async def test_subscribe_and_rule_both_succeed(
        self, sample_results: list[DiscoveryResult], sample_strategy: DiscoveryStrategy
    ) -> None:
        """Test that both subscription and rule are added together."""
        client = MockGammaClient(sample_results[:1])
        ingester = MockIngester()
        parser = MockParser()

        manager = SubscriptionManager(client, ingester, parser)
        await manager.execute_strategies([sample_strategy])

        # Both should succeed
        assert "token_1" in ingester.get_subscribed_tokens()
        assert parser.has_rule_for_token("token_1")

    @pytest.mark.asyncio
    async def test_subscription_failure_skips_rule(
        self, sample_results: list[DiscoveryResult], sample_strategy: DiscoveryStrategy
    ) -> None:
        """Test that rule is not added if subscription fails."""
        client = MockGammaClient(sample_results[:1])
        ingester = MockIngester()
        parser = MockParser()

        # Make subscribe raise an exception
        async def failing_subscribe(token_ids: list[str]) -> None:
            raise RuntimeError("Subscription failed")

        ingester.subscribe = failing_subscribe  # type: ignore[method-assign]

        manager = SubscriptionManager(client, ingester, parser)
        count = await manager.execute_strategies([sample_strategy])

        # Neither should be added
        assert count == 0
        assert not parser.has_rule_for_token("token_1")


# =============================================================================
# Empty/Edge Case Tests
# =============================================================================


class TestSubscriptionManagerEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_empty_strategies_list(self) -> None:
        """Test with no strategies."""
        client = MockGammaClient([])
        ingester = MockIngester()
        parser = MockParser()

        manager = SubscriptionManager(client, ingester, parser)
        count = await manager.execute_strategies([])

        assert count == 0

    @pytest.mark.asyncio
    async def test_no_discovery_results(
        self, sample_strategy: DiscoveryStrategy
    ) -> None:
        """Test when discovery returns no results."""
        client = MockGammaClient([])
        ingester = MockIngester()
        parser = MockParser()

        manager = SubscriptionManager(client, ingester, parser)
        count = await manager.execute_strategies([sample_strategy])

        assert count == 0
        assert len(ingester.get_subscribed_tokens()) == 0

    @pytest.mark.asyncio
    async def test_multiple_strategies(
        self, sample_results: list[DiscoveryResult]
    ) -> None:
        """Test executing multiple strategies."""
        # Strategy 1 matches crypto, Strategy 2 matches politics
        crypto_results = [r for r in sample_results if "crypto" in r.tags]
        politics_results = [r for r in sample_results if "politics" in r.tags]

        # We need to mock differently for each strategy call
        call_count = 0
        results_by_call = [crypto_results, politics_results]

        async def mock_discover(
            criteria: MarketCriteria, limit: int | None = None
        ) -> list[DiscoveryResult]:
            nonlocal call_count
            result = results_by_call[call_count] if call_count < len(results_by_call) else []
            call_count += 1
            if limit:
                return result[:limit]
            return result

        client = MockGammaClient([])
        client.discover = mock_discover  # type: ignore[method-assign]
        ingester = MockIngester()
        parser = MockParser()

        strategy1 = DiscoveryStrategy(
            name="crypto",
            criteria=MarketCriteria(tags=["crypto"]),
            rule_template=RuleTemplate(
                trigger_side="BUY",
                threshold=0.25,
                comparison="below",
                size_usdc=50.0,
            ),
        )
        strategy2 = DiscoveryStrategy(
            name="politics",
            criteria=MarketCriteria(tags=["politics"]),
            rule_template=RuleTemplate(
                trigger_side="SELL",
                threshold=0.75,
                comparison="above",
                size_usdc=100.0,
            ),
        )

        manager = SubscriptionManager(client, ingester, parser)
        count = await manager.execute_strategies([strategy1, strategy2])

        assert count == 3  # 2 crypto + 1 politics
        assert len(ingester.get_subscribed_tokens()) == 3
