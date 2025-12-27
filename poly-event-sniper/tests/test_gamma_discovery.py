"""Tests for Gamma Discovery Layer."""

import asyncio
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from src.discovery.client import GammaClient
from src.discovery.models import DiscoveryResult, MarketCriteria
from src.exceptions import GammaAPIError, GammaRateLimitError, GammaServerError


# =============================================================================
# MarketCriteria Tests
# =============================================================================


class TestMarketCriteriaModel:
    """Tests for MarketCriteria model."""

    def test_default_values(self) -> None:
        """Test default values are set correctly."""
        criteria = MarketCriteria()
        assert criteria.tags == []
        assert criteria.min_volume is None
        assert criteria.min_liquidity is None
        assert criteria.start_date_min is None
        assert criteria.keywords == []
        assert criteria.active_only is True

    def test_all_fields_set(self) -> None:
        """Test all fields can be set."""
        criteria = MarketCriteria(
            tags=["crypto", "politics"],
            min_volume=1000.0,
            min_liquidity=500.0,
            start_date_min=datetime(2025, 1, 1, tzinfo=timezone.utc),
            keywords=["bitcoin", "election"],
            active_only=False,
        )
        assert criteria.tags == ["crypto", "politics"]
        assert criteria.min_volume == 1000.0
        assert criteria.min_liquidity == 500.0
        assert criteria.keywords == ["bitcoin", "election"]
        assert criteria.active_only is False

    def test_is_frozen(self) -> None:
        """Test model is immutable."""
        criteria = MarketCriteria(tags=["crypto"])
        with pytest.raises(ValidationError):
            criteria.tags = ["politics"]  # type: ignore[misc]

    def test_to_query_params_empty(self) -> None:
        """Test query params with default criteria."""
        criteria = MarketCriteria()
        params = criteria.to_query_params()
        # active_only=True sends both active=true and closed=false
        assert params == {"active": "true", "closed": "false"}

    def test_to_query_params_with_tags(self) -> None:
        """Test query params with tags."""
        criteria = MarketCriteria(tags=["crypto", "bitcoin"])
        params = criteria.to_query_params()
        assert params["tag_slug"] == "crypto,bitcoin"
        assert params["active"] == "true"

    def test_to_query_params_inactive(self) -> None:
        """Test query params with active_only=False."""
        criteria = MarketCriteria(active_only=False)
        params = criteria.to_query_params()
        assert "active" not in params

    def test_min_volume_validation(self) -> None:
        """Test min_volume must be >= 0."""
        with pytest.raises(ValidationError):
            MarketCriteria(min_volume=-100.0)

    def test_min_liquidity_validation(self) -> None:
        """Test min_liquidity must be >= 0."""
        with pytest.raises(ValidationError):
            MarketCriteria(min_liquidity=-50.0)


# =============================================================================
# DiscoveryResult Tests
# =============================================================================


