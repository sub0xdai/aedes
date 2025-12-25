# Implementation Summary: Poly Event Sniper

**Date:** 2025-12-26
**Tests:** 303 passing
**Type Safety:** Mypy clean (including `--strict` on all modules)
**Status:** Phase 7 complete (General-Purpose Trading System)

---

## Active Trading Strategies

| Strategy | Market | Token | Parser | Trigger |
|----------|--------|-------|--------|---------|
| Bitcoin $100k Dip | BTC to $100k by Dec 31 | `7276...` | Threshold | BUY < 0.95 |
| Epstein Files | Trump releases files | `8607...` | Keyword | "Epstein", "Trump release" |
| 49ers vs Colts | NFL game winner | `8545...` | Keyword | "49ers touchdown", "SF score" |

**RSS Feeds:** 6 (Crypto: 2, Politics: 2, Sports: 2)

---

## What Was Implemented

### Phase 1: Foundation & Persistence

| Component | File | Description |
|-----------|------|-------------|
| **EventType extension** | `src/models.py` | Added `NEWS` and `SOCIAL` to EventType enum |
| **MarketEvent evolution** | `src/models.py` | Made `token_id`/`market_id` optional, added `content`/`source` fields, added `is_market_event()` helper |
| **TradeLogger** | `src/persistence/trade_logger.py` | Async JSONL logging with `aiofiles`, daily file rotation, fail-safe error handling |
| **Interface split** | `src/interfaces/ingester.py` | Split `BaseIngester` into `MarketDataIngester` and `ExternalEventIngester` |
| **Deferred subscription** | `src/ingesters/polymarket.py` | `subscribe()` can be called before `connect()` |

### Phase 2: Event Engine

| Component | File | Description |
|-----------|------|-------------|
| **ManualEventIngester** | `src/ingesters/external.py` | Test/God Mode event injection for external events |
| **KeywordParser** | `src/parsers/keyword.py` | News-to-trade signal generation with keyword matching |
| **KeywordRule** | `src/parsers/keyword.py` | Immutable configuration model for keyword triggers |

### Phase 3: Integration & Verification

| Component | File | Description |
|-----------|------|-------------|
| **Integration tests** | `tests/test_event_sniping.py` | Full pipeline tests: Inject -> Parse -> Execute -> Log |
| **main.py updates** | `main.py` | Added keyword rule loading, documented future multi-ingester support |

### Phase 4: Multi-Source Ingestion & RSS

| Component | File | Description |
|-----------|------|-------------|
| **Multi-Ingester Orchestrator** | `src/orchestrator.py` | N:N support with `asyncio.Queue` merging events from multiple ingesters |
| **Multi-Parser Routing** | `src/orchestrator.py` | Each event evaluated by all parsers, signals executed independently |
| **Backward Compatibility** | `src/orchestrator.py` | Legacy `Orchestrator(ingester, parser, executor)` API still works |
| **RssIngester** | `src/ingesters/rss.py` | RSS/Atom feed polling with GUID/link-based duplicate detection |
| **main.py Multi-Source** | `main.py` | Wired multi-source pipeline with type-safe ingester/parser lists |

### Phase 5a: Gamma Discovery Layer (Isolated)

| Component | File | Description |
|-----------|------|-------------|
| **MarketCriteria** | `src/discovery/models.py` | Search parameters (tags, min_volume, min_liquidity, keywords, active_only) |
| **DiscoveryResult** | `src/discovery/models.py` | Normalized market with invariants (market_id/token_id never None/empty) |
| **RuleTemplate** | `src/discovery/models.py` | Template for auto-generating ThresholdRules from discoveries |
| **DiscoveryStrategy** | `src/discovery/models.py` | Named strategy combining criteria + rule template + limits |
| **GammaClient** | `src/discovery/client.py` | Async HTTP client with pagination, retry, exponential backoff, rate limiting |
| **DiscoveryError hierarchy** | `src/exceptions.py` | `GammaAPIError`, `GammaRateLimitError`, `GammaServerError` |

**Methodology:** Middle-Out engineering (isolated from orchestrator), TDD Red-Green-Refactor.

### Phase 5b: SubscriptionManager (Orchestrator Bridge)

