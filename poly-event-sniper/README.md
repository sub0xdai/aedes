# Aedes - Polymarket Event Sniper

A modular, low-latency trading bot for Polymarket prediction markets.

## Overview

Aedes monitors Polymarket markets via WebSocket and RSS feeds, automatically executing trades when price thresholds are crossed or keywords detected. Built with a clean, extensible architecture.

```
┌─────────────────────────────────────────────────────────────────┐
│                         ORCHESTRATOR                             │
│                                                                  │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────────┐   │
│   │  INGESTERS  │ ──► │   PARSERS   │ ──► │    EXECUTOR     │   │
│   │ WS / RSS    │     │ Price/News  │     │  (Polymarket)   │   │
│   └─────────────┘     └─────────────┘     └─────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Features

- **Real-time WebSocket ingestion** from Polymarket CLOB
- **RSS feed monitoring** for news-driven trading
- **In-app wallet management** - no private key export needed
- **Threshold & keyword signals** with cooldown periods
- **Dry-run mode** for safe testing (enabled by default)
- **Terminal UI** with live monitoring
- **Auto-discovery** of markets via Gamma API
- **Portfolio tracking** with risk controls
- **Type-safe** with MyPy strict mode

## Installation

```bash
git clone <repo-url>
cd poly-event-sniper
uv sync
```

## Quick Start

```bash
# Run with TUI (recommended)
uv run python main.py --tui

# Demo mode (fake data, no connections)
uv run python main.py --demo

# Headless mode
uv run python main.py
```

On first launch, the TUI will prompt you to **create a wallet**. No need to export private keys from MetaMask - Aedes creates and encrypts wallets internally using Ethereum keystore format.

## Configuration

Create `.env` for optional settings (wallet is managed in-app):

```bash
# Bot Configuration
BOT_DRY_RUN=true                    # Set to false for live trading
BOT_MAX_POSITION_SIZE=1000.0        # Maximum position size in USDC

# Optional: RPC URL (defaults to public endpoint)
POLYGON_RPC_URL=https://polygon-rpc.com

# Optional: Pre-existing CLOB credentials (auto-derived if empty)
CLOB_API_KEY=
CLOB_API_SECRET=
CLOB_API_PASSPHRASE=
```

**Note:** CLOB API credentials are automatically derived from your wallet's private key. You don't need to manually configure them.

## TUI Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│ AEDES  ● Connected  DRY RUN    │  Wallet: 0x1234...5678 $42.50       │
├────────────────────────────────┬─────────────────────────────────────┤
│                                │ STRATEGIES                          │
│       LOG PANEL                │ Threshold: 1 / Keyword: 1           │
│       (live feed)              │ METRICS                             │
│                                │ Events: 0 / Signals: 0 / Trades: 0  │
│                                ├─────────────────────────────────────┤
│                                │ RECENT TRADES                       │
│                                │ (none)                              │
├────────────────────────────────┴─────────────────────────────────────┤
│ q Quit  c Clear  u Lock/Unlock                                       │
└──────────────────────────────────────────────────────────────────────┘
```

**Key bindings:**
- `q` - Quit
- `c` - Clear logs
- `u` - Lock/Unlock wallet

## Trading Rules

Edit `main.py` to configure your trading rules:

```python
# Price threshold rule
ThresholdRule(
    token_id="7276...",
    trigger_side=Side.BUY,
    threshold=0.30,
    comparison="below",
    size_usdc=2.0,
    cooldown_seconds=300.0,
)

# Keyword rule (news-driven)
KeywordRule(
    keyword="Bitcoin",
    token_id="7276...",
    trigger_side=Side.BUY,
    size_usdc=1.5,
    cooldown_seconds=600.0,
)
```

## Tests

```bash
uv run pytest           # Run all 319 tests
uv run pytest -v        # Verbose output
uv run mypy src/        # Type checking
```

## Safety Features

| Feature | Description |
|---------|-------------|
| Dry-run mode | Default on, logs trades without executing |
| Position limits | Configurable max size (default 1000 USDC) |
| Rate limiting | 100ms minimum between API calls |
| Spread validation | Rejects illiquid markets (>50% spread) |
| Encrypted wallet | Ethereum keystore encryption (same as MetaMask) |

## Project Structure

```
src/
├── tui/                 # Terminal UI (Textual)
│   ├── app.py           # Main application
│   └── widgets/         # UI components
├── wallet/              # Wallet management
├── executors/           # Trade execution
├── ingesters/           # Data sources (WS, RSS)
├── parsers/             # Signal generation
├── discovery/           # Market discovery (Gamma API)
├── managers/            # Portfolio, subscriptions
└── persistence/         # SQLite + JSONL logging
```

## License

MIT

## Disclaimer

This software is for educational purposes only. Trading prediction markets involves significant risk. Use at your own risk. Always test in dry-run mode before enabling live trading.
