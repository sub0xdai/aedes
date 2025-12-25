"""Domain models for the poly-event-sniper trading system."""

import uuid
from enum import Enum
from time import time
from typing import Any, Literal

from pydantic import BaseModel, Field


class Side(str, Enum):
    """Trade direction."""

    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    """Order execution status."""

    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


# =============================================================================
# Phase 7 Enums
# =============================================================================


class PositionSide(str, Enum):
    """Position direction."""

    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class OrderType(str, Enum):
    """Order type for execution."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    FOK = "FOK"


class TimeInForce(str, Enum):
    """Order time-in-force."""

    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"


class TradeSignal(BaseModel):
    """Signal indicating a trade opportunity.

    Immutable data structure passed between ingestion and execution layers.
    """

    model_config = {"frozen": True}

    token_id: str = Field(..., description="Polymarket token ID to trade")
    side: Side = Field(..., description="Trade direction (BUY/SELL)")
    size_usdc: float = Field(..., gt=0, description="Position size in USDC")
    reason: str = Field(..., description="Human-readable reason for the trade")
    timestamp: float = Field(default_factory=time, description="Signal generation time")


class ExecutionResult(BaseModel):
    """Result of an order execution attempt.

    Immutable data structure returned from the execution layer.
    """

    model_config = {"frozen": True}

    order_id: str = Field(..., description="Exchange-assigned order ID")
    status: OrderStatus = Field(..., description="Final order status")
    filled_price: float = Field(..., ge=0, description="Average fill price (0 if unfilled)")
    filled_size: float = Field(default=0.0, ge=0, description="Number of shares filled")
    fees_paid: float = Field(default=0.0, ge=0, description="Transaction fees in USDC")
    execution_timestamp: float = Field(
        default_factory=time, description="When the order completed"
    )
    error_message: str | None = Field(
        default=None, description="Failure details for debugging"
    )


# =============================================================================
# Ingestion Layer Models
# =============================================================================


class EventType(str, Enum):
    """Type of event from ingestion layer."""

    # Market data events
    PRICE_CHANGE = "PRICE_CHANGE"
    BOOK_UPDATE = "BOOK_UPDATE"
    LAST_TRADE = "LAST_TRADE"
    TICK_SIZE_CHANGE = "TICK_SIZE_CHANGE"

    # External events
    NEWS = "NEWS"
    SOCIAL = "SOCIAL"


class MarketEvent(BaseModel):
    """Raw event from ingestion layer.

    Immutable data structure yielded by ingesters.
    Supports both market data events (with token_id) and external events (with content).
    """

    model_config = {"frozen": True}

    event_type: EventType = Field(..., description="Type of event")
    timestamp: float = Field(default_factory=time, description="Event timestamp")

    # Market-specific fields (optional for external events)
    token_id: str | None = Field(default=None, description="Polymarket token/asset ID")
    market_id: str | None = Field(default=None, description="Polymarket condition ID")

    # Price data (optional, depends on event type)
    best_bid: float | None = Field(default=None, ge=0, le=1)
    best_ask: float | None = Field(default=None, ge=0, le=1)
    last_price: float | None = Field(default=None, ge=0, le=1)
    last_size: float | None = Field(default=None, ge=0)

    # External event payload (for NEWS/SOCIAL events)
    content: str | None = Field(default=None, description="Text payload for external events")
    source: str | None = Field(default=None, description="Origin of external event (e.g., 'twitter', 'reuters')")

    # Raw payload for extensibility
    raw_data: dict[str, Any] = Field(default_factory=dict)

    def is_market_event(self) -> bool:
        """Check if this event has market data (token_id populated)."""
        return self.token_id is not None and self.event_type in (
            EventType.PRICE_CHANGE,
            EventType.BOOK_UPDATE,
            EventType.LAST_TRADE,
            EventType.TICK_SIZE_CHANGE,
        )


# =============================================================================
# Parser Configuration Models
# =============================================================================


class ThresholdRule(BaseModel):
    """Rule defining a price/probability threshold trigger.

    Immutable configuration for threshold-based trading.
    """

    model_config = {"frozen": True}

    token_id: str = Field(..., description="Token to monitor")
    trigger_side: Side = Field(..., description="BUY when price drops, SELL when rises")
    threshold: float = Field(..., gt=0, lt=1, description="Price/probability threshold")
    comparison: Literal["above", "below"] = Field(
        ..., description="Trigger when price crosses threshold"
    )
    size_usdc: float = Field(..., gt=0, description="Order size when triggered")
    reason_template: str = Field(
        default="Threshold {comparison} {threshold} triggered",
        description="Template for trade reason",
    )
    cooldown_seconds: float = Field(
        default=60.0, ge=0, description="Minimum time between triggers"
    )


# =============================================================================
# Phase 7 Portfolio Models
# =============================================================================


class Position(BaseModel):
    """Represents an open position in a market.

    Immutable data structure for position tracking.
    """

    model_config = {"frozen": True}

    token_id: str = Field(..., description="Polymarket token ID")
    side: PositionSide = Field(..., description="LONG/SHORT/FLAT")
    quantity: float = Field(..., ge=0, description="Number of shares held")
    avg_entry_price: float = Field(..., ge=0, le=1, description="Average entry price")
    current_price: float = Field(..., ge=0, le=1, description="Last known market price")
    opened_at: float = Field(default_factory=time, description="Position open timestamp")

    @property
    def unrealized_pnl(self) -> float:
        """Calculate unrealized P&L in USDC."""
        if self.side == PositionSide.FLAT:
            return 0.0
        direction = 1.0 if self.side == PositionSide.LONG else -1.0
        return direction * self.quantity * (self.current_price - self.avg_entry_price)

    @property
    def market_value(self) -> float:
        """Current value of position in USDC."""
        return self.quantity * self.current_price


class Order(BaseModel):
    """Enhanced order model with full lifecycle tracking.

    Immutable data structure for order management.
    """

    model_config = {"frozen": True}

    client_order_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        description="Client-generated order ID",
    )
    token_id: str = Field(..., description="Polymarket token ID")
    side: Side = Field(..., description="BUY/SELL")
    quantity: float = Field(..., gt=0, description="Number of shares")
    order_type: OrderType = Field(default=OrderType.FOK, description="Order type")
    limit_price: float | None = Field(default=None, ge=0, le=1, description="Limit price")
    time_in_force: TimeInForce = Field(default=TimeInForce.FOK, description="Time in force")
    reason: str = Field(..., description="Human-readable reason")
    created_at: float = Field(default_factory=time, description="Order creation time")
