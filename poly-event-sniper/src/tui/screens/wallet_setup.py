"""Wallet setup screen for first-time users."""

from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from src.wallet import WalletManager


class WalletSetupScreen(Screen[str | None]):
    """Screen for creating or loading a wallet.

    Returns the wallet address on success, None on cancel.
    """

    CSS = """
    WalletSetupScreen {
        background: #1e1e2e;
    }

    #container {
        width: 60;
        height: auto;
        margin: 4 0;
        padding: 2;
        border: solid #cba6f7;
        background: #181825;
    }

    .title {
        text-align: center;
        text-style: bold;
        color: #f9e2af;
        margin-bottom: 1;
    }

    .subtitle {
        text-align: center;
        color: #6c7086;
        margin-bottom: 2;
    }

    .section-label {
        color: #cba6f7;
        margin-top: 1;
        margin-bottom: 0;
    }

    Input {
        margin-bottom: 1;
    }

    .button-row {
        layout: horizontal;
        height: auto;
        margin-top: 2;
    }

    Button {
        margin: 0 1;
    }

    Button.primary {
        background: #cba6f7;
        color: #1e1e2e;
    }

    Button.primary:hover {
        background: #f5c2e7;
    }

    .error-message {
        color: #f38ba8;
        text-align: center;
        margin-top: 1;
    }

    .success-message {
        color: #a6e3a1;
        text-align: center;
        margin-top: 1;
    }

    .address-display {
        background: #313244;
        color: #a6e3a1;
        padding: 1;
        margin: 1 0;
        text-align: center;
    }

    .info-text {
        color: #6c7086;
        text-align: center;
        margin-top: 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, wallet_manager: WalletManager) -> None:
        super().__init__()
        self._wallet_manager = wallet_manager
        self._created_wallet_address: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Center():
            with Vertical(id="container"):
                yield Label("WALLET SETUP", classes="title")
                yield Label("Create a new trading wallet", classes="subtitle")

                yield Label("Wallet Name:", classes="section-label")
                yield Input(placeholder="e.g., trading_bot", id="wallet-name")

                yield Label("Password (min 8 chars):", classes="section-label")
                yield Input(placeholder="Password to encrypt wallet", id="password", password=True)

                yield Label("Confirm Password:", classes="section-label")
                yield Input(placeholder="Confirm password", id="password-confirm", password=True)

                yield Label("", id="message", classes="error-message")

                with Center(classes="button-row"):
                    yield Button("Create Wallet", id="create-btn", classes="primary")
                    yield Button("Cancel", id="cancel-btn")
        yield Footer()

    def action_cancel(self) -> None:
        """Cancel and return to previous screen."""
        self.dismiss(None)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        elif event.button.id == "create-btn":
            await self._create_wallet()
        elif event.button.id == "continue-btn":
            self.dismiss(self._created_wallet_address)

    async def _create_wallet(self) -> None:
        """Create a new wallet."""
        name_input = self.query_one("#wallet-name", Input)
        password_input = self.query_one("#password", Input)
        confirm_input = self.query_one("#password-confirm", Input)
        message_label = self.query_one("#message", Label)

        name = name_input.value.strip()
        password = password_input.value
        confirm = confirm_input.value

        # Validation
        if not name:
            message_label.update("Please enter a wallet name")
            message_label.set_classes("error-message")
            return

        if len(password) < 8:
            message_label.update("Password must be at least 8 characters")
            message_label.set_classes("error-message")
            return

        if password != confirm:
            message_label.update("Passwords do not match")
            message_label.set_classes("error-message")
            return

        try:
            # Create wallet
            wallet = self._wallet_manager.create_wallet(name, password)
            self._created_wallet_address = wallet.address

            # Update UI to show success
            container = self.query_one("#container", Vertical)

            # Clear old content
            for child in list(container.children):
                child.remove()

            # Show success message
            await container.mount(Label("WALLET CREATED", classes="title"))
            await container.mount(Label("Your deposit address:", classes="subtitle"))
            await container.mount(Label(wallet.address, classes="address-display"))
            await container.mount(Label(
                "Send USDC (Polygon) to this address to fund your wallet",
                classes="info-text"
            ))
            await container.mount(Label(
                "Save your password - you'll need it to unlock the wallet",
                classes="info-text"
            ))

            with Center(classes="button-row"):
                btn = Button("Continue to Trading", id="continue-btn", classes="primary")
            await container.mount(Center(btn, classes="button-row"))

        except Exception as e:
            message_label.update(f"Error: {e}")
            message_label.set_classes("error-message")


class WalletUnlockScreen(Screen[str | None]):
    """Screen for unlocking an existing wallet.

    Returns the wallet address on success, None on cancel.
    """

    CSS = """
    WalletUnlockScreen {
        background: #1e1e2e;
    }

    #container {
        width: 60;
        height: auto;
        margin: 4 0;
        padding: 2;
        border: solid #cba6f7;
        background: #181825;
    }

    .title {
        text-align: center;
        text-style: bold;
        color: #f9e2af;
        margin-bottom: 1;
    }

    .subtitle {
        text-align: center;
        color: #6c7086;
        margin-bottom: 2;
    }

    .section-label {
        color: #cba6f7;
        margin-top: 1;
        margin-bottom: 0;
    }

    .wallet-option {
        background: #313244;
        color: #cdd6f4;
        padding: 1;
        margin: 0 0 1 0;
    }

    .wallet-option:hover {
        background: #45475a;
    }

    Input {
        margin-bottom: 1;
    }

    .button-row {
        layout: horizontal;
        height: auto;
        margin-top: 2;
    }

    Button {
        margin: 0 1;
    }

    Button.primary {
        background: #cba6f7;
        color: #1e1e2e;
    }

    .error-message {
        color: #f38ba8;
        text-align: center;
        margin-top: 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, wallet_manager: WalletManager) -> None:
        super().__init__()
        self._wallet_manager = wallet_manager
        self._selected_address: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Center():
            with Vertical(id="container"):
                yield Label("UNLOCK WALLET", classes="title")
                yield Label("Select a wallet to unlock", classes="subtitle")

                # List wallets
                wallets = self._wallet_manager.list_wallets()
                for i, wallet in enumerate(wallets):
                    addr = wallet["address"]
                    name = wallet["name"]
                    short_addr = f"{addr[:6]}...{addr[-4:]}"
                    yield Button(
                        f"{name} ({short_addr})",
                        id=f"wallet-{i}",
                        classes="wallet-option",
                    )

                yield Label("Password:", classes="section-label")
                yield Input(placeholder="Enter wallet password", id="password", password=True)

                yield Label("", id="message", classes="error-message")

                with Center(classes="button-row"):
                    yield Button("Unlock", id="unlock-btn", classes="primary")
                    yield Button("New Wallet", id="new-btn")
                    yield Button("Cancel", id="cancel-btn")
        yield Footer()

    def action_cancel(self) -> None:
        """Cancel and return."""
        self.dismiss(None)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "cancel-btn":
            self.dismiss(None)
        elif button_id == "new-btn":
            # Switch to setup screen
            self.app.push_screen(WalletSetupScreen(self._wallet_manager), self._on_wallet_created)
        elif button_id == "unlock-btn":
            await self._unlock_wallet()
        elif button_id and button_id.startswith("wallet-"):
            # Select this wallet
            wallets = self._wallet_manager.list_wallets()
            idx = int(button_id.split("-")[1])
            if idx < len(wallets):
                self._selected_address = wallets[idx]["address"]
                # Highlight selected
                for btn in self.query(".wallet-option"):
                    btn.remove_class("selected")
                event.button.add_class("selected")

    def _on_wallet_created(self, address: str | None) -> None:
        """Callback when wallet is created from setup screen."""
        if address:
            self.dismiss(address)

    async def _unlock_wallet(self) -> None:
        """Unlock the selected wallet."""
        message_label = self.query_one("#message", Label)
        password_input = self.query_one("#password", Input)

        if not self._selected_address:
            # Auto-select first wallet if none selected
            wallets = self._wallet_manager.list_wallets()
            if wallets:
                self._selected_address = wallets[0]["address"]
            else:
                message_label.update("No wallet selected")
                return

        password = password_input.value

        try:
            self._wallet_manager.load_wallet(self._selected_address, password)
            self.dismiss(self._selected_address)
        except ValueError:
            message_label.update("Invalid password")
        except FileNotFoundError:
            message_label.update("Wallet not found")
        except Exception as e:
            message_label.update(f"Error: {e}")
