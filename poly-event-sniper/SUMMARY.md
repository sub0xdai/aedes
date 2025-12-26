# Aedes - Polymarket Event Sniper

**Tests:** 319 passing | **Status:** Phase 9 complete (TUI Refactor)

## What It Does

Algorithmic trading bot for Polymarket prediction markets. Monitors price feeds and news sources, generates trade signals based on configurable rules, and executes trades automatically.

## Current TUI Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│ AEDES  ● Connected  DRY RUN    │  Wallet: 0x1234...5678 $42.50       │
├────────────────────────────────┬─────────────────────────────────────┤
│                                │ STRATEGIES          (50%)           │
│       LOG PANEL                │ Threshold: 1 / Keyword: 1           │
│       (live feed)              │ METRICS                             │
│                                │ Events: 0 / Signals: 0 / Trades: 0  │
│                                ├─────────────────────────────────────┤
│                                │ RECENT TRADES       (50%)           │
│                                │ (none)                              │
├────────────────────────────────┴─────────────────────────────────────┤
│ q Quit  c Clear  u Lock/Unlock                                       │
└──────────────────────────────────────────────────────────────────────┘
```

**On startup:** Modal overlay prompts for wallet unlock/create. Dismisses after success.

## Recent Changes (Phase 9)

| Component | Description |
|-----------|-------------|
| **UnlockModal** | Centered overlay for wallet unlock/create on startup |
| **GlobalHeader** | Title + status + mode (left) │ wallet address + balance (right) |
| **Sidebar 50/50** | Stats panel (top half), Trades panel (bottom half) |
| **Key bindings** | `q` Quit, `c` Clear, `u` Lock/Unlock |
| **Logging fix** | TUI mode suppresses console spam, logs to file only |
| **Stream fix** | Handles array payloads from Polymarket WebSocket |

## Architecture Overview

```
Ingesters (N)          Parsers/Strategies (M)       Executor
┌─────────────┐        ┌─────────────────┐         ┌─────────────┐
│ Polymarket  │──┐     │ PriceThreshold  │         │ Polymarket  │
│ RSS Feeds   │──┼──▶  │ Keyword Match   │──▶      │ CLOB Client │
│ Manual/Test │──┘     │ Custom Strategy │         └─────────────┘
└─────────────┘        └─────────────────┘               │
                              │                    ┌─────────────┐
                       PortfolioManager ◀──────────│ SQLite DB   │
                       (risk controls)             │ JSONL logs  │
                                                   └─────────────┘
```

## Key Features

- **Multi-source ingestion**: Polymarket WebSocket, RSS feeds, manual injection
- **Multi-parser routing**: Each event evaluated by all parsers
- **Gamma discovery**: Auto-discover markets by criteria (tags, volume, liquidity)
- **Wallet management**: Create/unlock wallets in-app (Ethereum keystore encryption)
- **Portfolio tracking**: Position management, PnL calculation, risk controls
- **Dual persistence**: SQLite (queries) + JSONL (audit trail)

## Quick Start

```bash
cd poly-event-sniper
uv sync
cp .env.example .env  # Fill in credentials (optional for dry-run)
uv run python main.py --tui       # TUI mode
uv run python main.py --demo      # Demo mode (fake data)
uv run python main.py             # Headless mode
uv run pytest -v                  # Run tests
```

## Test Coverage

| Area | Tests |
|------|-------|
| Execution & validation | 33 |
| Ingestion & parsing | 46 |
| Discovery & subscription | 56 |
| Portfolio & strategies | 76 |
| Persistence & database | 28 |
| TUI & callbacks | 21 |
| Wallet management | 16 |
| Integration | 43 |
| **Total** | **319** |

## File Structure

```
src/
├── tui/
│   ├── app.py                 # Main TUI app with modal logic
│   └── widgets/
│       ├── global_header.py   # Header with wallet info
│       └── unlock_modal.py    # Unlock/create modal overlay
├── wallet/manager.py          # Wallet create/load/encrypt
├── executors/polymarket.py    # CLOB client, auto-derive credentials
├── ingesters/polymarket.py    # WebSocket with array payload handling
├── discovery/                 # Gamma API client
├── managers/                  # Portfolio, Subscription
├── persistence/               # SQLite + JSONL
└── parsers/                   # Threshold, Keyword
```

## Dependencies

```
textual ^6.11.0    # TUI framework
aiosqlite ^0.20.0  # Async SQLite
feedparser ^6.0.12 # RSS parsing
aiofiles ^25.1.0   # Async file I/O
eth-account        # Wallet management
py-clob-client     # Polymarket API
```
