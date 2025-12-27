"""Wallet wizard modal for create/import/manage flows."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

from src.wallet import Wallet, WalletManager

# View state type
ViewState = Literal["choice", "create", "import_key", "import_keystore", "success", "manage"]


class UnlockModal(ModalScreen[Wallet | None]):
    """Modal screen for wallet wizard: create, import, or manage.

    Displays a centered dialog over a dimmed background.
    Returns the selected/created Wallet on success, None on cancel.

    Views:
        - choice: First-run wizard with Create/Import options
        - create: Create new wallet form
        - import_key: Import from private key
        - import_keystore: Import from keystore file (requires password)
        - success: Show address + QR code
        - manage: Multi-wallet management (select/switch wallets)
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    UnlockModal {
        align: center middle;
    }

    UnlockModal > Vertical {
        width: 60;
        height: auto;
        max-height: 90%;
        background: #1e1e2e;
        border: thick #cba6f7;
        padding: 1 2;
    }

    UnlockModal .modal-title {
        text-style: bold;
        color: #f9e2af;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }

    UnlockModal .modal-subtitle {
        color: #6c7086;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }

    UnlockModal .wallet-address {
        color: #a6e3a1;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }

    UnlockModal .wallet-address-full {
        color: #a6e3a1;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
        text-style: bold;
    }

    UnlockModal Input {
        width: 100%;
        margin-bottom: 1;
    }

    UnlockModal .button-row {
        width: 100%;
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    UnlockModal .choice-buttons {
        width: 100%;
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    UnlockModal .choice-buttons Button {
        width: 100%;
        margin: 0 0 1 0;
    }

    UnlockModal Button {
        margin: 0 1;
    }

    UnlockModal .btn-primary {
        background: #cba6f7;
        color: #1e1e2e;
    }

    UnlockModal .btn-primary:hover {
        background: #b4befe;
    }

    UnlockModal .btn-secondary {
        background: #313244;
        color: #cdd6f4;
    }

    UnlockModal .btn-secondary:hover {
        background: #45475a;
    }

    UnlockModal .btn-choice {
        background: #313244;
        color: #cdd6f4;
        width: 100%;
    }

    UnlockModal .btn-choice:hover {
        background: #45475a;
    }

    UnlockModal .error-text {
        color: #f38ba8;
        text-align: center;
        width: 100%;
        margin-top: 1;
    }

    UnlockModal .info-text {
        color: #89b4fa;
        text-align: center;
        width: 100%;
        margin-top: 1;
    }

    UnlockModal .success-text {
        color: #a6e3a1;
        text-align: center;
        width: 100%;
        margin-top: 1;
    }

    UnlockModal .qr-container {
        width: 100%;
        height: auto;
        align: center middle;
        margin: 1 0;
    }

    UnlockModal .qr-code {
        text-align: center;
    }

    UnlockModal .back-link {
        color: #6c7086;
        text-align: center;
        width: 100%;
        margin-top: 1;
    }
    """

    # Reactive view state
    view: reactive[ViewState] = reactive("choice")

    class WalletUnlocked(Message):
        """Emitted when wallet is successfully loaded."""

        def __init__(self, wallet: Wallet) -> None:
            super().__init__()
            self.wallet = wallet

    class WalletCreated(Message):
        """Emitted when wallet is successfully created."""

        def __init__(self, wallet: Wallet) -> None:
            super().__init__()
            self.wallet = wallet

    def __init__(
        self,
        wallet_manager: WalletManager,
        env_wallet_available: bool = False,
        initial_view: ViewState | None = None,
    ) -> None:
        """Initialize the wallet wizard.

        Args:
            wallet_manager: WalletManager instance for operations.
            env_wallet_available: Whether .env has a valid private key.
            initial_view: Force a specific initial view (e.g., "manage").
        """
        super().__init__()
        self._wallet_manager = wallet_manager
        self._env_wallet_available = env_wallet_available
        self._error = ""
        self._created_wallet: Wallet | None = None

        # Determine initial view
        if initial_view is not None:
            self.view = initial_view
        elif wallet_manager.has_wallets():
            self.view = "manage"
        else:
            self.view = "choice"

    def compose(self) -> ComposeResult:
        """Compose the modal content."""
        with Vertical():
            yield from self._compose_view()

    def _compose_view(self) -> ComposeResult:
        """Compose content for current view state."""
        if self.view == "choice":
            yield from self._compose_choice()
        elif self.view == "create":
            yield from self._compose_create()
        elif self.view == "import_key":
            yield from self._compose_import_key()
        elif self.view == "import_keystore":
            yield from self._compose_import_keystore()
        elif self.view == "success":
            yield from self._compose_success()
        elif self.view == "manage":
            yield from self._compose_manage()

    def _compose_choice(self) -> ComposeResult:
        """Compose first-run choice screen."""
        yield Label("WALLET SETUP", classes="modal-title")
        yield Label("Choose how to set up your trading wallet:", classes="modal-subtitle")

        choice_container = Vertical(classes="choice-buttons")
        choice_container._add_children(
            Button("Create New Wallet", id="btn-choice-create", classes="btn-choice"),
            Button("Import MetaMask Keystore", id="btn-choice-keystore", classes="btn-choice"),
            Button("Import Private Key", id="btn-choice-key", classes="btn-choice"),
        )
        yield choice_container

        if self._env_wallet_available:
            yield Label("", classes="info-text")
            yield Button("Use .env Wallet", id="btn-use-env", classes="btn-secondary")
        else:
            button_row = Center(classes="button-row")
            button_row._add_children(Button("Cancel", id="btn-cancel", classes="btn-secondary"))
            yield button_row

    def _compose_create(self) -> ComposeResult:
        """Compose create wallet screen."""
        yield Label("CREATE WALLET", classes="modal-title")
        yield Label("A new wallet will be created for trading", classes="modal-subtitle")
        yield Input(placeholder="Wallet name (optional)", id="name-input")

        button_row = Center(classes="button-row")
        button_row._add_children(
            Button("Create", id="btn-create", classes="btn-primary"),
            Button("Back", id="btn-back", classes="btn-secondary"),
        )
        yield button_row
        yield Static("", id="error-label")

    def _compose_import_key(self) -> ComposeResult:
        """Compose import private key screen."""
        yield Label("IMPORT PRIVATE KEY", classes="modal-title")
        yield Label("Paste your private key (hex format)", classes="modal-subtitle")
        yield Input(placeholder="0x... (64 hex characters)", id="private-key-input", password=True)
        yield Input(placeholder="Wallet name (optional)", id="name-input")

        button_row = Center(classes="button-row")
        button_row._add_children(
            Button("Import", id="btn-import-key", classes="btn-primary"),
            Button("Back", id="btn-back", classes="btn-secondary"),
        )
        yield button_row
        yield Static("", id="error-label")

    def _compose_import_keystore(self) -> ComposeResult:
        """Compose import keystore screen."""
        yield Label("IMPORT KEYSTORE", classes="modal-title")
        yield Label("Import a MetaMask JSON keystore file", classes="modal-subtitle")
        yield Input(placeholder="Path to keystore file", id="keystore-path-input")
        yield Input(placeholder="Keystore password", id="password-input", password=True)
        yield Input(placeholder="Wallet name (optional)", id="name-input")

        button_row = Center(classes="button-row")
        button_row._add_children(
            Button("Import", id="btn-import-keystore", classes="btn-primary"),
            Button("Back", id="btn-back", classes="btn-secondary"),
        )
        yield button_row
        yield Static("", id="error-label")

    def _compose_success(self) -> ComposeResult:
        """Compose success screen with QR code."""
        yield Label("WALLET READY", classes="modal-title")

        if self._created_wallet:
            yield Label("Your deposit address:", classes="modal-subtitle")
            yield Label(self._created_wallet.address, classes="wallet-address-full")

            # QR code container
            qr_container = Center(classes="qr-container")
            qr_container._add_children(Static("", id="qr-code", classes="qr-code"))
            yield qr_container

            yield Label("Scan with mobile wallet to deposit USDC (Polygon)", classes="info-text")

        button_row = Center(classes="button-row")
        button_row._add_children(Button("Continue to Trading", id="btn-continue", classes="btn-primary"))
        yield button_row

    def _compose_manage(self) -> ComposeResult:
        """Compose wallet management screen."""
        yield Label("WALLET MANAGEMENT", classes="modal-title")
        yield Label("Select a wallet to use:", classes="modal-subtitle")

        wallets = self._wallet_manager.list_wallets()

        if wallets:
            wallet_container = Vertical(classes="choice-buttons")
            wallet_buttons = []
            for wallet_info in wallets:
                addr = wallet_info["address"]
                name = wallet_info["name"]
                short = f"{addr[:6]}...{addr[-4:]}"
                btn = Button(
                    f"{name} ({short})",
                    id=f"btn-wallet-{addr.lower()}",
                    classes="btn-choice",
                )
                wallet_buttons.append(btn)
            wallet_container._add_children(*wallet_buttons)
            yield wallet_container

        # Add new wallet button
        yield Label("", classes="info-text")
        yield Button("Create/Import New", id="btn-add-new", classes="btn-secondary")

        button_row = Center(classes="button-row")
        button_row._add_children(Button("Cancel", id="btn-cancel", classes="btn-secondary"))
        yield button_row

    def watch_view(self, old_view: ViewState, new_view: ViewState) -> None:
        """React to view changes by recomposing."""
        # Skip if not mounted yet (initial __init__ call)
        if not self.is_mounted:
            return

        # Clear and recompose on view change
        container = self.query_one(Vertical)
        container.remove_children()

        # Add new content
        for widget in self._compose_view():
            container.mount(widget)

        # Focus appropriate input
        self.call_after_refresh(self._focus_first_input)

        # Generate QR code if success view
        if new_view == "success" and self._created_wallet:
            self.call_after_refresh(self._show_qr_code)

    def _focus_first_input(self) -> None:
        """Focus the first input in current view."""
        inputs = self.query(Input)
        if inputs:
            inputs.first().focus()

    def _show_qr_code(self) -> None:
        """Generate and display QR code."""
        if not self._created_wallet:
            return

        try:
            qr_text = self._wallet_manager.generate_qr_code(self._created_wallet.address)
            qr_widget = self.query_one("#qr-code", Static)
            qr_widget.update(qr_text)
        except Exception as e:
            # QR code is optional, don't fail
            qr_widget = self.query_one("#qr-code", Static)
            qr_widget.update(f"[dim](QR unavailable: {e})[/]")

    def on_mount(self) -> None:
        """Focus first input on mount."""
        self._focus_first_input()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input."""
        if self.view == "create":
            self._do_create()
        elif self.view == "import_key":
            if event.input.id == "private-key-input":
                self.query_one("#name-input", Input).focus()
            else:
                self._do_import_key()
        elif self.view == "import_keystore":
            if event.input.id == "keystore-path-input":
                self.query_one("#password-input", Input).focus()
            elif event.input.id == "password-input":
                self.query_one("#name-input", Input).focus()
            else:
                self._do_import_keystore()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        # Navigation
        if button_id == "btn-cancel":
            self.dismiss(None)
        elif button_id == "btn-back":
            self.view = "choice"
        elif button_id == "btn-use-env":
            # User chose to use .env wallet
            self.dismiss(None)

        # Choice buttons
        elif button_id == "btn-choice-create":
            self.view = "create"
        elif button_id == "btn-choice-keystore":
            self.view = "import_keystore"
        elif button_id == "btn-choice-key":
            self.view = "import_key"

        # Manage view buttons
        elif button_id == "btn-add-new":
            self.view = "choice"
        elif button_id and button_id.startswith("btn-wallet-"):
            # Extract address from button ID and load wallet directly
            address = button_id[len("btn-wallet-"):]
            self._do_load_wallet(address)

        # Action buttons
        elif button_id == "btn-create":
            self._do_create()
        elif button_id == "btn-import-key":
            self._do_import_key()
        elif button_id == "btn-import-keystore":
            self._do_import_keystore()
        elif button_id == "btn-continue":
            if self._created_wallet:
                self.dismiss(self._created_wallet)
            else:
                self.dismiss(None)

    def _show_error(self, message: str) -> None:
        """Display error message."""
        try:
            error_label = self.query_one("#error-label", Static)
            error_label.update(f"[#f38ba8]{message}[/]")
        except Exception:
            pass

    def _clear_error(self) -> None:
        """Clear error message."""
        try:
            error_label = self.query_one("#error-label", Static)
            error_label.update("")
        except Exception:
            pass

    def _do_load_wallet(self, address: str) -> None:
        """Load wallet directly by address."""
        try:
            wallet = self._wallet_manager.load_wallet(address)
            self.post_message(self.WalletUnlocked(wallet))
            self.dismiss(wallet)
        except Exception as e:
            # Show error in manage view (need to add error label there)
            self.notify(str(e), severity="error")

    def _do_create(self) -> None:
        """Attempt to create wallet."""
        name_input = self.query_one("#name-input", Input)
        name = name_input.value.strip()

        if not name:
            import time
            name = f"aedes_{int(time.time())}"

        try:
            wallet = self._wallet_manager.create_wallet(name)
            self._created_wallet = wallet
            self.post_message(self.WalletCreated(wallet))
            self.view = "success"
        except Exception as e:
            self._show_error(str(e))

    def _do_import_key(self) -> None:
        """Attempt to import from private key."""
        private_key = self.query_one("#private-key-input", Input).value
        name_input = self.query_one("#name-input", Input)
        name = name_input.value.strip() or None

        if not private_key:
            self._show_error("Please enter private key")
            return

        try:
            wallet = self._wallet_manager.import_from_private_key(private_key, name)
            self._created_wallet = wallet
            self.post_message(self.WalletCreated(wallet))
            self.view = "success"
        except ValueError as e:
            self._show_error(str(e))
        except Exception as e:
            self._show_error(f"Import failed: {e}")

    def _do_import_keystore(self) -> None:
        """Attempt to import from keystore file."""
        keystore_path = self.query_one("#keystore-path-input", Input).value
        password = self.query_one("#password-input", Input).value
        name_input = self.query_one("#name-input", Input)
        name = name_input.value.strip() or None

        if not keystore_path:
            self._show_error("Please enter keystore path")
            return

        if not password:
            self._show_error("Please enter keystore password")
            return

        # Expand path
        path = Path(keystore_path).expanduser()

        try:
            wallet = self._wallet_manager.import_from_keystore(path, password, name)
            self._created_wallet = wallet
            self.post_message(self.WalletCreated(wallet))
            self.view = "success"
        except FileNotFoundError:
            self._show_error("Keystore file not found")
        except ValueError as e:
            self._show_error(str(e))
        except Exception as e:
            self._show_error(f"Import failed: {e}")

    def action_cancel(self) -> None:
        """Cancel and close modal."""
        self.dismiss(None)


# Alias for backward compatibility
WalletWizard = UnlockModal
