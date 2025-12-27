"""Gamma API client for market discovery."""

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from time import time
from typing import Any

import aiohttp
from loguru import logger

from src.discovery.models import DiscoveryResult, MarketCriteria
from src.exceptions import GammaAPIError, GammaRateLimitError, GammaServerError


class GammaClient:
    """Async HTTP client for Polymarket Gamma API.

    Discovers markets matching specified criteria with:
    - Automatic pagination (cursor-based)
    - Rate limit handling with exponential backoff
    - Server error retries
    - Configurable timeouts

    Usage:
        async with GammaClient() as client:
            results = await client.discover(criteria)
            # or stream:
            async for result in client.discover_stream(criteria):
                process(result)
    """

    # API Configuration
    BASE_URL = "https://gamma-api.polymarket.com"
    EVENTS_ENDPOINT = "/events"

    # Backoff Configuration (matches PolymarketIngester pattern)
    INITIAL_BACKOFF: float = 1.0
    MAX_BACKOFF: float = 60.0
    BACKOFF_MULTIPLIER: float = 2.0
    MAX_RETRIES: int = 5

    # Rate Limiting
    MIN_REQUEST_INTERVAL: float = 0.1  # 100ms between requests

    # Timeouts
    DEFAULT_TIMEOUT: float = 30.0

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        """Initialize the Gamma client.

        Args:
            timeout: Request timeout in seconds.
            max_retries: Maximum retry attempts for transient errors.
        """
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._max_retries = max_retries
        self._session: aiohttp.ClientSession | None = None
        self._last_request_time: float = 0.0

    async def __aenter__(self) -> "GammaClient":
        """Async context manager entry."""
        self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit."""
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure session exists, creating if needed."""
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    async def _rate_limit(self) -> None:
        """Enforce minimum request interval."""
        elapsed = time() - self._last_request_time
        if elapsed < self.MIN_REQUEST_INTERVAL:
            await asyncio.sleep(self.MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time()

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay."""
        return min(
            self.INITIAL_BACKOFF * (self.BACKOFF_MULTIPLIER**attempt),
            self.MAX_BACKOFF,
        )

    async def _request_with_retry(
        self,
        url: str,
        params: dict[str, str],
    ) -> dict[str, Any]:
        """Make HTTP request with exponential backoff retry.

        Args:
            url: Full URL to request.
            params: Query parameters.

        Returns:
            Parsed JSON response.

        Raises:
            GammaRateLimitError: If rate limited after all retries.
            GammaServerError: If server error after all retries.
            GammaAPIError: For other API errors.
        """
        session = await self._ensure_session()
        last_exception: Exception | None = None

        for attempt in range(self._max_retries):
            await self._rate_limit()

            try:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        result: dict[str, Any] = await response.json()
                        return result

                    elif response.status == 429:
                        retry_after_header = response.headers.get("Retry-After")
                        retry_seconds = (
                            float(retry_after_header)
                            if retry_after_header
                            else self._calculate_backoff(attempt)
                        )
                        logger.warning(
                            "Rate limited (429), retry {} after {:.1f}s",
                            attempt + 1,
                            retry_seconds,
                        )
                        last_exception = GammaRateLimitError(retry_after=retry_seconds)
                        await asyncio.sleep(retry_seconds)

                    elif response.status >= 500:
                        backoff = self._calculate_backoff(attempt)
                        logger.warning(
                            "Server error ({}), retry {} after {:.1f}s",
                            response.status,
                            attempt + 1,
                            backoff,
                        )
                        last_exception = GammaServerError(
                            message=f"Server returned {response.status}",
                            status_code=response.status,
                        )
                        await asyncio.sleep(backoff)

                    else:
                        # Client error - don't retry
                        text = await response.text()
                        raise GammaAPIError(
                            f"API error {response.status}: {text[:200]}",
                            status_code=response.status,
                        )

            except aiohttp.ClientError as e:
                backoff = self._calculate_backoff(attempt)
                logger.warning(
                    "Connection error: {}, retry {} after {:.1f}s",
                    str(e),
                    attempt + 1,
                    backoff,
                )
                last_exception = GammaAPIError(f"Connection error: {e}")
                await asyncio.sleep(backoff)

            except asyncio.TimeoutError:
                backoff = self._calculate_backoff(attempt)
                logger.warning(
                    "Request timeout, retry {} after {:.1f}s",
                    attempt + 1,
                    backoff,
                )
                last_exception = GammaAPIError("Request timeout")
                await asyncio.sleep(backoff)

        # All retries exhausted
        if isinstance(last_exception, GammaRateLimitError):
            raise last_exception
        elif isinstance(last_exception, GammaServerError):
            raise last_exception
        elif last_exception is not None:
            raise last_exception
        else:
            raise GammaAPIError("Unknown error after retries")

    def _parse_event(self, event_data: dict[str, Any]) -> list[DiscoveryResult]:
        """Parse Gamma API event into DiscoveryResult objects.

        Args:
            event_data: Raw event dict from API.

        Returns:
            List of DiscoveryResult (one per market in the event).
        """
        results: list[DiscoveryResult] = []

        markets = event_data.get("markets", [])
        event_title = event_data.get("title", "")
        event_end_date_str = event_data.get("endDate")
        event_tags = [tag.get("slug", "") for tag in event_data.get("tags", [])]

        end_date: datetime | None = None
        if event_end_date_str:
            try:
                end_date = datetime.fromisoformat(
                    event_end_date_str.replace("Z", "+00:00")
                )
            except ValueError:
                logger.debug("Failed to parse end date: {}", event_end_date_str)

        for market in markets:
            market_id = market.get("id")
            clob_token_ids = market.get("clobTokenIds", [])

            # Skip if missing required fields or empty market_id
            if not market_id or not clob_token_ids:
                logger.debug(
                    "Skipping market with missing id or tokens: {}",
                    market.get("id", "unknown"),
                )
                continue

            # First token is YES outcome
            token_id = clob_token_ids[0] if clob_token_ids else None
            if not token_id:
                continue

            # Parse volume and liquidity safely
            volume = self._safe_float(market.get("volume", "0"))
            liquidity = self._safe_float(market.get("liquidity", "0"))

            results.append(
                DiscoveryResult(
                    market_id=market_id,
                    token_id=token_id,
                    title=event_title,
                    volume=volume,
                    liquidity=liquidity,
                    end_date=end_date,
                    tags=event_tags,
                )
            )

        return results

    @staticmethod
    def _safe_float(value: Any) -> float:
        """Safely parse float, returning 0.0 on failure."""
        if value is None:
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _filter_result(
        self,
        result: DiscoveryResult,
        criteria: MarketCriteria,
    ) -> bool:
        """Check if result matches client-side filter criteria.

        Args:
            result: Discovery result to check.
            criteria: Filter criteria.

        Returns:
            True if result passes all filters.
        """
        # Volume filter
        if criteria.min_volume is not None:
            if result.volume < criteria.min_volume:
                return False

        # Liquidity filter
        if criteria.min_liquidity is not None:
            if result.liquidity < criteria.min_liquidity:
                return False

        # Keyword filter (case-insensitive)
        if criteria.keywords:
            title_lower = result.title.lower()
            if not any(kw.lower() in title_lower for kw in criteria.keywords):
                return False

        return True

    async def discover(
        self,
        criteria: MarketCriteria,
        limit: int | None = None,
    ) -> list[DiscoveryResult]:
        """Discover markets matching criteria.

        Args:
            criteria: Search criteria.
            limit: Maximum results to return (None for all).

        Returns:
            List of DiscoveryResult matching criteria.

        Raises:
            GammaAPIError: On API errors.
            GammaRateLimitError: If rate limited.
            GammaServerError: On server errors.
        """
        results: list[DiscoveryResult] = []

        async for result in self.discover_stream(criteria):
            results.append(result)
            if limit is not None and len(results) >= limit:
                break

        return results

    async def discover_stream(
        self,
        criteria: MarketCriteria,
    ) -> AsyncIterator[DiscoveryResult]:
        """Stream discovered markets matching criteria.

        Handles pagination automatically, yielding results as they
        are discovered.

        Args:
            criteria: Search criteria.

        Yields:
            DiscoveryResult objects matching criteria.

        Raises:
            GammaAPIError: On API errors.
            GammaRateLimitError: If rate limited.
            GammaServerError: On server errors.
        """
        url = f"{self.BASE_URL}{self.EVENTS_ENDPOINT}"
        params = criteria.to_query_params()
        next_cursor: str | None = None

        while True:
            request_params = params.copy()
            if next_cursor:
                request_params["cursor"] = next_cursor

            logger.debug("Fetching events with params: {}", request_params)

            try:
                data = await self._request_with_retry(url, request_params)
            except GammaAPIError as e:
                logger.error("Gamma API error: {}", str(e))
                raise

            # Handle both API response formats:
            # - Real API returns raw list: [...]
            # - Some responses may be wrapped: {"data": [...]}
            if isinstance(data, list):
                events = data
                next_cursor = None  # Raw list format has no pagination
            else:
                events = data.get("data", [])

            for event in events:
                for result in self._parse_event(event):
                    if self._filter_result(result, criteria):
                        yield result

            # Check for more pages (only wrapped format supports pagination)
            if isinstance(data, list):
                break  # Raw list format has no pagination
            next_cursor = data.get("next_cursor")
            if not next_cursor:
                break

            logger.debug("Fetching next page with cursor: {}", next_cursor)
