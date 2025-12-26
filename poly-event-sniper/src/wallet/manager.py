"""Wallet management with secure keystore storage.

Uses Ethereum's Web3 Secret Storage (keystore) format for encrypted wallet storage.
This is the same format used by MetaMask, Geth, and other Ethereum wallets.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eth_account import Account
from eth_account.signers.local import LocalAccount
from loguru import logger


@dataclass
class Wallet:
    """Represents an unlocked wallet ready for use."""

    name: str
    address: str
    private_key: str  # Hex string with 0x prefix

    @property
    def short_address(self) -> str:
        """Return shortened address for display (0x1234...5678)."""
        return f"{self.address[:6]}...{self.address[-4:]}"


class WalletManager:
    """Manages wallet creation, storage, and retrieval.

    Wallets are stored in Ethereum keystore format (encrypted JSON files).
    Each wallet file is named by its address and contains encrypted private key.

    Usage:
        manager = WalletManager()

        # Create new wallet
        wallet = manager.create_wallet("trading_bot", "my_password")
        print(f"Deposit address: {wallet.address}")

        # List wallets
        for addr in manager.list_wallets():
            print(addr)

        # Load wallet
        wallet = manager.load_wallet("0x123...", "my_password")

        # Export private key (for MetaMask import)
        print(wallet.private_key)
    """

    DEFAULT_WALLET_DIR = Path("data/wallets")

    def __init__(self, wallet_dir: Path | None = None) -> None:
        """Initialize wallet manager.

        Args:
            wallet_dir: Directory to store wallet keystores.
                       Defaults to data/wallets/
        """
        self._wallet_dir = wallet_dir or self.DEFAULT_WALLET_DIR
        self._wallet_dir.mkdir(parents=True, exist_ok=True)
        self._active_wallet: Wallet | None = None

    @property
    def wallet_dir(self) -> Path:
        """Get the wallet storage directory."""
        return self._wallet_dir

    @property
    def active_wallet(self) -> Wallet | None:
        """Get the currently active wallet."""
        return self._active_wallet

    def create_wallet(self, name: str, password: str) -> Wallet:
        """Create a new wallet with encrypted keystore.

        Args:
            name: Human-readable name for the wallet.
            password: Password to encrypt the keystore.

        Returns:
            The created Wallet object (unlocked).

        Raises:
            ValueError: If password is too short.
        """
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters")

        # Generate new account
        account: LocalAccount = Account.create()

        # Create keystore (encrypted)
        keystore = account.encrypt(password)

        # Add metadata
        keystore["name"] = name

        # Save to file
        keystore_path = self._wallet_dir / f"{account.address.lower()}.json"
        with open(keystore_path, "w") as f:
            json.dump(keystore, f, indent=2)

        logger.info("Created new wallet: {} ({})", name, account.address)

        # Ensure private key has 0x prefix
        private_key_hex = account.key.hex()
        if not private_key_hex.startswith("0x"):
            private_key_hex = f"0x{private_key_hex}"

        wallet = Wallet(
            name=name,
            address=account.address,
            private_key=private_key_hex,
        )

        # Set as active
        self._active_wallet = wallet

        return wallet

    def list_wallets(self) -> list[dict[str, str]]:
        """List all stored wallets.

        Returns:
            List of dicts with 'address' and 'name' keys.
        """
        wallets = []
        for keystore_file in self._wallet_dir.glob("0x*.json"):
            try:
                with open(keystore_file) as f:
                    keystore = json.load(f)
                    # Ensure address has 0x prefix
                    addr = keystore.get("address", "").lower()
                    if not addr.startswith("0x"):
                        addr = f"0x{addr}"
                    wallets.append({
                        "address": addr,
                        "name": keystore.get("name", "unnamed"),
                    })
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Failed to read keystore {}: {}", keystore_file, e)

        return wallets

    def has_wallets(self) -> bool:
        """Check if any wallets exist."""
        return len(self.list_wallets()) > 0

    def load_wallet(self, address: str, password: str) -> Wallet:
        """Load and unlock a wallet by address.

        Args:
            address: Wallet address (with or without 0x prefix).
            password: Password to decrypt the keystore.

        Returns:
            The unlocked Wallet object.

        Raises:
            FileNotFoundError: If wallet doesn't exist.
            ValueError: If password is incorrect.
        """
        # Normalize address
        if not address.startswith("0x"):
            address = f"0x{address}"
        address = address.lower()

        keystore_path = self._wallet_dir / f"{address}.json"
        if not keystore_path.exists():
            raise FileNotFoundError(f"Wallet not found: {address}")

        with open(keystore_path) as f:
            keystore: dict[str, Any] = json.load(f)

        try:
            private_key_bytes = Account.decrypt(keystore, password)
        except ValueError as e:
            raise ValueError(f"Invalid password: {e}") from e

        name = keystore.get("name", "unnamed")

        # Ensure private key has 0x prefix
        private_key_hex = private_key_bytes.hex()
        if not private_key_hex.startswith("0x"):
            private_key_hex = f"0x{private_key_hex}"

        wallet = Wallet(
            name=name,
            address=f"0x{keystore['address']}",
            private_key=private_key_hex,
        )

        # Set as active
        self._active_wallet = wallet

        logger.info("Loaded wallet: {} ({})", name, wallet.short_address)

        return wallet

    def delete_wallet(self, address: str) -> bool:
        """Delete a wallet keystore file.

        Args:
            address: Wallet address to delete.

        Returns:
            True if deleted, False if not found.
        """
        if not address.startswith("0x"):
            address = f"0x{address}"
        address = address.lower()

        keystore_path = self._wallet_dir / f"{address}.json"
        if keystore_path.exists():
            keystore_path.unlink()
            logger.info("Deleted wallet: {}", address)

            # Clear active if this was it
            if self._active_wallet and self._active_wallet.address.lower() == address:
                self._active_wallet = None

            return True

        return False

    def export_private_key(self, address: str, password: str) -> str:
        """Export private key for a wallet (for MetaMask import).

        Args:
            address: Wallet address.
            password: Password to decrypt.

        Returns:
            Private key as hex string with 0x prefix.
        """
        wallet = self.load_wallet(address, password)
        return wallet.private_key

    def get_active_private_key(self) -> str | None:
        """Get the private key of the active wallet.

        Returns:
            Private key hex string or None if no active wallet.
        """
        if self._active_wallet:
            return self._active_wallet.private_key
        return None

    def set_active_wallet(self, wallet: Wallet) -> None:
        """Set the active wallet."""
        self._active_wallet = wallet
