# poly-event-sniper: Information Latency Arbitrage Bot

## ⚡ Overview
`poly-event-sniper` is a Python-based execution engine designed to exploit "Real World Latency" in Prediction Markets. 

**The Edge:** Markets resolve based on real-world events (speeches, government data, tweets). Most participants watch video feeds (latency: ~20s) or refresh web UI  to buy the correct outcome before the crowd reacts.

**Core Loop:** `Listen(Source) -> Match(Keyword/Value) -> Execute(Polymarket CLOB)`

## 🛠 Tech Stack
* **Language:** Python 3.11+
* **Concurrency:** `asyncio` (Crucial for waiting on multiple sockets/streams)
* **Web Requests:** `aiohttp` (Async HTTP)
* **Polymarket SDK:** `py-clob-client`
* **Data Parsing:** `beautifulsoup4` (HTML), `feedparser` (RSS), `tweepy` (X/Twitter)
* **Environment:** `uv` 

## 📂 Architecture
The system is built on a **Publisher/Subscriber** model to allow rapid switching of data sources.

### 1. The Watchtower (Data Sources)
Modular "Listeners" that monitor specific feeds.
* `sources/gov_scraper.py`: Polls .gov endpoints (e.g., BLS for inflation data) every 500ms.
* `sources/transcript_stream.py`: Connects to live captioning services (e.g., for speeches).
* `sources/rss_watcher.py`: Long-polling for news headers.

### 2. The Trigger (Logic)
* **Boolean:** `if "recession" in text: buy_yes()`
* **Numeric:** `if cpi_data > 3.2: buy_yes()`

### 3. The Executioner (Trade)
* Pre-calculates position size.
* Uses `py-clob-client` to fire **FOK (Fill or Kill)** Limit Orders.
* *Why Limit?* To avoid getting slippage from other bots. We buy at `Ask + 1%`.


## 🔧 Configuration
Create a `.env` file (DO NOT COMMIT):
```bash
# Wallet
POLYGON_PRIVATE_KEY="0x..."

# Polymarket API
CLOB_API_KEY=""
CLOB_SECRET=""
CLOB_PASSPHRASE=""

# Tuning
POLL_INTERVAL=0.5  # Seconds
MAX_SLIPPAGE=0.05  # 5% max price deviation

⚠️ Risk Warning

This bot executes real financial transactions based on parsing text.

    False Positives: If the target says "I will NOT say Crypto", a naive regex might trigger.

    Logic: Always test regex on past transcripts before live deployment.
