"""Inline wallet status widget for the dashboard."""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Input, Label, Static

from src.wallet import Wallet, WalletManager


class WalletWidget(Static):
    """Inline wallet status widget.

    Shows wallet state and provides inline actions:
    - No wallet: [Create Wallet] button
    - Locked: Address + [Unlock] button
    - Unlocked: Address + Balance + [Fund] button
    """

    DEFAULT_CSS = """
    WalletWidget {
        height: auto;
        padding: 0;
        width: 100%;
    }

    WalletWidget #wallet-content {
        width: 100%;
        height: auto;
    }

    .wallet-row {
        height: auto;
        width: 100%;
        layout: horizontal;
    }

    .wallet-address {
        color: #a6e3a1;
        margin-right: 1;
    }

    .wallet-balance {
        color: #f9e2af;
        margin-right: 1;
    }

    .wallet-status {
        color: #6c7086;
        margin-right: 1;
    }

    .wallet-action {
        min-width: 8;
        height: 3;
        background: #313244;
        color: #cdd6f4;
        border: tall #45475a;
        margin: 0 1 0 0;
    }

    .wallet-action:hover {
        background: #45475a;
    }

    .wallet-action:focus {
        background: #cba6f7;
        color: #1e1e2e;
    }

    #password-input {
        width: 100%;
        height: 3;
        margin-bottom: 1;
        background: #313244;
        color: #cdd6f4;
        border: tall #45475a;
    }

    #password-input:focus {
        border: tall #cba6f7;
    }

    .inline-form {
        height: auto;
        width: 100%;
        layout: vertical;
        padding: 0;
    }

    .form-buttons {
        layout: horizontal;
        height: auto;
        width: 100%;
    }

    .error-text {
        color: #f38ba8;
        margin-top: 1;
    }

    .deposit-address {
        background: #313244;
        color: #a6e3a1;
        padding: 0 1;
        margin: 0 1 0 0;
    }
    """

    class WalletUnlocked(Message):
        """Emitted when wallet is unlocked."""

        def __init__(self, wallet: Wallet) -> None:
            super().__init__()
            self.wallet = wallet

    class WalletCreated(Message):
        """Emitted when wallet is created."""

        def __init__(self, wallet: Wallet) -> None:
            super().__init__()
            self.wallet = wallet

    def __init__(self, wallet_manager: WalletManager, **kwargs) -> None:
        super().__init__(**kwargs)
        self._wallet_manager = wallet_manager
        self._state = "checking"  # checking, no_wallet, locked, create, unlock, unlocked, fund
        self._balance: float = 0.0
        self._error: str = ""

    def compose(self) -> ComposeResult:
        yield Static("Checking wallet...", id="wallet-content")

    def on_mount(self) -> None:
        """Check wallet state on mount."""
        self._update_state()

    def _update_state(self) -> None:
        """Update widget based on wallet state."""
        content = self.query_one("#wallet-content", Static)

        if self._wallet_manager.active_wallet:
            self._state = "unlocked"
            self._render_unlocked(content)
        elif self._wallet_manager.has_wallets():
            self._state = "locked"
            self._render_locked(content)
        else:
            self._state = "no_wallet"
            self._render_no_wallet(content)

    def _render_no_wallet(self, container: Static) -> None:
        """Render no wallet state."""
        container.update("")
        container.mount(
            Horizontal(
                Label("No wallet", classes="wallet-status"),
                Button("Create Wallet", id="btn-create", classes="wallet-action"),
                classes="wallet-row",
            )
        )

    def _render_locked(self, container: Static) -> None:
        """Render locked wallet state."""
        wallets = self._wallet_manager.list_wallets()
        if wallets:
            addr = wallets[0]["address"]
            short = f"{addr[:6]}...{addr[-4:]}"
        else:
            short = "Unknown"

        container.update("")
        container.mount(
            Horizontal(
                Label(short, classes="wallet-address"),
                Label("Locked", classes="wallet-status"),
                Button("Unlock", id="btn-unlock", classes="wallet-action"),
                classes="wallet-row",
            )
        )

    def _render_unlocked(self, container: Static) -> None:
        """Render unlocked wallet state."""
        wallet = self._wallet_manager.active_wallet
        if wallet:
            container.update("")
            container.mount(
                Horizontal(
                    Label(wallet.short_address, classes="wallet-address"),
                    Label(f"${self._balance:.2f}", classes="wallet-balance"),
                    Button("Fund", id="btn-fund", classes="wallet-action"),
                    classes="wallet-row",
                )
            )

    def _render_create_form(self, container: Static) -> None:
        """Render create wallet form."""
        from textual.containers import Vertical

        container.update("")
        container.mount(
            Vertical(
                Input(placeholder="Password (8+ chars)", id="password-input", password=True),
                Horizontal(
                    Button("Create", id="btn-do-create", classes="wallet-action"),
                    Button("Cancel", id="btn-cancel", classes="wallet-action"),
                    classes="form-buttons",
                ),
                classes="inline-form",
            )
        )
        if self._error:
            container.mount(Label(self._error, classes="error-text"))

    def _render_unlock_form(self, container: Static) -> None:
        """Render unlock wallet form."""
        from textual.containers import Vertical

        container.update("")
        container.mount(
            Vertical(
                Input(placeholder="Password", id="password-input", password=True),
                Horizontal(
                    Button("Unlock", id="btn-do-unlock", classes="wallet-action"),
                    Button("Cancel", id="btn-cancel", classes="wallet-action"),
                    classes="form-buttons",
                ),
                classes="inline-form",
            )
        )
        if self._error:
            container.mount(Label(self._error, classes="error-text"))

    def _render_fund_view(self, container: Static) -> None:
        """Render fund wallet view with deposit address."""
        wallet = self._wallet_manager.active_wallet
        if wallet:
            container.update("")
            container.mount(
                Horizontal(
                    Label("Deposit:", classes="wallet-status"),
                    Label(wallet.address, classes="deposit-address"),
                    Button("Copy", id="btn-copy", classes="wallet-action"),
                    Button("Done", id="btn-cancel", classes="wallet-action"),
                    classes="wallet-row",
                )
            )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id
        content = self.query_one("#wallet-content", Static)

        # Clear previous children
        for child in list(content.children):
            child.remove()

        if button_id == "btn-create":
            self._state = "create"
            self._error = ""
            self._render_create_form(content)

        elif button_id == "btn-unlock":
            self._state = "unlock"
            self._error = ""
            self._render_unlock_form(content)

        elif button_id == "btn-fund":
            self._state = "fund"
            self._render_fund_view(content)

        elif button_id == "btn-cancel":
            self._error = ""
            self._update_state()

        elif button_id == "btn-copy":
            # Copy address to clipboard (if available)
            wallet = self._wallet_manager.active_wallet
            if wallet:
                try:
                    import pyperclip
                    pyperclip.copy(wallet.address)
                    self.notify("Address copied!")
                except ImportError:
                    self.notify(f"Address: {wallet.address}")

        elif button_id == "btn-do-create":
            await self._do_create()

        elif button_id == "btn-do-unlock":
            await self._do_unlock()

    async def _do_create(self) -> None:
        """Create a new wallet."""
        try:
            password_input = self.query_one("#password-input", Input)
            password = password_input.value

            if len(password) < 8:
                self._error = "Password must be 8+ characters"
                content = self.query_one("#wallet-content", Static)
                for child in list(content.children):
                    child.remove()
                self._render_create_form(content)
                return

            # Create wallet with auto-generated name
            import time
            name = f"aedes_{int(time.time())}"
            wallet = self._wallet_manager.create_wallet(name, password)

            self._state = "unlocked"
            self._error = ""
            self._update_state()

            # Emit message
            self.post_message(self.WalletCreated(wallet))
            self.notify(f"Wallet created: {wallet.short_address}")

        except Exception as e:
            self._error = str(e)
            content = self.query_one("#wallet-content", Static)
            for child in list(content.children):
                child.remove()
            self._render_create_form(content)

    async def _do_unlock(self) -> None:
        """Unlock existing wallet."""
        try:
            password_input = self.query_one("#password-input", Input)
            password = password_input.value

            wallets = self._wallet_manager.list_wallets()
            if not wallets:
                self._error = "No wallet found"
                return

            # Unlock first wallet
            wallet = self._wallet_manager.load_wallet(wallets[0]["address"], password)

            self._state = "unlocked"
            self._error = ""
            self._update_state()

            # Emit message
            self.post_message(self.WalletUnlocked(wallet))
            self.notify(f"Wallet unlocked: {wallet.short_address}")

        except ValueError:
            self._error = "Wrong password"
            content = self.query_one("#wallet-content", Static)
            for child in list(content.children):
                child.remove()
            self._render_unlock_form(content)
        except Exception as e:
            self._error = str(e)
            content = self.query_one("#wallet-content", Static)
            for child in list(content.children):
                child.remove()
            self._render_unlock_form(content)

    def set_balance(self, balance: float) -> None:
        """Update displayed balance."""
        self._balance = balance
        if self._state == "unlocked":
            content = self.query_one("#wallet-content", Static)
            for child in list(content.children):
                child.remove()
            self._render_unlocked(content)