| Component | File | Description |
|-----------|------|-------------|
| **SubscriptionManager** | `src/managers/subscription.py` | Bridges discovery → orchestrator with automatic subscription |
| **Protocol classes** | `src/managers/subscription.py` | `IngesterProtocol`, `ParserProtocol`, `GammaClientProtocol` for DI |
| **PriceThresholdParser.add_rule()** | `src/parsers/threshold.py` | Runtime rule addition for discovered markets |
| **PriceThresholdParser.has_rule_for_token()** | `src/parsers/threshold.py` | Deduplication check |
| **PolymarketIngester.get_subscribed_tokens()** | `src/ingesters/polymarket.py` | Deduplication check |
| **main.py startup sequence** | `main.py` | 5-phase startup with discovery before orchestrator |

**Features:**
- Strategy-based market discovery at startup
- Automatic ThresholdRule generation from templates
- Deduplication (skips already subscribed/ruled tokens)
- Global and per-strategy subscription limits
- Atomic subscription + rule creation (fail-safe)

### Phase 6: Textual TUI Dashboard

| Component | File | Description |
|-----------|------|-------------|
| **OrchestratorCallback** | `src/callbacks.py` | Protocol for orchestrator event notifications (signal, trade, error, metrics, position) |
| **Orchestrator callbacks** | `src/orchestrator.py` | Added `register_callback()` and emit methods for TUI integration |
| **TuiLogSink** | `src/tui/log_sink.py` | Loguru sink that forwards logs to Textual RichLog widget |
| **StatusHeader** | `src/tui/widgets/header.py` | Connection status indicator and wallet balance display |
| **LiveLogPanel** | `src/tui/widgets/log_panel.py` | RichLog wrapper with auto-scroll |
| **StrategyStatsPanel** | `src/tui/widgets/strategy_stats.py` | Active rules count and live metrics |
| **RecentTradesTable** | `src/tui/widgets/trade_table.py` | DataTable of last N trades |
| **DashboardScreen** | `src/tui/screens/dashboard.py` | 60/40 layout with logs and stats panels |
| **SniperApp** | `src/tui/app.py` | Main Textual App with orchestrator as background worker |
| **Theme** | `src/tui/theme.tcss` | Cypherpunk aesthetic (green/crimson on black) |
| **--tui flag** | `main.py` | Launch TUI mode: `python main.py --tui` |

**Features:**
- Live log streaming via custom loguru sink
- Real-time trade notifications via callbacks
- Metrics dashboard (events, signals, trades)
- Connection status indicator
- Cypherpunk terminal aesthetic
- Graceful shutdown on quit

**Known Issue:**
- CLOB client initialization fails with "Non-hexadecimal digit found" if `.env` private key is missing/malformed
- This is a configuration issue, not a code bug - TUI renders correctly

### Phase 7: General-Purpose Trading System

**Goal:** Evolved Aedes from a reactive event sniper to a full algorithmic trading system with position tracking, portfolio management, and stateful strategies.

**Methodology:** Middle-Out (core domain models → managers → orchestrator integration), TDD Red-Green-Refactor.

#### Phase 7.1: Foundation Models

| Component | File | Description |
|-----------|------|-------------|
| **PositionSide** | `src/models.py` | Enum: LONG, SHORT, FLAT |
| **OrderType** | `src/models.py` | Enum: MARKET, LIMIT, FOK |
| **TimeInForce** | `src/models.py` | Enum: GTC, IOC, FOK |
| **Position** | `src/models.py` | Token position with `unrealized_pnl`, `market_value` computed properties |
| **Order** | `src/models.py` | Enhanced order with `client_order_id`, lifecycle tracking, validation |

#### Phase 7.2: SQLite Persistence

| Component | File | Description |
|-----------|------|-------------|
| **Schema** | `src/persistence/schema.py` | SQL schema: trades, positions, orders tables with indexes |
| **DatabaseManager** | `src/persistence/database.py` | Async SQLite via aiosqlite with CRUD operations |
| **Module restructure** | `src/persistence/__init__.py` | Converted single file to package, exports TradeLogger + DatabaseManager |

#### Phase 7.3: Portfolio Manager

