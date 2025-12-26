"""Modal overlay for wallet unlock/create."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

from src.wallet import Wallet, WalletManager


class UnlockModal(ModalScreen[Wallet | None]):
    """Modal screen for unlocking or creating a wallet.

    Displays a centered dialog over a dimmed background.
    Returns the unlocked Wallet on success, None on cancel.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    UnlockModal {
        align: center middle;
    }

    UnlockModal > Vertical {
        width: 50;
        height: auto;
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
    """

    class WalletUnlocked(Message):
        """Emitted when wallet is successfully unlocked."""

        def __init__(self, wallet: Wallet) -> None:
            super().__init__()
            self.wallet = wallet

    class WalletCreated(Message):
        """Emitted when wallet is successfully created."""

        def __init__(self, wallet: Wallet) -> None:
            super().__init__()
            self.wallet = wallet

    def __init__(self, wallet_manager: WalletManager) -> None:
        super().__init__()
        self._wallet_manager = wallet_manager
        self._mode = "unlock" if wallet_manager.has_wallets() else "create"
        self._error = ""

    def compose(self) -> ComposeResult:
        with Vertical():
            if self._mode == "unlock":
                yield Label("UNLOCK WALLET", classes="modal-title")
                # Show wallet address
                wallets = self._wallet_manager.list_wallets()
                if wallets:
                    addr = wallets[0]["address"]
                    short = f"{addr[:6]}...{addr[-4:]}"
                    yield Label(short, classes="wallet-address")
                yield Label("Enter password to unlock", classes="modal-subtitle")
                yield Input(placeholder="Password", id="password-input", password=True)
                with Center(classes="button-row"):
                    yield Button("Unlock", id="btn-unlock", classes="btn-primary")
                    yield Button("Cancel", id="btn-cancel", classes="btn-secondary")
            else:
                yield Label("CREATE WALLET", classes="modal-title")
                yield Label("Create a new trading wallet", classes="modal-subtitle")
                yield Input(
                    placeholder="Password (8+ characters)",
                    id="password-input",
                    password=True,
                )
                yield Input(
                    placeholder="Confirm password",
                    id="confirm-input",
                    password=True,
                )
                with Center(classes="button-row"):
                    yield Button("Create", id="btn-create", classes="btn-primary")
                    yield Button("Cancel", id="btn-cancel", classes="btn-secondary")

            yield Static("", id="error-label")

    def on_mount(self) -> None:
        """Focus password input on mount."""
        self.query_one("#password-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input."""
        if self._mode == "unlock":
            self._do_unlock()
        elif event.input.id == "password-input":
            # Focus confirm input
            self.query_one("#confirm-input", Input).focus()
        else:
            self._do_create()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-unlock":
            self._do_unlock()
        elif event.button.id == "btn-create":
            self._do_create()

    def _do_unlock(self) -> None:
        """Attempt to unlock wallet."""
        password = self.query_one("#password-input", Input).value
        error_label = self.query_one("#error-label", Static)

        if not password:
            error_label.update("[#f38ba8]Please enter password[/]")
            return

        wallets = self._wallet_manager.list_wallets()
        if not wallets:
            error_label.update("[#f38ba8]No wallet found[/]")
            return

        try:
            wallet = self._wallet_manager.load_wallet(wallets[0]["address"], password)
            self.post_message(self.WalletUnlocked(wallet))
            self.dismiss(wallet)
        except ValueError:
            error_label.update("[#f38ba8]Wrong password[/]")
            self.query_one("#password-input", Input).value = ""
            self.query_one("#password-input", Input).focus()
        except Exception as e:
            error_label.update(f"[#f38ba8]{e}[/]")

    def _do_create(self) -> None:
        """Attempt to create wallet."""
        password = self.query_one("#password-input", Input).value
        confirm = self.query_one("#confirm-input", Input).value
        error_label = self.query_one("#error-label", Static)

        if len(password) < 8:
            error_label.update("[#f38ba8]Password must be 8+ characters[/]")
            return

        if password != confirm:
            error_label.update("[#f38ba8]Passwords do not match[/]")
            self.query_one("#confirm-input", Input).value = ""
            self.query_one("#confirm-input", Input).focus()
            return

        try:
            import time

            name = f"aedes_{int(time.time())}"
            wallet = self._wallet_manager.create_wallet(name, password)
            self.post_message(self.WalletCreated(wallet))
            self.dismiss(wallet)
        except Exception as e:
            error_label.update(f"[#f38ba8]{e}[/]")

    def action_cancel(self) -> None:
        """Cancel and close modal."""
        self.dismiss(None)
