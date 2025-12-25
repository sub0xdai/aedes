"""Price threshold parser implementation."""

from time import time

from loguru import logger

from src.interfaces.parser import BaseParser
from src.models import EventType, MarketEvent, Side, ThresholdRule, TradeSignal


class PriceThresholdParser(BaseParser):
    """Parser that generates signals when price crosses thresholds.

    Evaluates market events against configured threshold rules and
    emits TradeSignal objects when conditions are met.

    Features:
    - Multiple threshold rules per token
    - Cooldown periods to prevent rapid-fire signals
    - Support for both "above" and "below" comparisons
    - Last price tracking for hysteresis
    """

    def __init__(self, rules: list[ThresholdRule]) -> None:
        """Initialize the parser with threshold rules.

        Args:
            rules: List of ThresholdRule configurations.
        """
        self._rules = rules
        # Map token_id -> list of rules for that token
        self._rules_by_token: dict[str, list[ThresholdRule]] = {}
        for rule in rules:
            if rule.token_id not in self._rules_by_token:
                self._rules_by_token[rule.token_id] = []
            self._rules_by_token[rule.token_id].append(rule)

        # Track last trigger time per (token_id, threshold) to enforce cooldowns
        self._last_trigger: dict[tuple[str, float], float] = {}

        # Track last known price per token for hysteresis
        self._last_price: dict[str, float] = {}

        logger.info("Initialized PriceThresholdParser with {} rules", len(rules))

    def evaluate(self, event: MarketEvent) -> TradeSignal | None:
        """Evaluate a market event against threshold rules.

        Args:
            event: The market event to evaluate.

        Returns:
            TradeSignal if a threshold is crossed, None otherwise.
        """
        # Only evaluate price-related market events
        if not event.is_market_event():
            return None

        # token_id is guaranteed to be non-None after is_market_event() check
        token_id = event.token_id
        assert token_id is not None  # Type narrowing for mypy

        # Get rules for this token
        rules = self._rules_by_token.get(token_id, [])
        if not rules:
            return None

        # Determine current price (prefer mid-price, fall back to last trade)
        current_price = self._get_price(event)
        if current_price is None:
            return None

        # Get previous price for this token
        prev_price = self._last_price.get(token_id)

        # Update last known price
        self._last_price[token_id] = current_price

        # Evaluate each rule
        for rule in rules:
            signal = self._evaluate_rule(rule, current_price, prev_price, event)
            if signal is not None:
                return signal

        return None

    def _evaluate_rule(
        self,
        rule: ThresholdRule,
        current_price: float,
        prev_price: float | None,
        event: MarketEvent,
    ) -> TradeSignal | None:
        """Evaluate a single threshold rule.

        Args:
            rule: The threshold rule to evaluate.
            current_price: Current market price.
            prev_price: Previous known price (for crossing detection).
            event: The original market event.

        Returns:
            TradeSignal if threshold is crossed, None otherwise.
        """
        # Check cooldown
        rule_key = (rule.token_id, rule.threshold)
        last_trigger = self._last_trigger.get(rule_key, 0.0)
        if time() - last_trigger < rule.cooldown_seconds:
            return None

        # Check if threshold is crossed
        crossed = False

        if rule.comparison == "above":
            # Trigger when price moves ABOVE threshold
            if prev_price is not None:
                # Crossing detection: was below or at, now above
                crossed = prev_price <= rule.threshold < current_price
            else:
                # First observation: just check if above
                crossed = current_price > rule.threshold

        else:  # comparison == "below"
            # Trigger when price moves BELOW threshold
            if prev_price is not None:
                # Crossing detection: was above or at, now below
                crossed = prev_price >= rule.threshold > current_price
            else:
                # First observation: just check if below
                crossed = current_price < rule.threshold

        if not crossed:
            return None

        # Generate signal
        reason = rule.reason_template.format(
            comparison=rule.comparison,
            threshold=rule.threshold,
            current_price=current_price,
            token_id=rule.token_id,
        )

        # Record trigger time
        self._last_trigger[rule_key] = time()

        logger.info(
            "Threshold triggered | token={} price={:.4f} threshold={:.4f} side={}",
            rule.token_id,
            current_price,
            rule.threshold,
            rule.trigger_side.value,
        )

        return TradeSignal(
            token_id=rule.token_id,
            side=rule.trigger_side,
            size_usdc=rule.size_usdc,
            reason=reason,
        )

    def _get_price(self, event: MarketEvent) -> float | None:
        """Extract price from market event.

        Prefers mid-price from bid/ask, falls back to last trade price.
        """
        # Try mid-price first
        if event.best_bid is not None and event.best_ask is not None:
            return (event.best_bid + event.best_ask) / 2

        # Fall back to last trade price
        if event.last_price is not None:
            return event.last_price

        # Try best ask (for BUY signals)
        if event.best_ask is not None:
            return event.best_ask

        # Try best bid (for SELL signals)
        if event.best_bid is not None:
            return event.best_bid

        return None

    def reset(self) -> None:
        """Reset parser state."""
        self._last_trigger.clear()
        self._last_price.clear()
        logger.info("Parser state reset")

    def add_rule(self, rule: ThresholdRule) -> None:
        """Add a new threshold rule at runtime.

        Args:
            rule: The threshold rule to add.
        """
        self._rules.append(rule)
        if rule.token_id not in self._rules_by_token:
            self._rules_by_token[rule.token_id] = []
        self._rules_by_token[rule.token_id].append(rule)
        logger.info(
            "Added rule | token={} threshold={:.4f} side={}",
            rule.token_id,
            rule.threshold,
            rule.trigger_side.value,
        )

    def has_rule_for_token(self, token_id: str) -> bool:
        """Check if any rule exists for the given token.

        Args:
            token_id: The token ID to check.

        Returns:
            True if at least one rule exists for this token.
        """
        return token_id in self._rules_by_token