| Component | File | Description |
|-----------|------|-------------|
| **PortfolioManager** | `src/managers/portfolio.py` | Position tracking, cash balance, risk controls |
| **get_balance()** | `src/interfaces/executor.py` | New abstract method for balance fetching |
| **PolymarketExecutor.get_balance()** | `src/executors/polymarket.py` | Implementation via CLOB client |

**Methods:**
- `load_state(executor)` - Hydrate positions from DB, fetch cash from exchange
- `check_order(order)` - Risk validation (cash, position, max positions)
- `on_fill(order, result)` - Update positions after execution
- `on_price_update(token_id, price)` - Mark-to-market updates

#### Phase 7.4: Strategy Interface

| Component | File | Description |
|-----------|------|-------------|
| **BaseStrategy** | `src/interfaces/strategy.py` | Stateful strategy ABC with on_tick/on_fill/generate_signals |
| **ParserStrategyAdapter** | `src/strategies/parser_adapter.py` | Wraps existing parsers as strategies for backward compatibility |

**Strategy Lifecycle:**
1. `on_tick(event)` - Process market event, update internal state
2. `generate_signals()` - Return list of Order objects to execute
3. `on_fill(order, result)` - React to filled orders
4. `reset()` - Clear internal state

#### Phase 7.5: Orchestrator Integration

| Component | File | Description |
|-----------|------|-------------|
| **Extended constructor** | `src/orchestrator.py` | Added `strategies`, `portfolio`, `database` parameters |
| **Strategy processing** | `src/orchestrator.py` | New `_process_with_strategies()` for Phase 7 flow |
| **Portfolio validation** | `src/orchestrator.py` | Orders validated via `portfolio.check_order()` before execution |
| **Dual persistence** | `src/orchestrator.py` | Persist to both SQLite and JSONL |

**Phase 7 Event Flow:**
1. Update portfolio prices on MarketEvent
2. Call `strategy.on_tick()` for all strategies
3. Collect orders from `strategy.generate_signals()`
4. Validate via `portfolio.check_order()`
5. Execute valid orders
6. Call `strategy.on_fill()` and `portfolio.on_fill()`
7. Persist to database AND JSONL

#### Phase 7.6: TUI Position Panel

| Component | File | Description |
|-----------|------|-------------|
| **PositionsPanel** | `src/tui/widgets/positions.py` | DataTable with Token, Side, Qty, Entry, Current, PnL |
| **on_position_updated** | `src/callbacks.py` | New callback method for position changes |
| **TuiCallback extension** | `src/tui/app.py` | Implements on_position_updated |

**Backward Compatibility:**
- Existing parsers automatically wrapped via `ParserStrategyAdapter`
- JSONL logger retained alongside SQLite
- `TradeSignal` still used internally for legacy path
- Orchestrator accepts legacy constructor arguments
- All 204 existing tests continue to pass

---

## Architecture

