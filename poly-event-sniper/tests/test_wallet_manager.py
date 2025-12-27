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


class TestWalletExists:
    """Tests for wallet_exists method."""

    def test_wallet_exists_true(self) -> None:
        """Test wallet_exists returns True for existing wallet."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))
            wallet = manager.create_wallet("test", "password123")

            assert manager.wallet_exists(wallet.address) is True

    def test_wallet_exists_false(self) -> None:
        """Test wallet_exists returns False for non-existent wallet."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))

            assert manager.wallet_exists("0x0000000000000000000000000000000000000000") is False

    def test_wallet_exists_normalizes_address(self) -> None:
        """Test wallet_exists handles address normalization."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))
            wallet = manager.create_wallet("test", "password123")

            # Without 0x prefix
            assert manager.wallet_exists(wallet.address[2:]) is True
            # Uppercase
            assert manager.wallet_exists(wallet.address.upper()) is True


class TestImportFromPrivateKey:
    """Tests for import_from_private_key method."""

    # Valid test private key (from eth_account docs)
    TEST_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"

    def test_import_from_private_key(self) -> None:
        """Test importing wallet from private key."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))
            wallet = manager.import_from_private_key(self.TEST_KEY, "password123")

            assert wallet.private_key == self.TEST_KEY
            assert wallet.address.startswith("0x")
            assert len(wallet.address) == 42
            assert manager.active_wallet == wallet

    def test_import_from_private_key_without_0x(self) -> None:
        """Test importing handles keys without 0x prefix."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))
            wallet = manager.import_from_private_key(self.TEST_KEY[2:], "password123")

            # Should still normalize to 0x prefix
            assert wallet.private_key == self.TEST_KEY

    def test_import_from_private_key_with_name(self) -> None:
        """Test importing with custom name."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))
            wallet = manager.import_from_private_key(
                self.TEST_KEY, "password123", name="my_wallet"
            )

            assert wallet.name == "my_wallet"

    def test_import_from_private_key_invalid(self) -> None:
        """Test importing invalid key raises ValueError."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))

            with pytest.raises(ValueError, match="64 hex characters"):
                manager.import_from_private_key("0x1234", "password123")

    def test_import_from_private_key_invalid_hex(self) -> None:
        """Test importing non-hex key raises ValueError."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))

            with pytest.raises(ValueError, match="hexadecimal"):
                manager.import_from_private_key("0x" + "g" * 64, "password123")

    def test_import_from_private_key_duplicate(self) -> None:
        """Test importing duplicate address raises ValueError."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))
            manager.import_from_private_key(self.TEST_KEY, "password123")

            with pytest.raises(ValueError, match="already exists"):
                manager.import_from_private_key(self.TEST_KEY, "password456")

    def test_import_from_private_key_short_password(self) -> None:
        """Test importing with short password raises ValueError."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))

            with pytest.raises(ValueError, match="8 characters"):
                manager.import_from_private_key(self.TEST_KEY, "short")


class TestImportFromKeystore:
    """Tests for import_from_keystore method."""

    def test_import_from_keystore(self) -> None:
        """Test importing wallet from keystore file."""
        with TemporaryDirectory() as tmpdir:
            # Create a keystore first
            manager1 = WalletManager(Path(tmpdir) / "source")
            original = manager1.create_wallet("original", "password123")
            keystore_path = Path(tmpdir) / "source" / f"{original.address.lower()}.json"

            # Import into different directory
            manager2 = WalletManager(Path(tmpdir) / "dest")
            imported = manager2.import_from_keystore(keystore_path, "password123")

            assert imported.address == original.address
            assert imported.private_key == original.private_key

    def test_import_from_keystore_custom_name(self) -> None:
        """Test importing keystore with custom name."""
        with TemporaryDirectory() as tmpdir:
            manager1 = WalletManager(Path(tmpdir) / "source")
            original = manager1.create_wallet("original", "password123")
            keystore_path = Path(tmpdir) / "source" / f"{original.address.lower()}.json"

            manager2 = WalletManager(Path(tmpdir) / "dest")
            imported = manager2.import_from_keystore(
                keystore_path, "password123", name="renamed"
            )

            assert imported.name == "renamed"

    def test_import_from_keystore_not_found(self) -> None:
        """Test importing non-existent keystore raises FileNotFoundError."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))

            with pytest.raises(FileNotFoundError, match="not found"):
                manager.import_from_keystore("/nonexistent/file.json", "password")

    def test_import_from_keystore_wrong_password(self) -> None:
        """Test importing with wrong password raises ValueError."""
        with TemporaryDirectory() as tmpdir:
            manager1 = WalletManager(Path(tmpdir) / "source")
            original = manager1.create_wallet("original", "password123")
            keystore_path = Path(tmpdir) / "source" / f"{original.address.lower()}.json"

            manager2 = WalletManager(Path(tmpdir) / "dest")
            with pytest.raises(ValueError, match="Wrong password"):
                manager2.import_from_keystore(keystore_path, "wrong_password")

    def test_import_from_keystore_duplicate(self) -> None:
        """Test importing duplicate address raises ValueError."""
        with TemporaryDirectory() as tmpdir:
            manager1 = WalletManager(Path(tmpdir) / "source")
            original = manager1.create_wallet("original", "password123")
            keystore_path = Path(tmpdir) / "source" / f"{original.address.lower()}.json"

            manager2 = WalletManager(Path(tmpdir) / "dest")
            manager2.import_from_keystore(keystore_path, "password123")

            with pytest.raises(ValueError, match="already exists"):
                manager2.import_from_keystore(keystore_path, "password123")

    def test_import_from_keystore_invalid_json(self) -> None:
        """Test importing invalid JSON raises ValueError."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))

            # Create invalid JSON file
            invalid_path = Path(tmpdir) / "invalid.json"
            with open(invalid_path, "w") as f:
                f.write("not json")

            with pytest.raises(ValueError, match="Invalid keystore JSON"):
                manager.import_from_keystore(invalid_path, "password")

    def test_import_from_keystore_missing_crypto(self) -> None:
        """Test importing keystore without crypto field raises ValueError."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))

            # Create JSON without crypto field
            invalid_path = Path(tmpdir) / "invalid.json"
            with open(invalid_path, "w") as f:
                json.dump({"address": "0x123"}, f)

            with pytest.raises(ValueError, match="missing 'crypto' field"):
                manager.import_from_keystore(invalid_path, "password")


class TestGenerateQRCode:
    """Tests for generate_qr_code method."""

    def test_generate_qr_code(self) -> None:
        """Test QR code generation returns string."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))
            wallet = manager.create_wallet("test", "password123")

            qr = manager.generate_qr_code(wallet.address)

            assert isinstance(qr, str)
            assert len(qr) > 0
            # Should contain block characters used in QR codes
            assert any(c in qr for c in ["█", "▀", "▄", " "])

    def test_generate_qr_code_uses_active_wallet(self) -> None:
        """Test QR code uses active wallet when no address provided."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))
            wallet = manager.create_wallet("test", "password123")

            # Should use active wallet
            qr = manager.generate_qr_code()
            assert isinstance(qr, str)
            assert len(qr) > 0

    def test_generate_qr_code_no_wallet(self) -> None:
        """Test QR code generation fails without address or active wallet."""
        with TemporaryDirectory() as tmpdir:
            manager = WalletManager(Path(tmpdir))

            with pytest.raises(ValueError, match="No address provided"):
                manager.generate_qr_code()
