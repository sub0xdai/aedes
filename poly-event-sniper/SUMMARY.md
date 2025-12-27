# Aedes - Polymarket Event Sniper

**Tests:** 339 passing | **Status:** Phase 10 complete (Wallet Wizard UX)

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
│ q Quit  c Clear  u Lock/Unlock  w Wallets                            │
└──────────────────────────────────────────────────────────────────────┘
```

**On startup:** Wallet wizard modal with Create/Import options. QR code for funding on success.

## Recent Changes (Phase 10)

| Component | Description |
|-----------|-------------|
| **WalletWizard** | First-run wizard: Create / Import Keystore / Import Private Key |
| **QR Code Funding** | Terminal QR code for mobile wallet deposits (segno) |
| **Import Methods** | `import_from_keystore()`, `import_from_private_key()` in WalletManager |
| **.env Fallback** | Power users can bypass TUI wallet with POLYGON_PRIVATE_KEY |
| **Optional Config** | POLYGON_PRIVATE_KEY now optional (TUI-first mode) |
| **Wallet Hotkey** | Press `w` to manage/switch wallets during runtime |

## Wallet Wizard Flow

```
First Run (no wallets):
┌─────────────────────────────────────────────┐
│            WALLET SETUP                     │
│  Choose how to set up your trading wallet:  │
│  [Create New Wallet]                        │
│  [Import MetaMask Keystore]                 │
│  [Import Private Key]                       │
│  [Use .env Wallet] (if available)           │
└─────────────────────────────────────────────┘

After Create/Import:
┌─────────────────────────────────────────────┐
│           WALLET READY                      │
│  Your deposit address:                      │
│  0x742d35Cc6634C0532925a3b844Bc9e759...     │
│  ▄▄▄▄▄▄▄▄▄▄▄                                │
│  █ ▄▄▄▄▄ █  <- QR Code (scan to fund)       │
│  █ █▄▄▄█ █                                  │
│  [Continue to Trading]                      │
└─────────────────────────────────────────────┘

Wallet Management (press 'w'):
┌─────────────────────────────────────────────┐
│          WALLET MANAGEMENT                  │
│  Select a wallet to use:                    │
│  [aedes_1735266123 (0xb62d...a9a3)]         │
│  [imported_wallet (0x742d...59e7)]          │
│                                             │
│  [Create/Import New]                        │
│  [Cancel]                                   │
└─────────────────────────────────────────────┘
```

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
- **Wallet wizard**: Create/import wallets with QR code for funding
- **Multi-wallet management**: Switch between wallets with `w` hotkey
- **Auto-derive CLOB**: API credentials derived from private key automatically
- **Portfolio tracking**: Position management, PnL calculation, risk controls
- **Dual persistence**: SQLite (queries) + JSONL (audit trail)

## Quick Start

```bash
cd poly-event-sniper
uv sync
uv run python main.py --tui       # TUI mode (wallet wizard on first run)
uv run python main.py --demo      # Demo mode (fake data)
uv run python main.py             # Headless mode
uv run pytest -v                  # Run tests
```

## Hotkeys

| Key | Action |
|-----|--------|
| `q` | Quit application |
| `c` | Clear log panel |
| `u` | Lock/Unlock current wallet |
| `w` | Open wallet management |

## Test Coverage

| Area | Tests |
|------|-------|
| Execution & validation | 33 |
| Ingestion & parsing | 46 |
| Discovery & subscription | 56 |
| Portfolio & strategies | 76 |
| Persistence & database | 28 |
| TUI & callbacks | 21 |
| Wallet management | 36 |
| Integration | 43 |
| **Total** | **339** |

## File Structure

```
src/
├── tui/
│   ├── app.py                 # Main TUI app with modal logic
│   └── widgets/
│       ├── global_header.py   # Header with wallet info
│       ├── unlock_modal.py    # Wallet wizard (create/import/unlock/manage)
│       └── qr_display.py      # Terminal QR code widget
├── wallet/manager.py          # Wallet create/import/load/encrypt
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
segno ^1.6.1       # QR code generation
aiosqlite ^0.20.0  # Async SQLite
feedparser ^6.0.12 # RSS parsing
aiofiles ^25.1.0   # Async file I/O
eth-account        # Wallet management
py-clob-client     # Polymarket API
```