```
┌───────────────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR (N:N Multi-Source + Strategies)            │
│  (Merges ingesters → evaluates with strategies/parsers → executes)        │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  INGESTERS                    STRATEGIES/PARSERS          EXECUTOR         │
│  ┌──────────────────┐        ┌─────────────────┐       ┌──────────────┐   │
│  │PolymarketIngester│──┐     │ BaseStrategy    │       │Polymarket    │   │
│  │(MarketData)      │  │     │ (Phase 7)       │       │Executor      │   │
│  └──────────────────┘  │     └────────┬────────┘       └──────────────┘   │
│  ┌──────────────────┐  │  Queue       │                       │           │
│  │RssIngester       │──┼─────▶ Event ─┼─▶ Order ─────────────▶│           │
│  │(RSS/Atom feeds)  │  │              │     ▲                 ▼           │
│  └──────────────────┘  │     ┌────────┴────────┐       ┌──────────────┐   │
│  ┌──────────────────┐  │     │ParserStrategy   │       │ TradeLogger  │   │
│  │ManualEventIngester│─┘     │Adapter (legacy) │       │ (JSONL)      │   │
│  │(Testing/GodMode) │        └─────────────────┘       └──────────────┘   │
│  └──────────────────┘                                  ┌──────────────┐   │
│                                                        │DatabaseManager│   │
│                                                        │ (SQLite)     │   │
│                                                        └──────────────┘   │
└───────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────┐
│                    PORTFOLIO MANAGER (Phase 7 - Risk Controls)             │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────┐    │
│  │ check_order()   │───▶│ Position Dict   │───▶│   DatabaseManager   │    │
│  │ (Risk Validation│    │ (In-Memory)     │    │   (Persistence)     │    │
│  └─────────────────┘    └─────────────────┘    └─────────────────────┘    │
│         │                       │                        │                 │
│    Cash check             Quantity check            on_fill() →           │
│    Max positions          Mark-to-market            upsert_position()     │
│                                                                            │
└───────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────┐
│                    DISCOVERY LAYER (Phase 5a - Isolated)                   │
├───────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────────┐  │
│  │ MarketCriteria  │────▶│   GammaClient   │────▶│  DiscoveryResult[]  │  │
│  │ (Search Params) │     │ (HTTP + Retry)  │     │  (Normalized Data)  │  │
│  └─────────────────┘     └─────────────────┘     └─────────────────────┘  │
│         │                        │                         │               │
│  tags, volume,          gamma-api.polymarket.com          market_id,      │
│  liquidity, keywords    /events + pagination              token_id,       │
│                         429/5xx retry + backoff           volume, tags    │
└───────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────┐
│               SUBSCRIPTION MANAGER (Phase 5b - Orchestrator Bridge)        │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌──────────────────┐    ┌─────────────────────┐    ┌──────────────────┐  │
│  │DiscoveryStrategy │───▶│SubscriptionManager  │───▶│  Orchestrator    │  │
│  │ + RuleTemplate   │    │  (Startup Phase 3)  │    │  (Live Trading)  │  │
│  └──────────────────┘    └─────────────────────┘    └──────────────────┘  │
│                                   │                                        │
│                    ┌──────────────┼──────────────┐                        │
│                    ▼              ▼              ▼                        │
│             ┌───────────┐  ┌───────────┐  ┌───────────┐                   │
│             │ Ingester  │  │  Parser   │  │ Dedup +   │                   │
│             │.subscribe │  │.add_rule  │  │ Limits    │                   │
│             └───────────┘  └───────────┘  └───────────┘                   │
│                                                                            │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## Test Coverage

| Test File | Count | Coverage |
|-----------|-------|----------|
| `test_execution.py` | 33 | Executor validation, price bounds |
| `test_ingestion.py` | 18 | WebSocket parsing, reconnection |
| `test_parsing.py` | 14 | Threshold crossing, cooldowns, dynamic rules |
| `test_orchestrator.py` | 12 | Pipeline integration, multi-ingester/parser |
| `test_persistence.py` | 11 | TradeLogger JSONL output |
| `test_external_ingester.py` | 12 | ManualEventIngester |
| `test_keyword_parser.py` | 14 | Keyword matching, signals |
| `test_event_sniping.py` | 5 | Full pipeline integration |
| `test_rss_ingester.py` | 14 | RSS polling, deduplication |
| `test_gamma_discovery.py` | 41 | MarketCriteria, DiscoveryResult, GammaClient (Phase 5a) |
| `test_subscription_manager.py` | 15 | SubscriptionManager, dedup, atomicity (Phase 5b) |
| `test_tui/test_callbacks.py` | 8 | OrchestratorCallback protocol, callback invocation (Phase 6) |
| `test_tui/test_log_sink.py` | 7 | TuiLogSink, loguru integration (Phase 6) |
| `test_tui/test_positions_panel.py` | 6 | PositionsPanel widget, on_position_updated (Phase 7) |
| `test_models_phase7.py` | 32 | Position, Order, PnL calculations (Phase 7) |
| `test_database.py` | 17 | DatabaseManager CRUD, concurrent access (Phase 7) |
| `test_portfolio_manager.py` | 21 | PortfolioManager risk controls, fills (Phase 7) |
| `test_strategy.py` | 13 | BaseStrategy, ParserStrategyAdapter (Phase 7) |
| `test_orchestrator_phase7.py` | 10 | Orchestrator with strategies/portfolio (Phase 7) |
| **Total** | **303** | |

---

## Key Design Decisions

### 1. Interface Hierarchy
```python
BaseIngester (ABC)
├── connect(), disconnect(), stream(), is_connected
├── MarketDataIngester
│   └── subscribe(token_ids)  # For Polymarket
└── ExternalEventIngester
    └── configure(sources)    # For News/Social
    └── inject_event()        # For testing/God Mode
