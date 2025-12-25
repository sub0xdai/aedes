"""Persistence layer for the poly-event-sniper trading system.

Provides:
- TradeLogger: Append-only JSONL logging for audit trails
- DatabaseManager: SQLite storage for trades, positions, and orders
"""

from src.persistence.database import DatabaseManager
from src.persistence.trade_logger import TradeLogger

__all__ = ["DatabaseManager", "TradeLogger"]
