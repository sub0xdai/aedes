"""SQL schema definitions for the SQLite database."""

# Schema version for migrations
SCHEMA_VERSION = 1

# Create tables SQL
CREATE_TRADES_TABLE = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    client_order_id TEXT,
    token_id TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    fees REAL DEFAULT 0,
    executed_at REAL NOT NULL,
    created_at REAL DEFAULT (strftime('%s', 'now'))
);
"""

CREATE_POSITIONS_TABLE = """
CREATE TABLE IF NOT EXISTS positions (
    token_id TEXT PRIMARY KEY,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    avg_entry_price REAL NOT NULL,
    current_price REAL NOT NULL,
    opened_at REAL NOT NULL,
    updated_at REAL DEFAULT (strftime('%s', 'now'))
);
"""

CREATE_ORDERS_TABLE = """
CREATE TABLE IF NOT EXISTS orders (
    client_order_id TEXT PRIMARY KEY,
    token_id TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    order_type TEXT NOT NULL,
    limit_price REAL,
    time_in_force TEXT NOT NULL,
    status TEXT NOT NULL,
    exchange_order_id TEXT,
    reason TEXT,
    created_at REAL NOT NULL,
    updated_at REAL DEFAULT (strftime('%s', 'now'))
);
"""

# Indexes for fast lookups
CREATE_TRADES_TOKEN_INDEX = """
CREATE INDEX IF NOT EXISTS idx_trades_token ON trades(token_id);
"""

CREATE_TRADES_TIME_INDEX = """
CREATE INDEX IF NOT EXISTS idx_trades_time ON trades(executed_at);
"""

CREATE_ORDERS_TOKEN_INDEX = """
CREATE INDEX IF NOT EXISTS idx_orders_token ON orders(token_id);
"""

CREATE_ORDERS_STATUS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
"""

# All schema statements in order
SCHEMA_STATEMENTS = [
    CREATE_TRADES_TABLE,
    CREATE_POSITIONS_TABLE,
    CREATE_ORDERS_TABLE,
    CREATE_TRADES_TOKEN_INDEX,
    CREATE_TRADES_TIME_INDEX,
    CREATE_ORDERS_TOKEN_INDEX,
    CREATE_ORDERS_STATUS_INDEX,
]