```

### 2. Deferred Subscription
```python
# Can configure before connect - tokens stored and sent on connect
await ingester.subscribe(["token_123"])
await ingester.connect()  # Sends subscription automatically
```

### 3. Non-blocking Persistence
```python
# Uses aiofiles to avoid blocking the event loop
async with aiofiles.open(filepath, "a") as f:
    await f.write(json.dumps(record) + "\n")
```

### 4. Fail-safe Logging
```python
# IO errors logged but don't crash the bot
try:
    await f.write(...)
except OSError as e:
    logger.error("Failed to persist: {}", e)
    # Trading continues
```

### 5. Multi-Source Queue Merging (Phase 4)
```python
# Multiple ingesters push to shared queue
async def _forward_stream(self, ingester):
    async for event in ingester.stream():
        await self._event_queue.put(event)

# Main loop consumes from queue
while self._is_running:
    event = await self._event_queue.get()
    await self._process_event(event)
```

### 6. Multi-Parser Evaluation (Phase 4)
```python
# Each event evaluated by ALL parsers
for parser in self._parsers:
    signal = parser.evaluate(event)
    if signal:
        result = await self._executor.execute(signal)
```

### 7. Backward Compatible API (Phase 4)
```python
# Legacy API still works
Orchestrator(ingester, parser, executor)

# New multi-source API
Orchestrator(
    ingesters=[poly_ingester, rss_ingester],
    parsers=[price_parser, keyword_parser],
    executor=executor,
)
```

### 8. Gamma Discovery - Isolated Layer (Phase 5)
```python
# Standalone discovery service - no orchestrator imports
from src.discovery import GammaClient, MarketCriteria, DiscoveryResult

async with GammaClient() as client:
    criteria = MarketCriteria(
        tags=["crypto", "politics"],
        min_volume=10000.0,
        keywords=["Bitcoin", "Trump"],
    )
    results = await client.discover(criteria, limit=50)

    # Or stream for memory efficiency
    async for result in client.discover_stream(criteria):
        print(result.market_id, result.token_id, result.title)
```

### 9. Invariant Enforcement (Phase 5)
```python
# Pydantic min_length=1 ensures market_id/token_id never None or empty
class DiscoveryResult(BaseModel):
    market_id: str = Field(..., min_length=1)  # INVARIANT
    token_id: str = Field(..., min_length=1)   # INVARIANT

# Invalid data rejected at construction time
DiscoveryResult(market_id="", ...)  # ValidationError!
```

### 10. Exponential Backoff with Rate Limiting (Phase 5a)
```python
# Matches PolymarketIngester pattern
INITIAL_BACKOFF = 1.0   # seconds
MAX_BACKOFF = 60.0      # cap
BACKOFF_MULTIPLIER = 2.0
MIN_REQUEST_INTERVAL = 0.1  # 100ms rate limit

# Retry sequence: 1s → 2s → 4s → 8s → 16s (capped at 60s)
# 429 errors respect Retry-After header when present
```

### 11. Startup Discovery Sequence (Phase 5b)
```python
# main.py 5-phase startup
async def main() -> None:
    # Phase 1: Load Static Configuration
    threshold_rules = load_threshold_rules()
    discovery_strategies = load_discovery_strategies()

    # Phase 2: Initialize Core Components
    poly_ingester = PolymarketIngester()
    price_parser = PriceThresholdParser(threshold_rules)

    # Phase 3: Startup Discovery (BEFORE orchestrator starts)
    if discovery_strategies:
        async with GammaClient() as gamma_client:
            manager = SubscriptionManager(gamma_client, poly_ingester, price_parser)
            discovered = await manager.execute_strategies(discovery_strategies)

    # Phase 4: Assemble Ingesters and Parsers
    # Phase 5: Initialize Executor and Orchestrator
```

### 12. Atomic Subscription + Rule Creation (Phase 5b)
```python
# Subscribe first, add rule only if subscribe succeeds
async def _add_market(self, result: DiscoveryResult, strategy: DiscoveryStrategy) -> bool:
    rule = self._create_rule(result, strategy)

    try:
        await self._ingester.subscribe([result.token_id])
    except Exception:
        return False  # No rule added if subscribe fails

    self._parser.add_rule(rule)  # Only reached if subscribe succeeded
    return True
