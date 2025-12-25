"""Simplified TUI demo that bypasses the complex app structure."""
import asyncio
import random

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Label, RichLog, Static


class SimpleDemoApp(App):
    """Simplified demo app to test TUI rendering."""

    CSS = """
    Screen {
        background: #000000;
    }

    #main {
        layout: horizontal;
    }

    #log-panel {
        width: 60%;
        border: solid green;
        height: 100%;
    }

    #right-panel {
        width: 40%;
        height: 100%;
    }

    #stats {
        border: solid green;
        height: auto;
        padding: 1;
    }

    #trades {
        border: solid green;
        height: 1fr;
    }

    .title {
        text-style: bold;
        color: lime;
    }

    .value {
        color: #00cc00;
    }

    RichLog {
        background: #000000;
        color: lime;
    }
    """

    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self):
        super().__init__()
        self._demo_task: asyncio.Task | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            yield RichLog(id="log-panel", highlight=True, markup=True)
            with Vertical(id="right-panel"):
                with Static(id="stats"):
                    yield Label("SNIPER STATUS", classes="title")
                    yield Label("Connection: CONNECTED", classes="value")
                    yield Label("Balance: $1,337.42", classes="value")
                    yield Label("")
                    yield Label("STRATEGIES", classes="title")
                    yield Label("ThresholdRules: 3", classes="value")
                    yield Label("KeywordRules: 4", classes="value")
                    yield Label("")
                    yield Label("METRICS", classes="title")
                    yield Label("Events: 0", id="events", classes="value")
                    yield Label("Signals: 0", id="signals", classes="value")
                    yield Label("Trades: 0", id="trades-count", classes="value")
                with Static(id="trades"):
                    yield Label("RECENT TRADES", classes="title")
                    yield Label("(none yet)", id="trade-list")
        yield Footer()

    async def on_mount(self) -> None:
        """Start demo loop on mount."""
        log = self.query_one("#log-panel", RichLog)
        log.write("[bold green]DEMO MODE STARTED[/]")
        log.write("Press Q to quit")
        log.write("")

        self._demo_task = asyncio.create_task(self._run_demo())

    async def _run_demo(self) -> None:
        """Run demo loop with fake data."""
        log = self.query_one("#log-panel", RichLog)

        messages = [
            "[dim]Polling RSS: cointelegraph.com[/]",
            "[dim]Polling RSS: coindesk.com[/]",
            "[green]Price update: BTC $100k at 0.847[/]",
            "[yellow]Spread widening on token 7276...[/]",
            "[green]New RSS entry: 'Bitcoin surges past $99k'[/]",
            "[cyan]Keyword match: 'Bitcoin' detected[/]",
            "[bold green]Signal: BUY $50 on Epstein market[/]",
        ]

        events = 0
        signals = 0
        trades = 0

        try:
            while True:
                await asyncio.sleep(random.uniform(0.5, 2.0))

                msg = random.choice(messages)
                log.write(msg)
                events += 1

                # Update metrics
                self.query_one("#events", Label).update(f"Events: {events}")

                # Random trade (10% chance)
                if random.random() < 0.15:
                    signals += 1
                    trades += 1
                    self.query_one("#signals", Label).update(f"Signals: {signals}")
                    self.query_one("#trades-count", Label).update(f"Trades: {trades}")

                    side = random.choice(["BUY", "SELL"])
                    price = random.uniform(0.2, 0.8)
                    log.write(f"[bold magenta]TRADE: {side} @ ${price:.3f}[/]")

                    self.query_one("#trade-list", Label).update(
                        f"{side} @ {price:.3f} (#{trades})"
                    )

        except asyncio.CancelledError:
            log.write("[red]Demo stopped[/]")

    async def action_quit(self) -> None:
        """Quit with cleanup."""
        if self._demo_task:
            self._demo_task.cancel()
            try:
                await self._demo_task
            except asyncio.CancelledError:
                pass
        self.exit()


if __name__ == "__main__":
    SimpleDemoApp().run()
