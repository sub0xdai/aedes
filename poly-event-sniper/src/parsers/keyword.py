"""Keyword-based parser for news-to-trade signal generation."""

from time import time

from loguru import logger
from pydantic import BaseModel, Field

from src.interfaces.parser import BaseParser
from src.models import EventType, MarketEvent, Side, TradeSignal


class KeywordRule(BaseModel):
    """Rule defining a keyword trigger for trading.

    Immutable configuration for keyword-based signal generation.
    """

    model_config = {"frozen": True}

    keyword: str = Field(..., description="Keyword or phrase to match")
    token_id: str = Field(..., description="Token to trade when triggered")
    trigger_side: Side = Field(..., description="Trade direction when triggered")
    size_usdc: float = Field(..., gt=0, description="Order size in USDC")
    reason_template: str = Field(
        default="Keyword '{keyword}' detected",
        description="Template for trade reason",
    )
    case_sensitive: bool = Field(
        default=False,
        description="Whether keyword matching is case-sensitive",
    )
    cooldown_seconds: float = Field(
        default=60.0,
        ge=0,
        description="Minimum time between triggers for this keyword",
    )


class KeywordParser(BaseParser):
    """Parser that generates signals when keywords are detected in event content.

    Evaluates NEWS and SOCIAL events against configured keyword rules and
    emits TradeSignal objects when matches are found.

    Features:
    - Multiple keyword rules
    - Case-sensitive or case-insensitive matching
    - Cooldown periods to prevent rapid-fire signals
    - First-match-wins semantics
    """

    def __init__(self, rules: list[KeywordRule]) -> None:
        """Initialize the parser with keyword rules.

        Args:
            rules: List of KeywordRule configurations.
        """
        self._rules = rules

        # Track last trigger time per keyword to enforce cooldowns
        self._last_trigger: dict[str, float] = {}

        logger.info("Initialized KeywordParser with {} rules", len(rules))

    def evaluate(self, event: MarketEvent) -> TradeSignal | None:
        """Evaluate an event against keyword rules.

        Args:
            event: The event to evaluate.

        Returns:
            TradeSignal if a keyword is matched, None otherwise.
        """
        # Only evaluate external events (NEWS, SOCIAL)
        if event.event_type not in (EventType.NEWS, EventType.SOCIAL):
            return None

        # No content to evaluate
        if event.content is None:
            return None

        # Evaluate each rule
        for rule in self._rules:
            signal = self._evaluate_rule(rule, event)
            if signal is not None:
                return signal

        return None

    def _evaluate_rule(
        self,
        rule: KeywordRule,
        event: MarketEvent,
    ) -> TradeSignal | None:
        """Evaluate a single keyword rule against event content.

        Args:
            rule: The keyword rule to evaluate.
            event: The event to check.

        Returns:
            TradeSignal if keyword matches and cooldown passed, None otherwise.
        """
        # Check cooldown
        last_trigger = self._last_trigger.get(rule.keyword, 0.0)
        if time() - last_trigger < rule.cooldown_seconds:
            return None

        # Prepare content and keyword for matching
        content = event.content
        keyword = rule.keyword

        if content is None:
            return None

        if not rule.case_sensitive:
            content = content.lower()
            keyword = keyword.lower()

        # Check if keyword is in content
        if keyword not in content:
            return None

        # Match found - generate signal
        reason = rule.reason_template.format(
            keyword=rule.keyword,
            source=event.source or "unknown",
            content=event.content[:50] if event.content else "",
        )

        # Record trigger time
        self._last_trigger[rule.keyword] = time()

        logger.info(
            "Keyword triggered | keyword='{}' token={} side={} source={}",
            rule.keyword,
            rule.token_id,
            rule.trigger_side.value,
            event.source,
        )

        return TradeSignal(
            token_id=rule.token_id,
            side=rule.trigger_side,
            size_usdc=rule.size_usdc,
            reason=reason,
        )

    def reset(self) -> None:
        """Reset parser state (clears cooldown tracking)."""
        self._last_trigger.clear()
        logger.info("KeywordParser state reset")