```

### 13. Protocol-Based Dependency Injection (Phase 5b)
```python
# Protocols allow any compatible implementation
class IngesterProtocol(Protocol):
    async def subscribe(self, token_ids: list[str]) -> None: ...
    def get_subscribed_tokens(self) -> set[str]: ...

class ParserProtocol(Protocol):
    def add_rule(self, rule: ThresholdRule) -> None: ...
    def has_rule_for_token(self, token_id: str) -> bool: ...

# SubscriptionManager accepts any compatible implementation
class SubscriptionManager:
    def __init__(self, client: GammaClientProtocol, ingester: IngesterProtocol, parser: ParserProtocol): ...
```

### 14. Position Model with Computed PnL (Phase 7)
```python
class Position(BaseModel):
    model_config = {"frozen": True}  # Immutable

    token_id: str
    side: PositionSide  # LONG/SHORT/FLAT
    quantity: float
    avg_entry_price: float
    current_price: float

    @property
    def unrealized_pnl(self) -> float:
        if self.side == PositionSide.FLAT:
            return 0.0
        direction = 1.0 if self.side == PositionSide.LONG else -1.0
        return direction * self.quantity * (self.current_price - self.avg_entry_price)

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price
```

### 15. Order Validation Before Execution (Phase 7)
```python
# Portfolio validates orders before execution
def check_order(self, order: Order) -> tuple[bool, str]:
    if order.side == Side.BUY:
        # Check cash sufficiency
        cost = order.quantity * (order.limit_price or 1.0)
        if cost > self._cash_balance:
            return False, f"Insufficient cash: {cost:.2f} > {self._cash_balance:.2f}"

        # Check max positions for new positions
        if order.token_id not in self._positions:
            if len(self._positions) >= self._max_positions:
                return False, f"Max positions reached: {self._max_positions}"

    elif order.side == Side.SELL:
        # Check position sufficiency
        pos = self._positions.get(order.token_id)
        if pos is None or pos.quantity < order.quantity:
            return False, "Insufficient position for sell"

    return True, ""
```

### 16. Strategy Interface with Lifecycle (Phase 7)
```python
class BaseStrategy(ABC):
    @abstractmethod
    def on_tick(self, event: MarketEvent) -> None:
        """Process market event, update internal state."""

    @abstractmethod
    def generate_signals(self) -> list[Order]:
        """Return orders to execute based on current state."""

    @abstractmethod
    def on_fill(self, order: Order, result: ExecutionResult) -> None:
        """React to order fills."""

    @abstractmethod
    def reset(self) -> None:
        """Reset internal state."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy identifier."""
```

### 17. Parser-to-Strategy Adapter (Phase 7)
```python
# Existing parsers wrapped for backward compatibility
class ParserStrategyAdapter(BaseStrategy):
    def __init__(self, parser: BaseParser):
        self._parser = parser
        self._pending_signal: TradeSignal | None = None

    def on_tick(self, event: MarketEvent) -> None:
        signal = self._parser.evaluate(event)
        if signal:
            self._pending_signal = signal

    def generate_signals(self) -> list[Order]:
        if self._pending_signal is None:
            return []

        signal = self._pending_signal
        self._pending_signal = None

        # Convert TradeSignal to Order
        return [Order(
            token_id=signal.token_id,
            side=signal.side,
            quantity=signal.size_usdc / 0.5,  # Estimate
            reason=signal.reason,
        )]
```

### 18. Dual Persistence (Phase 7)
```python
# Orchestrator persists to both SQLite (queries) and JSONL (audit)
async def _execute_order(self, order: Order, strategy: BaseStrategy) -> None:
    result = await self._execute_order_impl(order)

    # Persist to JSONL (audit trail)
    if self._trade_logger:
        await self._trade_logger.log_execution(signal, result)

    # Persist to SQLite (queryable)
    if self._database:
        await self._database.insert_trade(order, result)
