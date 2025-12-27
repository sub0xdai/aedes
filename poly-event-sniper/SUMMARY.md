# Aedes - Polymarket Event Sniper

**Tests:** 338 passing | **Status:** Phase 12 complete (Wallet Dashboard + Bug Fixes)

> **Geo-Blocking Notice:** Polymarket is blocked in Australia, USA, and other regions.
> You must deploy to a VPS in a supported region (UK, EU, etc.). See [docs/DEPLOY.md](docs/DEPLOY.md).

## What It Does

Algorithmic trading bot for Polymarket prediction markets. Monitors price feeds and news sources, generates trade signals based on configurable rules, and executes trades automatically.

## Current TUI Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│ AEDES  ■ IDLE  DRY RUN         │  Wallet: 0x1234...5678 $42.50       │
├────────────────────────────────┬─────────────────────────────────────┤
│                                │ WALLET                              │
│                                │ Balance: $42.50                     │
│                                │ PnL: +$3.25                         │
│       LOG PANEL                │ Positions: 2                        │
│       (live feed)              │ METRICS                             │
│                                │ Discovered: 35 / Signals: 0         │
│                                ├─────────────────────────────────────┤
│                                │ POSITIONS                           │
│                                │ Token   Entry  Now    PnL           │
│                                │ 8a3f... 0.25   0.31  +$0.60         │
│                                ├─────────────────────────────────────┤
│                                │ RECENT TRADES                       │
│                                │ BUY 8a3f... @ 0.25 ✓                │
├────────────────────────────────┴─────────────────────────────────────┤
│ q Quit  s Start/Stop  d Discover  c Clear  w Wallets                 │
└──────────────────────────────────────────────────────────────────────┘
```

**Trading states:** IDLE (yellow) → press `s` → RUNNING (green) → press `s` → IDLE

**On startup:** Wallet wizard modal with Create/Import options. QR code for funding on success.

---

## Recent Changes (Phase 12)

| Component | Description |
|-----------|-------------|
| **Wallet Dashboard** | 3-way sidebar split: Wallet summary, Positions table, Recent trades |
| **Balance Display** | Shows wallet balance, PnL, position count in sidebar |
| **Positions Panel** | Compact 4-column table (Token, Entry, Now, PnL) |
| **Gamma API Fix** | Fixed response parsing - API returns raw list, not wrapped object |
| **Discovery Fix** | Added `closed=false` param to get active tradeable markets |
| **Deployment Guide** | Added `docs/DEPLOY.md` for VPS deployment (geo-blocking workaround) |

---

## Recent Changes (Phase 11)

| Component | Description |
|-----------|-------------|
| **Smart Discovery** | 8 auto-discovery strategies with lowered thresholds |
| **On-Demand Discovery** | Press `d` to discover new markets anytime |
| **Discovered Counter** | Sidebar shows total discovered markets |
| **No Static Rules** | Threshold/Keyword rules now empty - discovery handles all |

### Discovery Strategies

| Strategy | Volume | Trigger | Position |
|----------|--------|---------|----------|
| high_volume_buys | $10k | BUY < 0.25 | $1.50 |
| high_volume_sells | $10k | SELL > 0.75 | $1.50 |
| crypto | $5k | BUY < 0.20 | $1.50 |
| politics | $15k | BUY < 0.15 | $2.00 |
| sports | $5k | BUY < 0.20 | $1.00 |
| entertainment | $5k | BUY < 0.25 | $1.00 |
| science | $3k | BUY < 0.20 | $1.00 |
| business | $5k | BUY < 0.20 | $1.50 |

---

## Recent Changes (Phase 10)

| Component | Description |
|-----------|-------------|
| **Start/Stop Control** | Press `s` to start/stop trading - no auto-start |
| **Trading Status** | Header shows IDLE/RUNNING/STOPPED status clearly |
| **Password-free Wallets** | No passwords required - wallets stored as plain JSON |
| **WalletWizard** | First-run wizard: Create / Import Keystore / Import Private Key |
| **QR Code Funding** | Terminal QR code for mobile wallet deposits (segno) |
| **Import Methods** | `import_from_keystore()`, `import_from_private_key()` in WalletManager |
| **.env Fallback** | Power users can bypass TUI wallet with POLYGON_PRIVATE_KEY |
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
| `s` | Start/Stop trading |
| `d` | Discover new markets |
| `c` | Clear log panel |
| `w` | Open wallet management |
| `Esc` | Close help panel |

## Test Coverage

| Area | Tests |
|------|-------|
| Execution & validation | 33 |
| Ingestion & parsing | 46 |
| Discovery & subscription | 56 |
| Portfolio & strategies | 76 |
| Persistence & database | 28 |
| TUI & callbacks | 21 |
| Wallet management | 34 |
| Integration | 43 |
| **Total** | **338** |

## File Structure

```
src/
├── tui/
│   ├── app.py                 # Main TUI app with modal logic
│   └── widgets/
│       ├── global_header.py   # Header with wallet info
│       ├── unlock_modal.py    # Wallet wizard (create/import/unlock/manage)
│       └── qr_display.py      # Terminal QR code widget
├── wallet/manager.py          # Wallet create/import/load (plain JSON storage)
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