class TestDiscoveryResultModel:
    """Tests for DiscoveryResult model."""

    def test_required_fields_missing_market_id(self) -> None:
        """Test market_id is required."""
        with pytest.raises(ValidationError):
            DiscoveryResult(
                token_id="token_123",
                title="Test Market",
            )  # type: ignore[call-arg]

    def test_required_fields_missing_token_id(self) -> None:
        """Test token_id is required."""
        with pytest.raises(ValidationError):
            DiscoveryResult(
                market_id="market_123",
                title="Test Market",
            )  # type: ignore[call-arg]

    def test_required_fields_missing_title(self) -> None:
        """Test title is required."""
        with pytest.raises(ValidationError):
            DiscoveryResult(
                market_id="market_123",
                token_id="token_456",
            )  # type: ignore[call-arg]

    def test_invariant_market_id_not_empty(self) -> None:
        """Test market_id cannot be empty string."""
        with pytest.raises(ValidationError):
            DiscoveryResult(
                market_id="",
                token_id="token_123",
                title="Test",
            )

    def test_invariant_token_id_not_empty(self) -> None:
        """Test token_id cannot be empty string."""
        with pytest.raises(ValidationError):
            DiscoveryResult(
                market_id="market_123",
                token_id="",
                title="Test",
            )

    def test_valid_result(self) -> None:
        """Test creating a valid DiscoveryResult."""
        result = DiscoveryResult(
            market_id="market_123",
            token_id="token_456",
            title="Will BTC hit $100k?",
            volume=150000.50,
            liquidity=25000.00,
            end_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
            tags=["crypto", "bitcoin"],
        )
        assert result.market_id == "market_123"
        assert result.token_id == "token_456"
        assert result.title == "Will BTC hit $100k?"
        assert result.volume == 150000.50
        assert result.liquidity == 25000.00
        assert result.discovered_at > 0

    def test_is_frozen(self) -> None:
        """Test model is immutable."""
        result = DiscoveryResult(
            market_id="m1",
            token_id="t1",
            title="Test",
        )
        with pytest.raises(ValidationError):
            result.market_id = "m2"  # type: ignore[misc]

    def test_default_values(self) -> None:
        """Test default values for optional fields."""
        result = DiscoveryResult(
            market_id="m1",
            token_id="t1",
            title="Test",
        )
        assert result.volume == 0.0
        assert result.liquidity == 0.0
        assert result.end_date is None
        assert result.tags == []

    def test_volume_must_be_non_negative(self) -> None:
        """Test volume must be >= 0."""
        with pytest.raises(ValidationError):
            DiscoveryResult(
                market_id="m1",
                token_id="t1",
                title="Test",
                volume=-100.0,
            )

    def test_liquidity_must_be_non_negative(self) -> None:
        """Test liquidity must be >= 0."""
        with pytest.raises(ValidationError):
            DiscoveryResult(
                market_id="m1",
                token_id="t1",
                title="Test",
                liquidity=-50.0,
            )


# =============================================================================
# GammaClient Tests - Initialization
# =============================================================================


class TestGammaClientInit:
    """Tests for GammaClient initialization."""

    def test_default_timeout(self) -> None:
        """Test default timeout is set."""
        client = GammaClient()
        assert client._timeout.total == 30.0

    def test_custom_timeout(self) -> None:
        """Test custom timeout."""
        client = GammaClient(timeout=60.0)
        assert client._timeout.total == 60.0

    def test_custom_max_retries(self) -> None:
        """Test custom max retries."""
        client = GammaClient(max_retries=3)
        assert client._max_retries == 3