```

---

## Future Work (Beyond Phase 7)

### Live External Feeds
- `TwitterIngester` - Twitter/X API streaming
- `WebhookIngester` - Receive HTTP POST webhooks

### Example Strategies
- Mean reversion strategy
- Momentum strategy
- News-driven event strategy
- Arbitrage between markets

### Configuration File Support
Load rules and feeds from YAML/JSON instead of hardcoding in main.py

### Enhanced Position Management
- Stop-loss orders
- Take-profit targets
- Position sizing algorithms
- Risk-adjusted order sizing

---

## Quick Reference

### Running the Bot
```bash
cd poly-event-sniper
uv sync
cp .env.example .env  # Fill in credentials
uv run python main.py  # Dry-run mode by default
uv run python main.py --tui  # TUI mode
```

### Running Tests
```bash
uv run pytest -v           # All tests
uv run pytest -v -k keyword # Just keyword tests
uv run mypy src/ main.py   # Type checking
```

### Testing Event Sniping (Manual)
```python
from src.ingesters.external import ManualEventIngester
from src.parsers.keyword import KeywordParser, KeywordRule

# Create test ingester
ingester = ManualEventIngester()
await ingester.connect()

# Inject test event
await ingester.inject_event("FED HIKE announced", source="test")

# Events flow through stream() to orchestrator
```

### Testing RSS Ingestion
```python
from src.ingesters.rss import RssIngester

# Create RSS ingester
rss = RssIngester(poll_interval=60.0)
await rss.configure(["https://example.com/feed.xml"])
await rss.connect()

# Events flow through stream() as new entries appear
async for event in rss.stream():
    print(event.content, event.source)
```

### Testing Gamma Discovery (Phase 5a)
```python
from src.discovery import GammaClient, MarketCriteria

async with GammaClient() as client:
    # Discover crypto markets with volume > $10k
    criteria = MarketCriteria(
        tags=["crypto"],
        min_volume=10000.0,
        active_only=True,
    )

    # Get up to 10 results
    results = await client.discover(criteria, limit=10)

    for r in results:
        print(f"{r.market_id}: {r.title} (${r.volume:,.0f})")
```

### Testing SubscriptionManager (Phase 5b)
```python
from src.discovery import GammaClient, MarketCriteria, DiscoveryStrategy, RuleTemplate
from src.managers import SubscriptionManager
from src.ingesters.polymarket import PolymarketIngester
from src.parsers.threshold import PriceThresholdParser

# Define a discovery strategy
strategy = DiscoveryStrategy(
    name="crypto_dips",
    criteria=MarketCriteria(tags=["crypto"], min_volume=50000.0),
    rule_template=RuleTemplate(
        trigger_side="BUY",
        threshold=0.20,
        comparison="below",
        size_usdc=25.0,
    ),
    max_markets=5,
)

# Execute at startup
async with GammaClient() as client:
    manager = SubscriptionManager(client, ingester, parser, global_limit=50)
    count = await manager.execute_strategies([strategy])
    print(f"Auto-subscribed to {count} markets")
```

### Testing PortfolioManager (Phase 7)
```python
from src.managers import PortfolioManager
from src.persistence import DatabaseManager
from pathlib import Path

async with DatabaseManager(Path("data/trading.db")) as db:
    portfolio = PortfolioManager(database=db)
    await portfolio.load_state(executor)

    # Check order validation
    order = Order(token_id="token_123", side=Side.BUY, quantity=100.0, ...)
    is_valid, reason = portfolio.check_order(order)

    if is_valid:
        result = await executor.execute_order(order)
        await portfolio.on_fill(order, result)

    # View positions
    for token_id, pos in portfolio.positions.items():
        print(f"{token_id}: {pos.quantity} @ {pos.avg_entry_price} (PnL: {pos.unrealized_pnl})")
```

### Testing Strategy Interface (Phase 7)
```python
from src.interfaces.strategy import BaseStrategy
from src.strategies.parser_adapter import ParserStrategyAdapter
from src.parsers.threshold import PriceThresholdParser

# Wrap existing parser as strategy
parser = PriceThresholdParser(rules)
strategy = ParserStrategyAdapter(parser)

