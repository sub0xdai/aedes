# Poly Event Sniper

A modular, low-latency event sniping bot for Polymarket prediction markets.

## Overview

Poly Event Sniper monitors Polymarket markets via WebSocket and automatically executes trades when price/probability thresholds are crossed. Built with a clean, extensible architecture following SOLID principles.

```
┌─────────────────────────────────────────────────────────────────┐
│                         ORCHESTRATOR                             │
│                                                                  │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────────┐   │
│   │  INGESTER   │ ──► │   PARSER    │ ──► │    EXECUTOR     │   │
│   │ (WebSocket) │     │ (Threshold) │     │  (Polymarket)   │   │
│   └─────────────┘     └─────────────┘     └─────────────────┘   │
│         │                   │                     │              │
│         ▼                   ▼                     ▼              │
│    MarketEvent         TradeSignal         ExecutionResult       │
└─────────────────────────────────────────────────────────────────┘
```

## Features

- **Real-time WebSocket ingestion** from Polymarket CLOB
- **Threshold-based signal generation** with cooldown periods
- **Dry-run mode** for safe testing (enabled by default)
- **Rate limiting** to prevent API bans (100ms between requests)
- **Position size limits** for risk management
- **Price validation** with spread checks for illiquid markets
- **Auto-reconnect** with exponential backoff
- **Graceful shutdown** handling (SIGINT/SIGTERM)
- **Comprehensive logging** with loguru
- **Type-safe** with MyPy strict mode

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.12+ |
| Package Manager | [uv](https://github.com/astral-sh/uv) |
| Configuration | pydantic-settings |
| HTTP/WebSocket | aiohttp |
| Polymarket Client | py-clob-client |
| Logging | loguru |
| Type Checking | MyPy (strict) |
| Testing | pytest + pytest-asyncio |
| Formatting | black, isort |

## Project Structure

```
poly-event-sniper/
├── src/
│   ├── config.py              # Pydantic settings configuration
│   ├── exceptions.py          # Custom exception hierarchy
│   ├── models.py              # Domain models (immutable)
│   ├── orchestrator.py        # Pipeline orchestration
│   ├── interfaces/
│   │   ├── executor.py        # BaseExecutor ABC
│   │   ├── ingester.py        # BaseIngester ABC
│   │   └── parser.py          # BaseParser ABC
│   ├── executors/
│   │   └── polymarket.py      # Polymarket CLOB executor
│   ├── ingesters/
│   │   └── polymarket.py      # WebSocket market data ingester
│   └── parsers/
│       └── threshold.py       # Price threshold parser
├── tests/
│   ├── test_execution.py      # Executor tests (33)
│   ├── test_ingestion.py      # Ingester tests (18)
│   ├── test_parsing.py        # Parser tests (14)
│   └── test_orchestrator.py   # Integration tests (6)
├── main.py                    # Entry point
├── pyproject.toml             # Dependencies & config
└── .env                       # Credentials (not committed)
```

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd poly-event-sniper

# Install dependencies with uv
uv sync

# Copy environment template
cp .env.example .env
```

## Configuration

Edit `.env` with your Polymarket credentials:

```bash
# Polygon Network
POLYGON_PRIVATE_KEY=your_private_key_here
POLYGON_RPC_URL=https://polygon-rpc.com

# Polymarket CLOB API
CLOB_API_KEY=your_api_key_here
CLOB_API_SECRET=your_api_secret_here
CLOB_API_PASSPHRASE=your_passphrase_here

# Bot Configuration
BOT_DRY_RUN=true                    # Set to false for live trading
BOT_MAX_POSITION_SIZE=1000.0        # Maximum position size in USDC

# Ingester Configuration
INGESTER_RECONNECT_ATTEMPTS=5
INGESTER_HEARTBEAT_INTERVAL=30.0

# Parser Configuration
PARSER_DEFAULT_COOLDOWN_SECONDS=60.0
```

## Usage

### Configure Trading Rules

Edit `main.py` to add your threshold rules:

```python
def load_rules() -> list[ThresholdRule]:
    return [
        # BUY when probability drops below 30%
        ThresholdRule(
            token_id="21742633143463906290569050155826241533067272736897614950488156847949938836455",
            trigger_side=Side.BUY,
            threshold=0.30,
            comparison="below",
            size_usdc=100.0,
            reason_template="BUY: probability dropped below {threshold}",
            cooldown_seconds=60.0,
        ),
        # SELL when probability rises above 70%
        ThresholdRule(
            token_id="21742633143463906290569050155826241533067272736897614950488156847949938836455",
            trigger_side=Side.SELL,
            threshold=0.70,
            comparison="above",
            size_usdc=50.0,
            reason_template="SELL: probability rose above {threshold}",
            cooldown_seconds=60.0,
        ),
    ]
```

### Run the Bot

```bash
# Run in dry-run mode (default)
uv run python main.py

# Logs are written to logs/ directory
```

### Run Tests

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/test_parsing.py

# Run with coverage
uv run pytest --cov=src
```

### Type Checking

```bash
uv run mypy src/ main.py
```

## Architecture

### Domain Models

All models are immutable (frozen) Pydantic models for thread safety:

- **TradeSignal**: Trading instruction (token_id, side, size_usdc, reason)
- **ExecutionResult**: Order result (order_id, status, filled_price, fees)
- **MarketEvent**: Raw market data from WebSocket
- **ThresholdRule**: Trading rule configuration

### Interfaces (ABCs)

The system uses abstract base classes for extensibility:

- **BaseIngester**: Async generator yielding `MarketEvent`
- **BaseParser**: Evaluates events, returns `TradeSignal | None`
- **BaseExecutor**: Executes signals, returns `ExecutionResult`

### Exception Hierarchy

```
ExecutorError
├── AuthenticationError
├── ExecutionError
├── OrderBookError
├── PriceValidationError
├── PositionSizeError
└── RateLimitError

IngestionError
├── ConnectionError
├── SubscriptionError
└── ReconnectionExhaustedError

ParserError
├── InvalidEventError
└── RuleConfigurationError
```

## Safety Features

| Feature | Description |
|---------|-------------|
| Dry-run mode | Default on, logs trades without executing |
| Position limits | Configurable max position size (default 1000 USDC) |
| Rate limiting | 100ms minimum between API calls |
| Spread validation | Rejects trades in illiquid markets (>50% spread) |
| Price bounds | Validates prices are within 0.01-0.99 range |
| Auto-reconnect | Exponential backoff on WebSocket disconnection |

## Development

### Adding a New Ingester

```python
from src.interfaces.ingester import BaseIngester
from src.models import MarketEvent

class TwitterIngester(BaseIngester):
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def subscribe(self, token_ids: list[str]) -> None: ...
    async def stream(self) -> AsyncIterator[MarketEvent]: ...
    @property
    def is_connected(self) -> bool: ...
```

### Adding a New Parser

```python
from src.interfaces.parser import BaseParser
from src.models import MarketEvent, TradeSignal

class SentimentParser(BaseParser):
    def evaluate(self, event: MarketEvent) -> TradeSignal | None: ...
    def reset(self) -> None: ...
```

## Test Coverage

```
tests/test_execution.py     33 tests  (executor, validation, models)
tests/test_ingestion.py     18 tests  (WebSocket parsing, connection)
tests/test_parsing.py       14 tests  (threshold logic, cooldowns)
tests/test_orchestrator.py   6 tests  (pipeline integration)
─────────────────────────────────────
Total                       71 tests
```

## License

MIT

## Disclaimer

This software is for educational purposes only. Trading prediction markets involves significant risk. Use at your own risk. Always test thoroughly in dry-run mode before enabling live trading.
