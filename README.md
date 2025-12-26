# Aedes Trading Engine

## System Overview

The Aedes Trading Engine is a high-performance, event-driven algorithmic trading system designed for Polymarket. It specializes in information latency arbitrage by programmatically ingesting real-world data feeds and executing positions on the Polymarket CLOB (Central Limit Order Book) prior to market consensus convergence.

The system operates on a low-latency loop:
1.  **Ingestion**: Real-time monitoring of external data sources (government reports, live transcripts, news feeds).
2.  **Analysis**: Instantaneous keyword matching and numeric threshold evaluation against active prediction markets.
3.  **Execution**: Automated order placement via the Polymarket API with strict risk parameters.

## Architecture

The system utilizes a modular Publisher/Subscriber architecture to ensure decoupling between data acquisition and trade execution.

### Data Ingestion Layer
Modular interfaces monitor specific data streams. New sources can be added by implementing the base listener interface.
*   **Government Data Scraper**: Polls official .gov endpoints (e.g., BLS) at high frequency for macroeconomic indicators.
*   **Transcript Stream**: Connects to live captioning services for real-time speech analysis.
*   **RSS/News Watcher**: Monitors high-velocity news feeds for headlines impacting market probabilities.

### Signal Generation Engine
The core logic processor evaluates incoming data against pre-defined trading rules.
*   **Boolean Logic**: Triggers on specific keyword presence or absence.
*   **Numeric Thresholds**: Executes when quantitative data (e.g., CPI, inflation rates) breaches defined bounds.

### Order Execution System
Handles the interaction with the Polymarket Exchange.
*   **Position Sizing**: Dynamically calculates trade size based on risk configuration.
*   **Order Management**: Utilizes FOK (Fill or Kill) Limit Orders to ensure execution certainty without adverse selection.
*   **Latency Optimization**: Direct connection to the Polygon network and Polymarket CLOB for minimal round-trip time.

## Technology Stack

*   **Runtime**: Python 3.11+
*   **Concurrency**: `asyncio` for non-blocking I/O operations.
*   **Networking**: `aiohttp` for asynchronous HTTP requests.
*   **Exchange Integration**: `py-clob-client` (Polymarket SDK).
*   **Data Parsing**: `beautifulsoup4`, `feedparser`, `tweepy`.
*   **Package Management**: `uv`.

## Configuration

The system requires environment-specific configuration via a `.env` file.

```bash
# Network & Authentication
POLYGON_PRIVATE_KEY="<Private Key>"

# Polymarket API Credentials
CLOB_API_KEY="<API Key>"
CLOB_SECRET="<API Secret>"
CLOB_PASSPHRASE="<Passphrase>"

# System Parameters
POLL_INTERVAL=0.5       # Polling frequency in seconds
MAX_SLIPPAGE=0.05       # Maximum allowable price deviation (5%)
```

## Risk Disclosure

This software automates financial transactions based on text parsing and programmatic logic.
*   **False Positives**: Natural language ambiguity may trigger incorrect trade signals.
*   **Execution Risk**: Network latency or API instability can impact order fill rates.
*   **Financial Risk**: Users are solely responsible for all trading activity and financial outcomes. Thorough backtesting and dry-run validation are strongly recommended before live deployment.