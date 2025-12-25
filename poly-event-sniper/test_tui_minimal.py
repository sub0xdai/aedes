"""Minimal TUI test to verify Textual renders correctly."""
from textual.app import App, ComposeResult
from textual.widgets import Static, Header, Footer


class TestApp(App):
    """Minimal test app."""

    BINDINGS = [("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("TEST - If you can see this, Textual works!")
        yield Static("Press Q to quit")
        yield Footer()


if __name__ == "__main__":
    TestApp().run()
