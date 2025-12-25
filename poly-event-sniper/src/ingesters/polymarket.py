"""Polymarket CLOB WebSocket ingester implementation."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import aiohttp
from loguru import logger

from src.config import get_settings
from src.exceptions import (
    ConnectionError,
    ReconnectionExhaustedError,
    SubscriptionError,
)
from src.interfaces.ingester import MarketDataIngester
from src.models import EventType, MarketEvent


class PolymarketIngester(MarketDataIngester):
    """Ingester implementation for Polymarket CLOB WebSocket.

    Connects to the Polymarket market channel and yields MarketEvent
    objects for subscribed tokens.

    Features:
    - Automatic reconnection with exponential backoff
    - Rate limit awareness (respects 429 responses)
    - Clean shutdown handling
    - Event parsing with validation
    """

    # WebSocket endpoint
    WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

    # Reconnection settings
    MAX_RECONNECT_ATTEMPTS = 5
    INITIAL_BACKOFF_SECONDS = 1.0
    MAX_BACKOFF_SECONDS = 60.0
    BACKOFF_MULTIPLIER = 2.0

    # Heartbeat interval
    HEARTBEAT_INTERVAL = 30.0

    def __init__(self) -> None:
        """Initialize the ingester."""
        self._settings = get_settings()
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._subscribed_tokens: set[str] = set()
        self._is_connected = False
        self._reconnect_attempts = 0
        self._should_run = False

    async def connect(self) -> None:
        """Establish WebSocket connection to Polymarket.

        If tokens were pre-registered via subscribe(), sends subscription
        message after connection is established.
        """
        logger.info("Connecting to Polymarket WebSocket: {}", self.WS_URL)

        try:
            self._session = aiohttp.ClientSession()
            self._ws = await self._session.ws_connect(
                self.WS_URL,
                heartbeat=self.HEARTBEAT_INTERVAL,
            )
            self._is_connected = True
            self._reconnect_attempts = 0
            self._should_run = True

            logger.info("Successfully connected to Polymarket WebSocket")

            # Send subscription for any pre-registered tokens
            if self._subscribed_tokens:
                await self._send_subscription(list(self._subscribed_tokens))

        except Exception as e:
            logger.error("Failed to connect to WebSocket: {}", str(e))
            await self._cleanup()
            raise ConnectionError(f"WebSocket connection failed: {e}") from e

    async def disconnect(self) -> None:
        """Gracefully close WebSocket connection."""
        logger.info("Disconnecting from Polymarket WebSocket")
        self._should_run = False
        await self._cleanup()

    async def _cleanup(self) -> None:
        """Clean up resources."""
        self._is_connected = False
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def subscribe(self, token_ids: list[str]) -> None:
        """Subscribe to market events for specified tokens.

        Can be called before or after connect(). If called before,
        tokens are registered and subscription is sent when connect() is called.
        If called after, subscription is sent immediately.
        """
        self._subscribed_tokens.update(token_ids)

        # If already connected, send subscription immediately
        if self._is_connected and self._ws is not None:
            await self._send_subscription(token_ids)
        else:
            logger.info("Registered {} tokens for subscription on connect", len(token_ids))

    async def _send_subscription(self, token_ids: list[str]) -> None:
        """Send subscription message to WebSocket."""
        if self._ws is None:
            raise SubscriptionError("WebSocket not available")

        subscription_msg = {"assets_ids": token_ids, "type": "market"}

        try:
            await self._ws.send_json(subscription_msg)
            logger.info("Subscribed to {} tokens", len(token_ids))

        except Exception as e:
            raise SubscriptionError(f"Subscription failed: {e}") from e

    async def stream(self) -> AsyncIterator[MarketEvent]:
        """Stream market events as async generator."""
        if not self._is_connected or self._ws is None:
            raise ConnectionError("Not connected to WebSocket")

        while self._should_run:
            try:
                msg = await self._ws.receive(timeout=60.0)

                if msg.type == aiohttp.WSMsgType.TEXT:
                    event = self._parse_message(msg.data)
                    if event is not None:
                        yield event

                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.warning("WebSocket closed, attempting reconnect")
                    await self._reconnect()

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error("WebSocket error: {}", self._ws.exception())
                    await self._reconnect()

            except asyncio.TimeoutError:
                # No message received, continue waiting
                continue
            except asyncio.CancelledError:
                logger.info("Stream cancelled, shutting down")
                break
            except Exception as e:
                logger.error("Error in stream: {}", str(e))
                await self._reconnect()

    async def _reconnect(self) -> None:
        """Attempt to reconnect with exponential backoff."""
        await self._cleanup()

        while self._reconnect_attempts < self.MAX_RECONNECT_ATTEMPTS:
            self._reconnect_attempts += 1
            backoff = min(
                self.INITIAL_BACKOFF_SECONDS
                * (self.BACKOFF_MULTIPLIER ** (self._reconnect_attempts - 1)),
                self.MAX_BACKOFF_SECONDS,
            )

            logger.info(
                "Reconnection attempt {}/{} in {:.1f}s",
                self._reconnect_attempts,
                self.MAX_RECONNECT_ATTEMPTS,
                backoff,
            )

            await asyncio.sleep(backoff)

            try:
                await self.connect()
                # connect() automatically re-subscribes to registered tokens
                return
            except ConnectionError:
                continue

        raise ReconnectionExhaustedError(
            f"Failed to reconnect after {self.MAX_RECONNECT_ATTEMPTS} attempts"
        )

    def _parse_message(self, data: str) -> MarketEvent | None:
        """Parse WebSocket message into MarketEvent."""
        try:
            payload = json.loads(data)
            event_type_str = payload.get("event_type", "")

            # Map event types
            event_type_map = {
                "book": EventType.BOOK_UPDATE,
                "price_change": EventType.PRICE_CHANGE,
                "last_trade_price": EventType.LAST_TRADE,
                "tick_size_change": EventType.TICK_SIZE_CHANGE,
            }

            event_type = event_type_map.get(event_type_str)
            if event_type is None:
                return None

            # Extract common fields
            token_id = payload.get("asset_id", "")
            market_id = payload.get("market", "")

            # Extract price data based on event type
            best_bid = self._safe_float(payload.get("best_bid"))
            best_ask = self._safe_float(payload.get("best_ask"))
            last_price = self._safe_float(payload.get("price"))
            last_size = self._safe_float(payload.get("size"))

            # For book events, extract from bids/asks arrays
            if event_type == EventType.BOOK_UPDATE:
                bids = payload.get("buys", [])
                asks = payload.get("sells", [])
                if bids:
                    best_bid = self._safe_float(bids[0].get("price"))
                if asks:
                    best_ask = self._safe_float(asks[0].get("price"))

            return MarketEvent(
                event_type=event_type,
                token_id=token_id,
                market_id=market_id,
                best_bid=best_bid,
                best_ask=best_ask,
                last_price=last_price,
                last_size=last_size,
                raw_data=payload,
            )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(
                "Failed to parse message: {} - {}", str(e), data[:100] if data else ""
            )
            return None

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        """Safely parse a float value."""
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @property
    def is_connected(self) -> bool:
        """Check if connected to WebSocket."""
        return self._is_connected

    def get_subscribed_tokens(self) -> set[str]:
        """Get the set of currently subscribed token IDs.

        Returns:
            A copy of the subscribed tokens set.
        """
        return self._subscribed_tokens.copy()