# Use in orchestrator
orchestrator = Orchestrator(
    ingesters=[ingester],
    strategies=[strategy],
    executor=executor,
    portfolio=portfolio,
)
```

### Trade Log Location
```
data/trades_2025-12-26.jsonl  # JSONL audit trail
data/trading.db               # SQLite database (Phase 7)
```

Format (JSONL):
```json
{"logged_at": 1703347200.0, "signal": {...}, "result": {...}}
```

---

## Files Changed

```
src/
├── models.py              # EventType, MarketEvent, Position, Order, enums (Phase 7)
├── orchestrator.py        # Multi-ingester/parser/strategy support, portfolio (Phase 7)
├── callbacks.py           # OrchestratorCallback + on_position_updated (Phase 7)
├── exceptions.py          # DiscoveryError hierarchy (Phase 5a)
├── interfaces/
│   ├── ingester.py        # Split into 3 classes
│   ├── executor.py        # Added get_balance() (Phase 7)
│   └── strategy.py        # NEW: BaseStrategy ABC (Phase 7)
├── ingesters/
│   ├── polymarket.py      # Deferred subscription, get_subscribed_tokens()
│   ├── external.py        # ManualEventIngester
│   └── rss.py             # RssIngester (Phase 4)
├── executors/
│   └── polymarket.py      # Added get_balance() (Phase 7)
├── parsers/
│   ├── threshold.py       # add_rule(), has_rule_for_token()
│   └── keyword.py         # KeywordParser
├── discovery/             # Phase 5a - Isolated Discovery Layer
│   ├── __init__.py
│   ├── models.py          # MarketCriteria, DiscoveryResult, RuleTemplate, DiscoveryStrategy
│   └── client.py          # GammaClient
├── managers/              # Phase 5b + Phase 7 - Managers
│   ├── __init__.py        # Re-exports: SubscriptionManager, PortfolioManager
│   ├── subscription.py    # SubscriptionManager
│   └── portfolio.py       # NEW: PortfolioManager (Phase 7)
├── persistence/           # REFACTORED: Package (Phase 7)
│   ├── __init__.py        # Re-exports: TradeLogger, DatabaseManager
│   ├── trade_logger.py    # TradeLogger (moved from persistence.py)
│   ├── schema.py          # NEW: SQL schema (Phase 7)
│   └── database.py        # NEW: DatabaseManager (Phase 7)
├── strategies/            # NEW: Phase 7 - Strategy Implementations
│   ├── __init__.py        # Re-exports: ParserStrategyAdapter
│   └── parser_adapter.py  # ParserStrategyAdapter
└── tui/                   # Phase 6 + Phase 7 - Textual TUI Dashboard
    ├── __init__.py
    ├── app.py             # AedesApp + TuiCallback (Phase 7: on_position_updated)
    ├── log_sink.py
    ├── theme.tcss
    ├── screens/
    │   ├── __init__.py
    │   └── dashboard.py
    └── widgets/
        ├── __init__.py    # Added PositionsPanel export (Phase 7)
        ├── header.py
        ├── log_panel.py
        ├── strategy_stats.py
        ├── trade_table.py
        └── positions.py   # NEW: PositionsPanel (Phase 7)

tests/
├── test_persistence.py
├── test_external_ingester.py
├── test_keyword_parser.py
├── test_event_sniping.py
├── test_orchestrator.py
├── test_rss_ingester.py
├── test_gamma_discovery.py
├── test_subscription_manager.py
├── test_models_phase7.py       # NEW: 32 tests (Phase 7)
├── test_database.py            # NEW: 17 tests (Phase 7)
├── test_portfolio_manager.py   # NEW: 21 tests (Phase 7)
├── test_strategy.py            # NEW: 13 tests (Phase 7)
├── test_orchestrator_phase7.py # NEW: 10 tests (Phase 7)
├── test_tui/
│   ├── __init__.py
│   ├── test_callbacks.py
│   ├── test_log_sink.py
│   └── test_positions_panel.py # NEW: 6 tests (Phase 7)
└── test_*.py

main.py                    # --tui flag, 5-phase startup with discovery
pyproject.toml             # Added aiofiles, feedparser, textual, aiosqlite
```

---

## Dependencies Added

```toml
# Phase 1-3
aiofiles = "^25.1.0"
types-aiofiles = "^25.1.0"  # dev dependency

# Phase 4
feedparser = "^6.0.12"

# Phase 6
textual = "^6.11.0"

# Phase 7
aiosqlite = "^0.20.0"
```
