"""QR code display widget for terminal."""

from textual.widgets import Static


class QRDisplay(Static):
    """Display a QR code in the terminal.

    Uses segno library to generate terminal-compatible QR codes.
    Best used for displaying Ethereum addresses for mobile wallet scanning.
    """

    DEFAULT_CSS = """
    QRDisplay {
        width: auto;
        height: auto;
        text-align: center;
        padding: 1;
    }
    """

    def __init__(self, address: str, **kwargs) -> None:
        """Initialize QR display with an Ethereum address.

        Args:
            address: Ethereum address to encode as QR code.
        """
        super().__init__(**kwargs)
        self._address = address

    def on_mount(self) -> None:
        """Generate and display QR code on mount."""
        try:
            import segno
        except ImportError:
            self.update("[red]QR code unavailable (install segno)[/]")
            return

        # Create QR with ethereum URI format for wallet compatibility
        uri = f"ethereum:{self._address}"
        qr = segno.make(uri)

        # Get terminal-compatible output
        qr_text = qr.terminal(compact=True)
        self.update(qr_text)

    def update_address(self, address: str) -> None:
        """Update the displayed address.

        Args:
            address: New Ethereum address to encode.
        """
        self._address = address
        self.on_mount()
