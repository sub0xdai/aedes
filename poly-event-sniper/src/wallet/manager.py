"""Wallet management with simple JSON storage.

Stores wallets as plain JSON files with name, address, and private key.
This is appropriate for a local TUI application where file system access
implies full access to the wallet anyway.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eth_account import Account
from eth_account.signers.local import LocalAccount
from loguru import logger


@dataclass
class Wallet:
    """Represents a wallet ready for use."""

    name: str
    address: str
    private_key: str  # Hex string with 0x prefix

    @property
    def short_address(self) -> str:
        """Return shortened address for display (0x1234...5678)."""
        return f"{self.address[:6]}...{self.address[-4:]}"


class WalletManager:
    """Manages wallet creation, storage, and retrieval.

    Wallets are stored as simple JSON files with name, address, and private key.
    Each wallet file is named by its address.

    Usage:
        manager = WalletManager()

        # Create new wallet
        wallet = manager.create_wallet("trading_bot")
        print(f"Deposit address: {wallet.address}")

        # List wallets
        for addr in manager.list_wallets():
            print(addr)

        # Load wallet
        wallet = manager.load_wallet("0x123...")

        # Export private key (for MetaMask import)
        print(wallet.private_key)
    """

    DEFAULT_WALLET_DIR = Path("data/wallets")

    def __init__(self, wallet_dir: Path | None = None) -> None:
        """Initialize wallet manager.

        Args:
            wallet_dir: Directory to store wallet files.
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

    def create_wallet(self, name: str) -> Wallet:
        """Create a new wallet.

        Args:
            name: Human-readable name for the wallet.

        Returns:
            The created Wallet object.
        """
        # Generate new account
        account: LocalAccount = Account.create()

        # Ensure private key has 0x prefix
        private_key_hex = account.key.hex()
        if not private_key_hex.startswith("0x"):
            private_key_hex = f"0x{private_key_hex}"

        # Create wallet data
        wallet_data = {
            "name": name,
            "address": account.address,
            "private_key": private_key_hex,
        }

        # Save to file
        wallet_path = self._wallet_dir / f"{account.address.lower()}.json"
        with open(wallet_path, "w") as f:
            json.dump(wallet_data, f, indent=2)

        logger.info("Created new wallet: {} ({})", name, account.address)

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
        for wallet_file in self._wallet_dir.glob("0x*.json"):
            try:
                with open(wallet_file) as f:
                    data = json.load(f)
                    # Handle both new format and legacy keystore format
                    addr = data.get("address", "").lower()
                    if not addr.startswith("0x"):
                        addr = f"0x{addr}"
                    wallets.append({
                        "address": addr,
                        "name": data.get("name", "unnamed"),
                    })
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Failed to read wallet {}: {}", wallet_file, e)

        return wallets

    def has_wallets(self) -> bool:
        """Check if any wallets exist."""
        return len(self.list_wallets()) > 0

    def load_wallet(self, address: str) -> Wallet:
        """Load a wallet by address.

        Args:
            address: Wallet address (with or without 0x prefix).

        Returns:
            The Wallet object.

        Raises:
            FileNotFoundError: If wallet doesn't exist.
        """
        # Normalize address
        if not address.startswith("0x"):
            address = f"0x{address}"
        address = address.lower()

        wallet_path = self._wallet_dir / f"{address}.json"
        if not wallet_path.exists():
            raise FileNotFoundError(f"Wallet not found: {address}")

        with open(wallet_path) as f:
            data: dict[str, Any] = json.load(f)

        # Handle both new format and legacy keystore format
        if "private_key" in data:
            # New simple format
            private_key_hex = data["private_key"]
            name = data.get("name", "unnamed")
            wallet_address = data.get("address", address)
        elif "crypto" in data or "Crypto" in data:
            # Legacy encrypted keystore - cannot load without password
            raise ValueError(
                "Legacy encrypted wallet found. Please re-import using private key."
            )
        else:
            raise ValueError("Invalid wallet file format")

        # Ensure address has 0x prefix
        if not wallet_address.startswith("0x"):
            wallet_address = f"0x{wallet_address}"

        wallet = Wallet(
            name=name,
            address=wallet_address,
            private_key=private_key_hex,
        )

        # Set as active
        self._active_wallet = wallet

        logger.info("Loaded wallet: {} ({})", name, wallet.short_address)

        return wallet

    def delete_wallet(self, address: str) -> bool:
        """Delete a wallet file.

        Args:
            address: Wallet address to delete.

        Returns:
            True if deleted, False if not found.
        """
        if not address.startswith("0x"):
            address = f"0x{address}"
        address = address.lower()

        wallet_path = self._wallet_dir / f"{address}.json"
        if wallet_path.exists():
            wallet_path.unlink()
            logger.info("Deleted wallet: {}", address)

            # Clear active if this was it
            if self._active_wallet and self._active_wallet.address.lower() == address:
                self._active_wallet = None

            return True

        return False

    def export_private_key(self, address: str) -> str:
        """Export private key for a wallet (for MetaMask import).

        Args:
            address: Wallet address.

        Returns:
            Private key as hex string with 0x prefix.
        """
        wallet = self.load_wallet(address)
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

    def wallet_exists(self, address: str) -> bool:
        """Check if a wallet with the given address already exists.

        Args:
            address: Ethereum address (with or without 0x prefix).

        Returns:
            True if wallet exists, False otherwise.
        """
        # Normalize to lowercase first to handle 0X prefix
        address = address.lower()
        if not address.startswith("0x"):
            address = f"0x{address}"

        wallet_path = self._wallet_dir / f"{address}.json"
        return wallet_path.exists()

    def import_from_private_key(
        self, private_key: str, name: str | None = None
    ) -> Wallet:
        """Import wallet from a raw private key.

        Args:
            private_key: Hex private key (with or without 0x prefix).
            name: Optional name for the wallet.

        Returns:
            The imported Wallet object.

        Raises:
            ValueError: If private key is invalid.
            ValueError: If wallet with same address already exists.
        """
        # Normalize key - add 0x if missing
        if not private_key.startswith("0x"):
            private_key = f"0x{private_key}"

        # Validate key format (should be 0x + 64 hex chars)
        if len(private_key) != 66:
            raise ValueError("Private key must be 64 hex characters (with 0x prefix)")

        try:
            int(private_key, 16)
        except ValueError as e:
            raise ValueError("Private key must be valid hexadecimal") from e

        # Create account from key
        try:
            account: LocalAccount = Account.from_key(private_key)
        except Exception as e:
            raise ValueError(f"Invalid private key: {e}") from e

        # Check for duplicate
        if self.wallet_exists(account.address):
            raise ValueError(f"Wallet already exists: {account.address}")

        # Generate name if not provided
        if name is None:
            import time
            name = f"imported_{int(time.time())}"

        # Create wallet data
        wallet_data = {
            "name": name,
            "address": account.address,
            "private_key": private_key,
        }

        # Save to file
        wallet_path = self._wallet_dir / f"{account.address.lower()}.json"
        with open(wallet_path, "w") as f:
            json.dump(wallet_data, f, indent=2)

        logger.info("Imported wallet from private key: {} ({})", name, account.address)

        wallet = Wallet(
            name=name,
            address=account.address,
            private_key=private_key,
        )

        self._active_wallet = wallet
        return wallet

    def import_from_keystore(
        self, keystore_path: Path | str, password: str, name: str | None = None
    ) -> Wallet:
        """Import wallet from an existing keystore JSON file (MetaMask export).

        Note: Password is still required because MetaMask keystores are encrypted.
        After import, the wallet is stored in our simple unencrypted format.

        Args:
            keystore_path: Path to the JSON keystore file.
            password: Password to decrypt the keystore.
            name: Optional name for the wallet (defaults to original or filename).

        Returns:
            The imported Wallet object.

        Raises:
            FileNotFoundError: If keystore file doesn't exist.
            ValueError: If keystore is invalid or password is wrong.
            ValueError: If wallet with same address already exists.
        """
        keystore_path = Path(keystore_path)
        if not keystore_path.exists():
            raise FileNotFoundError(f"Keystore file not found: {keystore_path}")

        # Load and validate keystore
        try:
            with open(keystore_path) as f:
                keystore: dict[str, Any] = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid keystore JSON: {e}") from e

        # Validate required fields
        if "crypto" not in keystore and "Crypto" not in keystore:
            raise ValueError("Invalid keystore: missing 'crypto' field")
        if "address" not in keystore:
            raise ValueError("Invalid keystore: missing 'address' field")

        # Decrypt to get private key
        try:
            private_key_bytes = Account.decrypt(keystore, password)
        except ValueError as e:
            raise ValueError(f"Wrong password or corrupted keystore: {e}") from e

        # Get address
        address = keystore["address"].lower()
        if not address.startswith("0x"):
            address = f"0x{address}"

        # Check for duplicate
        if self.wallet_exists(address):
            raise ValueError(f"Wallet already exists: {address}")

        # Determine name
        if name is None:
            name = keystore.get("name") or keystore_path.stem

        # Convert to hex
        private_key_hex = f"0x{private_key_bytes.hex()}"
        account = Account.from_key(private_key_hex)

        # Create wallet data (simple format, not encrypted)
        wallet_data = {
            "name": name,
            "address": account.address,
            "private_key": private_key_hex,
        }

        # Save to our wallet directory
        dest_path = self._wallet_dir / f"{address}.json"
        with open(dest_path, "w") as f:
            json.dump(wallet_data, f, indent=2)

        logger.info("Imported wallet from keystore: {} ({})", name, address)

        wallet = Wallet(
            name=name,
            address=account.address,
            private_key=private_key_hex,
        )

        self._active_wallet = wallet
        return wallet

    def generate_qr_code(self, address: str | None = None) -> str:
        """Generate terminal QR code for the given address.

        Args:
            address: Ethereum address to encode. If None, uses active wallet.

        Returns:
            ASCII/Unicode string representation of QR code.

        Raises:
            ValueError: If no address provided and no active wallet.
        """
        if address is None:
            if self._active_wallet is None:
                raise ValueError("No address provided and no active wallet")
            address = self._active_wallet.address

        try:
            import segno
        except ImportError as e:
            raise ImportError("segno package required for QR codes") from e

        import io

        # Create QR with ethereum URI format for wallet compatibility
        uri = f"ethereum:{address}"
        qr = segno.make(uri)

        # Capture terminal output to string
        buffer = io.StringIO()
        qr.terminal(out=buffer, compact=True)
        return buffer.getvalue()
