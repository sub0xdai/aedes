"""Discovery layer models for Gamma API market search."""

from datetime import datetime
from time import time

from pydantic import BaseModel, Field


class MarketCriteria(BaseModel):
    """Search parameters for Gamma API market discovery.

    Immutable configuration for filtering markets by tags, volume,
    liquidity, dates, and keywords.
    """

    model_config = {"frozen": True}

    tags: list[str] = Field(
        default_factory=list,
        description="Tag slugs to filter by (e.g., 'crypto', 'politics')",
    )
    min_volume: float | None = Field(
        default=None,
        ge=0,
        description="Minimum trading volume in USDC",
    )
    min_liquidity: float | None = Field(
        default=None,
        ge=0,
        description="Minimum liquidity in USDC",
    )
    start_date_min: datetime | None = Field(
        default=None,
        description="Markets starting after this date",
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="Title keyword whitelist (case-insensitive match)",
    )
    active_only: bool = Field(
        default=True,
        description="Only return active (non-resolved) markets",
    )

    def to_query_params(self) -> dict[str, str]:
        """Convert criteria to Gamma API query parameters.

        Returns:
            Dict of query string parameters for the API request.
        """
        params: dict[str, str] = {}

        if self.tags:
            params["tag_slug"] = ",".join(self.tags)

        if self.active_only:
            params["active"] = "true"

        # Note: min_volume, min_liquidity, keywords are client-side filters
        # as Gamma API may not support all filters server-side

        return params


class DiscoveryResult(BaseModel):
    """Normalized market representation from Gamma API.

    Immutable data structure containing essential market information
    for downstream processing.

    Invariants:
        - market_id is REQUIRED and never None/empty
        - token_id is REQUIRED and never None/empty
        - title is REQUIRED
    """

    model_config = {"frozen": True}

    market_id: str = Field(
        ...,
        min_length=1,
        description="Polymarket market/condition ID (REQUIRED)",
    )
    token_id: str = Field(
        ...,
        min_length=1,
        description="YES outcome token ID (REQUIRED)",
    )
    title: str = Field(
        ...,
        description="Market question/title",
    )
    volume: float = Field(
        default=0.0,
        ge=0,
        description="Trading volume in USDC",
    )
    liquidity: float = Field(
        default=0.0,
        ge=0,
        description="Current liquidity in USDC",
    )
    end_date: datetime | None = Field(
        default=None,
        description="Market resolution date",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Market tag slugs",
    )
    discovered_at: float = Field(
        default_factory=time,
        description="Timestamp of discovery",
    )


class RuleTemplate(BaseModel):
    """Blueprint for generating trading rules from discovered markets.

    Defines the trading logic to apply to any market found by a specific strategy.
    The 'token_id' field is omitted here as it is populated dynamically.
    """

    model_config = {"frozen": True}

    trigger_side: str = Field(..., description="BUY or SELL")
    threshold: float = Field(..., gt=0, lt=1, description="Price/probability threshold")
    comparison: str = Field(..., description="'above' or 'below'")
    size_usdc: float = Field(..., gt=0, description="Order size per trade")
    cooldown_seconds: float = Field(default=300.0, ge=0)


class DiscoveryStrategy(BaseModel):
    """Configuration binding search criteria to trading logic.

    Example: "High Volume Crypto Dip" -> Find crypto > $100k vol -> Buy if < 0.10
    """

    model_config = {"frozen": True}

    name: str = Field(..., description="Unique name for this strategy")
    criteria: MarketCriteria = Field(..., description="Search parameters")
    rule_template: RuleTemplate = Field(..., description="Trading logic to apply")
    max_markets: int = Field(default=10, gt=0, description="Max markets to subscribe to")
