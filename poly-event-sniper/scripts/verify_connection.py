#!/usr/bin/env python3
"""Verify Polymarket connection before going live.

Tests:
1. Private key format validation
2. CLOB API authentication (auto-derives credentials)
3. Wallet balance fetch
4. WebSocket market feed connection
5. Order book access for a test market

Usage:
    uv run python scripts/verify_connection.py
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from py_clob_client.client import ClobClient

from src.config import get_settings
from src.ingesters.polymarket import PolymarketIngester

# Test token - a known active market
# Using a Bitcoin market that should have liquidity
TEST_TOKEN_ID = "72764351885425491292910818593903116970287593848365163845719951278848564016561"

HOST = "https://clob.polymarket.com"
CHAIN_ID = 137


def validate_private_key(key: str) -> tuple[bool, str]:
    """Validate private key format.

    Returns:
        Tuple of (is_valid, message)
    """
    if not key:
        return False, "Private key is empty"

    if not key.startswith("0x"):
        return False, "Private key must start with '0x'"

    # Remove 0x prefix and check length
    hex_part = key[2:]
    if len(hex_part) != 64:
        return False, f"Private key should be 64 hex chars (got {len(hex_part)})"

    # Check if all characters are valid hex
    try:
        int(hex_part, 16)
    except ValueError:
        return False, "Private key contains non-hexadecimal characters"

    # Check for placeholder values
    if "YOUR" in key.upper() or "PRIVATE" in key.upper():
        return False, "Private key appears to be a placeholder"

    return True, "Private key format is valid"


async def test_clob_auth_and_balance() -> tuple[bool, str, float]:
    """Test CLOB authentication and fetch balance.

    Auto-derives API credentials from private key.

    Returns:
        Tuple of (success, message, balance)
    """
    settings = get_settings()
    private_key = settings.polygon.private_key.get_secret_value()

    try:
        # Initialize client with auto-derive
        client = ClobClient(
            host=HOST,
            chain_id=CHAIN_ID,
            key=private_key,
            signature_type=0,  # EOA wallet
        )

        # Derive credentials
        creds = await asyncio.to_thread(client.create_or_derive_api_creds)
        client.set_api_creds(creds)

        # Test balance fetch
        response = await asyncio.to_thread(client.get_balance_allowance)
        balance = float(response.get("balance", 0))

        return True, "CLOB authentication successful (auto-derived credentials)", balance

    except Exception as e:
        error_msg = str(e)
        if "Non-hexadecimal" in error_msg:
            return False, "Invalid private key format - check POLYGON_PRIVATE_KEY in .env", 0.0
        return False, f"CLOB authentication failed: {e}", 0.0


async def test_order_book(client: ClobClient | None = None) -> tuple[bool, str]:
    """Test order book fetch for a known market.

    Returns:
        Tuple of (success, message)
    """
    settings = get_settings()

    try:
        if client is None:
            private_key = settings.polygon.private_key.get_secret_value()
            client = ClobClient(
                host=HOST,
                chain_id=CHAIN_ID,
                key=private_key,
                signature_type=0,
            )
            creds = await asyncio.to_thread(client.create_or_derive_api_creds)
            client.set_api_creds(creds)

        # Fetch order book
        order_book = await asyncio.to_thread(client.get_order_book, TEST_TOKEN_ID)

        bids = order_book.get("bids", [])
        asks = order_book.get("asks", [])

        if bids or asks:
            best_bid = float(bids[0]["price"]) if bids else None
            best_ask = float(asks[0]["price"]) if asks else None
            return True, f"Order book OK | bid={best_bid} ask={best_ask}"
        else:
            return True, "Order book accessible (empty - market may be inactive)"

    except Exception as e:
        return False, f"Order book fetch failed: {e}"


async def test_websocket() -> tuple[bool, str]:
    """Test WebSocket connection to Polymarket.

    Returns:
        Tuple of (success, message)
    """
    ingester = PolymarketIngester()

    try:
        await ingester.connect()

        if ingester.is_connected:
            await ingester.disconnect()
            return True, "WebSocket connection successful"
        else:
            return False, "WebSocket connected but is_connected=False"

    except Exception as e:
        return False, f"WebSocket connection failed: {e}"


async def main() -> int:
    """Run all verification tests."""
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
    )

    settings = get_settings()
    private_key = settings.polygon.private_key.get_secret_value()

    print("\n" + "=" * 60)
    print("  POLYMARKET CONNECTION VERIFICATION")
    print("=" * 60)
    print(f"\n  Dry Run Mode: {settings.bot.dry_run}")
    print(f"  Max Position Size: ${settings.bot.max_position_size}")
    print()

    all_passed = True

    # Test 0: Private key format
    print("  [1/4] Validating private key format...")
    success, msg = validate_private_key(private_key)
    status = "PASS" if success else "FAIL"
    print(f"        {status}: {msg}")
    if not success:
        print("\n" + "=" * 60)
        print("  PRIVATE KEY INVALID - Cannot continue")
        print("\n  Fix your .env file:")
        print("    POLYGON_PRIVATE_KEY=0x<64 hex characters>")
        print("=" * 60 + "\n")
        return 1
    all_passed = all_passed and success

    # Test 1: CLOB Credentials
    print("\n  [2/4] Testing CLOB API authentication...")
    success, msg, balance = await test_clob_auth_and_balance()
    status = "PASS" if success else "FAIL"
    print(f"        {status}: {msg}")
    if success:
        print(f"        Balance: ${balance:.2f} USDC")
        if balance < 1.0:
            print("        WARNING: Balance is very low!")
    all_passed = all_passed and success

    # Test 2: Order Book
    print("\n  [3/4] Testing order book access...")
    success, msg = await test_order_book()
    status = "PASS" if success else "FAIL"
    print(f"        {status}: {msg}")
    all_passed = all_passed and success

    # Test 3: WebSocket
    print("\n  [4/4] Testing WebSocket connection...")
    success, msg = await test_websocket()
    status = "PASS" if success else "FAIL"
    print(f"        {status}: {msg}")
    all_passed = all_passed and success

    print("\n" + "=" * 60)
    if all_passed:
        print("  ALL TESTS PASSED - Ready for live trading!")
        print("\n  Next steps:")
        print("    1. Set BOT_DRY_RUN=false in .env")
        print("    2. Set BOT_MAX_POSITION_SIZE=2.0 for testing")
        print("    3. Run: uv run python main.py")
    else:
        print("  SOME TESTS FAILED - Check configuration and try again")
    print("=" * 60 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