class TestGammaClientContextManager:
    """Tests for async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_creates_session(self) -> None:
        """Test context manager creates and closes session."""
        async with GammaClient() as client:
            assert client._session is not None
        assert client._session is None


# =============================================================================
# GammaClient Tests - Parsing
# =============================================================================


class TestGammaClientParsing:
    """Tests for Gamma API response parsing."""

    def test_parse_event_basic(self) -> None:
        """Test parsing a basic event."""
        client = GammaClient()
        event_data: dict[str, Any] = {
            "id": "event_123",
            "title": "Will BTC hit $100k?",
            "endDate": "2025-12-31T23:59:59Z",
            "tags": [{"slug": "crypto"}, {"slug": "bitcoin"}],
            "markets": [
                {
                    "id": "market_456",
                    "clobTokenIds": ["token_yes_789", "token_no_012"],
                    "volume": "150000.50",
                    "liquidity": "25000.00",
                }
            ],
        }

        results = client._parse_event(event_data)

        assert len(results) == 1
        assert results[0].market_id == "market_456"
        assert results[0].token_id == "token_yes_789"
        assert results[0].title == "Will BTC hit $100k?"
        assert results[0].volume == 150000.50
        assert results[0].liquidity == 25000.00
        assert results[0].tags == ["crypto", "bitcoin"]

    def test_parse_event_multiple_markets(self) -> None:
        """Test parsing event with multiple markets."""
        client = GammaClient()
        event_data: dict[str, Any] = {
            "title": "Multi-market event",
            "markets": [
                {"id": "m1", "clobTokenIds": ["t1"]},
                {"id": "m2", "clobTokenIds": ["t2"]},
            ],
            "tags": [],
        }

        results = client._parse_event(event_data)
        assert len(results) == 2

    def test_parse_event_skips_invalid_markets(self) -> None:
        """Test parsing skips markets without required fields."""
        client = GammaClient()
        event_data: dict[str, Any] = {
            "title": "Test",
            "markets": [
                {"id": "valid", "clobTokenIds": ["token"]},
                {"id": "", "clobTokenIds": ["token"]},  # Empty id
                {"id": "no_tokens", "clobTokenIds": []},  # No tokens
                {"clobTokenIds": ["token"]},  # Missing id
            ],
            "tags": [],
        }

        results = client._parse_event(event_data)
        assert len(results) == 1
        assert results[0].market_id == "valid"

    def test_safe_float_parsing(self) -> None:
        """Test _safe_float handles various inputs."""
        assert GammaClient._safe_float("123.45") == 123.45
        assert GammaClient._safe_float(123.45) == 123.45
        assert GammaClient._safe_float(123) == 123.0
        assert GammaClient._safe_float(None) == 0.0
        assert GammaClient._safe_float("invalid") == 0.0
        assert GammaClient._safe_float({}) == 0.0


# =============================================================================
# GammaClient Tests - Filtering
# =============================================================================


class TestGammaClientFiltering:
    """Tests for client-side result filtering."""

    def test_filter_by_min_volume(self) -> None:
        """Test filtering by minimum volume."""
        client = GammaClient()
        criteria = MarketCriteria(min_volume=1000.0)

        low_volume = DiscoveryResult(
            market_id="m1", token_id="t1", title="Low", volume=500.0
        )
        high_volume = DiscoveryResult(
            market_id="m2", token_id="t2", title="High", volume=1500.0
        )

        assert client._filter_result(low_volume, criteria) is False
        assert client._filter_result(high_volume, criteria) is True

    def test_filter_by_min_liquidity(self) -> None:
        """Test filtering by minimum liquidity."""
        client = GammaClient()
        criteria = MarketCriteria(min_liquidity=500.0)

        low_liq = DiscoveryResult(
            market_id="m1", token_id="t1", title="Low", liquidity=100.0
        )
        high_liq = DiscoveryResult(
            market_id="m2", token_id="t2", title="High", liquidity=1000.0
        )

        assert client._filter_result(low_liq, criteria) is False
        assert client._filter_result(high_liq, criteria) is True

    def test_filter_by_keywords(self) -> None:
        """Test filtering by keywords (case-insensitive)."""
        client = GammaClient()
        criteria = MarketCriteria(keywords=["bitcoin", "election"])

        match = DiscoveryResult(
            market_id="m1", token_id="t1", title="Will Bitcoin hit $100k?"
        )
        no_match = DiscoveryResult(
            market_id="m2", token_id="t2", title="Will it rain tomorrow?"
        )
        case_insensitive = DiscoveryResult(
            market_id="m3", token_id="t3", title="BITCOIN price prediction"
        )

        assert client._filter_result(match, criteria) is True
        assert client._filter_result(no_match, criteria) is False
        assert client._filter_result(case_insensitive, criteria) is True

    def test_filter_passes_all(self) -> None:
        """Test that result must pass ALL filters."""
        client = GammaClient()
        criteria = MarketCriteria(
            min_volume=1000.0,
            min_liquidity=500.0,
            keywords=["bitcoin"],
        )

        # Passes volume but not keywords
        result = DiscoveryResult(
            market_id="m1",
            token_id="t1",
            title="Ethereum",
            volume=2000.0,
            liquidity=1000.0,
        )
        assert client._filter_result(result, criteria) is False

    def test_filter_no_criteria_passes_all(self) -> None:
        """Test that empty criteria passes all results."""
        client = GammaClient()
        criteria = MarketCriteria()

        result = DiscoveryResult(
            market_id="m1", token_id="t1", title="Any Market"
        )
        assert client._filter_result(result, criteria) is True


# =============================================================================
# GammaClient Tests - HTTP with Mocks
# =============================================================================


class MockResponse:
    """Mock aiohttp response for testing."""

    def __init__(
        self,
        status: int,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self._json_data = json_data or {}
        self.headers = headers or {}

    async def json(self) -> dict[str, Any]:
        return self._json_data

    async def text(self) -> str:
        return str(self._json_data)

    async def __aenter__(self) -> "MockResponse":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


class TestGammaClientDiscover:
    """Tests for discover() method with mocked HTTP."""

    @pytest.mark.asyncio
    async def test_discover_success(self) -> None:
        """Test successful discovery."""
        mock_response = MockResponse(
            status=200,
            json_data={
                "data": [
                    {
                        "title": "Test Event",
                        "markets": [
                            {
                                "id": "market_1",
                                "clobTokenIds": ["token_1"],
                                "volume": "1000",
                                "liquidity": "500",
                            }
                        ],
                        "tags": [{"slug": "test"}],
                    }
                ],
                "next_cursor": None,
            },
        )

        async with GammaClient() as client:
            with patch.object(client._session, "get", return_value=mock_response):
                results = await client.discover(MarketCriteria())

        assert len(results) == 1
        assert results[0].market_id == "market_1"

    @pytest.mark.asyncio
    async def test_discover_with_limit(self) -> None:
        """Test discover respects limit parameter."""
        mock_response = MockResponse(
            status=200,
            json_data={
                "data": [
                    {
                        "title": "Event",
                        "markets": [
                            {"id": "m1", "clobTokenIds": ["t1"]},
                            {"id": "m2", "clobTokenIds": ["t2"]},
                            {"id": "m3", "clobTokenIds": ["t3"]},
                        ],
                        "tags": [],
                    }
                ],
            },
        )

        async with GammaClient() as client:
            with patch.object(client._session, "get", return_value=mock_response):
                results = await client.discover(MarketCriteria(), limit=2)

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_discover_pagination(self) -> None:
        """Test discover handles pagination."""
        page1_response = MockResponse(
            status=200,
            json_data={
                "data": [
                    {
                        "title": "Event 1",
                        "markets": [{"id": "m1", "clobTokenIds": ["t1"]}],
                        "tags": [],
                    }
                ],
                "next_cursor": "cursor_page2",
            },
        )
        page2_response = MockResponse(
            status=200,
            json_data={
                "data": [
                    {
                        "title": "Event 2",
                        "markets": [{"id": "m2", "clobTokenIds": ["t2"]}],
                        "tags": [],
                    }
                ],
                "next_cursor": None,
            },
        )

        call_count = 0

        def mock_get(*args: Any, **kwargs: Any) -> MockResponse:
            nonlocal call_count
            call_count += 1
            return page1_response if call_count == 1 else page2_response

        async with GammaClient() as client:
            with patch.object(client._session, "get", side_effect=mock_get):
                results = await client.discover(MarketCriteria())

        assert len(results) == 2
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_discover_empty_results(self) -> None:
        """Test discover with no results."""
        mock_response = MockResponse(
            status=200,
            json_data={"data": [], "next_cursor": None},
        )

        async with GammaClient() as client:
            with patch.object(client._session, "get", return_value=mock_response):
                results = await client.discover(MarketCriteria())

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_discover_raw_list_format(self) -> None:
        """Test discover handles real Gamma API format (raw list, not wrapped)."""
        # Real Gamma API returns raw list, not {"data": [...]}
        mock_response = MockResponse(
            status=200,
            json_data=[
                {
                    "title": "Real API Event",
                    "markets": [
                        {
                            "id": "market_real",
                            "clobTokenIds": ["token_real"],
                            "volume": "5000",
                            "liquidity": "1000",
                        }
                    ],
                    "tags": [{"slug": "crypto"}],
                }
            ],
        )

        async with GammaClient() as client:
            with patch.object(client._session, "get", return_value=mock_response):
                results = await client.discover(MarketCriteria())

        assert len(results) == 1
        assert results[0].market_id == "market_real"
        assert results[0].title == "Real API Event"


# =============================================================================
# GammaClient Tests - Error Handling
# =============================================================================


class TestGammaClientErrorHandling:
    """Tests for error handling and retries."""

    @pytest.mark.asyncio
    async def test_rate_limit_error(self) -> None:
        """Test 429 response raises GammaRateLimitError."""
        mock_response = MockResponse(
            status=429,
            headers={"Retry-After": "5"},
        )

        async with GammaClient(max_retries=1) as client:
            # Speed up test by reducing backoff
            client.INITIAL_BACKOFF = 0.01
            client.MAX_BACKOFF = 0.05

            with patch.object(client._session, "get", return_value=mock_response):
                with pytest.raises(GammaRateLimitError) as exc_info:
                    await client.discover(MarketCriteria())

        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_server_error_retries(self) -> None:
        """Test 500 response triggers retry then raises."""
        mock_response = MockResponse(status=500)
        call_count = 0

        def mock_get(*args: Any, **kwargs: Any) -> MockResponse:
            nonlocal call_count
            call_count += 1
            return mock_response

        async with GammaClient(max_retries=2) as client:
            client.INITIAL_BACKOFF = 0.01
            client.MAX_BACKOFF = 0.05

            with patch.object(client._session, "get", side_effect=mock_get):
                with pytest.raises(GammaServerError):
                    await client.discover(MarketCriteria())

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_client_error_no_retry(self) -> None:
        """Test 4xx (non-429) errors don't retry."""
        mock_response = MockResponse(
            status=400,
            json_data={"error": "Bad request"},
        )
        call_count = 0

        def mock_get(*args: Any, **kwargs: Any) -> MockResponse:
            nonlocal call_count
            call_count += 1
            return mock_response

        async with GammaClient() as client:
            with patch.object(client._session, "get", side_effect=mock_get):
                with pytest.raises(GammaAPIError) as exc_info:
                    await client.discover(MarketCriteria())

        assert exc_info.value.status_code == 400
        assert call_count == 1  # No retry

    @pytest.mark.asyncio
    async def test_timeout_handling(self) -> None:
        """Test timeout triggers retry."""
        call_count = 0

        def mock_get(*args: Any, **kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1
            raise asyncio.TimeoutError()

        async with GammaClient(max_retries=2) as client:
            client.INITIAL_BACKOFF = 0.01

            with patch.object(client._session, "get", side_effect=mock_get):
                with pytest.raises(GammaAPIError):
                    await client.discover(MarketCriteria())

        assert call_count == 2


# =============================================================================
# GammaClient Tests - Backoff
# =============================================================================


class TestGammaClientBackoff:
    """Tests for exponential backoff calculation."""

    def test_backoff_calculation(self) -> None:
        """Test exponential backoff values."""
        client = GammaClient()
        client.INITIAL_BACKOFF = 1.0
        client.BACKOFF_MULTIPLIER = 2.0
        client.MAX_BACKOFF = 60.0

        assert client._calculate_backoff(0) == 1.0
        assert client._calculate_backoff(1) == 2.0
        assert client._calculate_backoff(2) == 4.0
        assert client._calculate_backoff(3) == 8.0

    def test_backoff_respects_max(self) -> None:
        """Test backoff is capped at MAX_BACKOFF."""
        client = GammaClient()
        client.INITIAL_BACKOFF = 1.0
        client.BACKOFF_MULTIPLIER = 2.0
        client.MAX_BACKOFF = 10.0

        assert client._calculate_backoff(10) == 10.0  # Would be 1024 without cap
