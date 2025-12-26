"""Tests for wallet manager."""

import json
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.wallet import Wallet, WalletManager


class TestWallet:
    """Tests for Wallet dataclass."""

    def test_wallet_creation(self) -> None:
        """Test basic wallet creation."""
        wallet = Wallet(
            name="test",
            address="0x742d35Cc6634C0532925a3b844Bc9e7595f9211F",
            private_key="0x" + "a" * 64,
        )
        assert wallet.name == "test"
        assert wallet.address.startswith("0x")
        assert wallet.private_key.startswith("0x")

    def test_short_address(self) -> None:
        """Test short address formatting."""
        wallet = Wallet(
            name="test",
            address="0x742d35Cc6634C0532925a3b844Bc9e7595f9211F",
            private_key="0x" + "a" * 64,
        )
        assert wallet.short_address == "0x742d...211F"


class TestWalletManager:
    """Tests for WalletManager."""

    def test_create_wallet(self) -> None:
        """Test wallet creation generates valid address."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))
            wallet = manager.create_wallet("test_wallet", "password123")

            assert wallet.name == "test_wallet"
            assert wallet.address.startswith("0x")
            assert len(wallet.address) == 42
            assert wallet.private_key.startswith("0x")
            assert len(wallet.private_key) == 66  # 0x + 64 hex chars

    def test_create_wallet_saves_keystore(self) -> None:
        """Test wallet creation saves encrypted keystore file."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))
            wallet = manager.create_wallet("test_wallet", "password123")

            keystore_path = Path(tmpdir) / f"{wallet.address.lower()}.json"
            assert keystore_path.exists()

            with open(keystore_path) as f:
                keystore = json.load(f)

            assert keystore["name"] == "test_wallet"
            assert "crypto" in keystore  # Encrypted data
            assert "address" in keystore

    def test_create_wallet_sets_active(self) -> None:
        """Test wallet creation sets it as active."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))
            wallet = manager.create_wallet("test_wallet", "password123")

            assert manager.active_wallet is not None
            assert manager.active_wallet.address == wallet.address

    def test_password_too_short(self) -> None:
        """Test password validation."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))
            with pytest.raises(ValueError, match="at least 8 characters"):
                manager.create_wallet("test", "short")

    def test_list_wallets(self) -> None:
        """Test listing wallets."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))

            # Initially empty
            assert manager.list_wallets() == []
            assert not manager.has_wallets()

            # Create wallets
            wallet1 = manager.create_wallet("wallet1", "password123")
            wallet2 = manager.create_wallet("wallet2", "password456")

            wallets = manager.list_wallets()
            assert len(wallets) == 2
            assert manager.has_wallets()

            addresses = [w["address"] for w in wallets]
            assert wallet1.address.lower() in addresses
            assert wallet2.address.lower() in addresses

    def test_load_wallet(self) -> None:
        """Test loading and unlocking a wallet."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))
            original = manager.create_wallet("test_wallet", "password123")

            # Clear active wallet
            manager._active_wallet = None

            # Load it back
            loaded = manager.load_wallet(original.address, "password123")

            assert loaded.name == original.name
            assert loaded.address == original.address
            assert loaded.private_key == original.private_key

    def test_load_wallet_wrong_password(self) -> None:
        """Test loading with wrong password fails."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))
            wallet = manager.create_wallet("test_wallet", "password123")

            with pytest.raises(ValueError, match="Invalid password"):
                manager.load_wallet(wallet.address, "wrong_password")

    def test_load_wallet_not_found(self) -> None:
        """Test loading non-existent wallet."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))

            with pytest.raises(FileNotFoundError, match="not found"):
                manager.load_wallet("0x0000000000000000000000000000000000000000", "password")

    def test_delete_wallet(self) -> None:
        """Test deleting a wallet."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))
            wallet = manager.create_wallet("test_wallet", "password123")

            assert manager.has_wallets()

            result = manager.delete_wallet(wallet.address)
            assert result is True
            assert not manager.has_wallets()
            assert manager.active_wallet is None

    def test_delete_nonexistent_wallet(self) -> None:
        """Test deleting non-existent wallet returns False."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))

            result = manager.delete_wallet("0x0000000000000000000000000000000000000000")
            assert result is False

    def test_export_private_key(self) -> None:
        """Test exporting private key."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))
            wallet = manager.create_wallet("test_wallet", "password123")

            exported = manager.export_private_key(wallet.address, "password123")
            assert exported == wallet.private_key

    def test_get_active_private_key(self) -> None:
        """Test getting active wallet's private key."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))

            # No active wallet
            assert manager.get_active_private_key() is None

            # Create wallet (becomes active)
            wallet = manager.create_wallet("test_wallet", "password123")
            assert manager.get_active_private_key() == wallet.private_key

    def test_address_normalization(self) -> None:
        """Test address normalization (with/without 0x, case)."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))
            wallet = manager.create_wallet("test_wallet", "password123")

            # Load with lowercase
            loaded1 = manager.load_wallet(wallet.address.lower(), "password123")
            assert loaded1.address.lower() == wallet.address.lower()

            # Load without 0x prefix
            loaded2 = manager.load_wallet(wallet.address[2:], "password123")
            assert loaded2.address.lower() == wallet.address.lower()

    def test_multiple_managers_same_dir(self) -> None:
        """Test multiple managers can access same wallet directory."""
        with TemporaryDirectory() as tmpdir:
            manager1 = WalletManager(Path(tmpdir))
            wallet = manager1.create_wallet("shared_wallet", "password123")

            # New manager instance
            manager2 = WalletManager(Path(tmpdir))
            assert manager2.has_wallets()

            # Load wallet from second manager
            loaded = manager2.load_wallet(wallet.address, "password123")
            assert loaded.private_key == wallet.private_key
