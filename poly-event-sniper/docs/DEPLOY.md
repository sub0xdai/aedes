# Deploying Poly-Event-Sniper to DigitalOcean VPS

## Why Remote Deployment?

Polymarket is geo-blocked in certain regions (Australia, USA, etc.). The API rejects requests based on IP address before authentication. You **must** run the bot from a supported region.

**Supported Regions:** UK, Germany, Finland, Netherlands, parts of South America, non-restricted EU

## Prerequisites

- DigitalOcean account with a Droplet in a supported region
- SSH access to your VPS
- Git installed locally
- Your Polygon wallet private key (the bot will derive API credentials on the VPS)

---

## Step 1: Create DigitalOcean Droplet

If you haven't already:

1. Log into DigitalOcean
2. Create Droplet:
   - **Region:** London, Amsterdam, or Frankfurt
   - **Image:** Ubuntu 24.04 LTS
   - **Size:** Basic $6/mo (1GB RAM) is sufficient
   - **Authentication:** SSH key (recommended)
3. Note your Droplet's IP address

---

## Step 2: Initial Server Setup

SSH into your VPS:

```bash
ssh root@YOUR_DROPLET_IP
```

### Install Dependencies

```bash
# Update system
apt update && apt upgrade -y

# Install Python 3.12+ and essentials
apt install -y python3.12 python3.12-venv python3-pip git curl

# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# Verify
uv --version
python3.12 --version
```

### Create Non-Root User (Recommended)

```bash
# Create user for running the bot
adduser aedes
usermod -aG sudo aedes

# Copy SSH keys
mkdir -p /home/aedes/.ssh
cp ~/.ssh/authorized_keys /home/aedes/.ssh/
chown -R aedes:aedes /home/aedes/.ssh

# Switch to new user
su - aedes
```

---

## Step 3: Clone and Configure

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/aedes_trade.git
cd aedes_trade/poly-event-sniper

# Create virtual environment and install dependencies
uv sync

# Copy and configure environment
cp .env.example .env
nano .env
```

### Configure `.env`

```bash
# REQUIRED: Your Polygon wallet private key (hex with 0x prefix)
POLYGON_PRIVATE_KEY=0xYOUR_ACTUAL_PRIVATE_KEY_HERE

# Leave CLOB credentials empty - they'll be auto-derived on first run
CLOB_API_KEY=
CLOB_API_SECRET=
CLOB_API_PASSPHRASE=

# IMPORTANT: Set to false for live trading
BOT_DRY_RUN=false

# Start with small position sizes
BOT_MAX_POSITION_SIZE=5.0
```

---

## Step 4: Generate API Credentials

The first time you run the bot from a supported region, it will auto-derive Polymarket API credentials:

```bash
# Test that credentials can be derived
uv run python -c "
from src.executors.polymarket import PolymarketExecutor
import asyncio

async def test():
    executor = PolymarketExecutor()
    await executor.setup()
    balance = await executor.get_balance()
    print(f'Success! Balance: \${balance:.2f} USDC')

asyncio.run(test())
"
```

If successful, you'll see your wallet balance. If not, check:
- Your IP is from a supported region (`curl ifconfig.me`)
- Your private key is correct
- You have USDC in your Polygon wallet

---

## Step 5: Run the Bot

### Interactive Mode (Testing)

```bash
# Run with TUI
uv run python main.py --tui

# Or headless
uv run python main.py
```

### Background Mode (Production)

Using `tmux` (recommended):

```bash
# Install tmux
sudo apt install -y tmux

# Create new session
tmux new -s aedes

# Run the bot
cd ~/aedes_trade/poly-event-sniper
uv run python main.py --tui

# Detach: Ctrl+B, then D
# Reattach later: tmux attach -t aedes
```

Using `systemd` (auto-restart):

```bash
# Create service file
sudo nano /etc/systemd/system/aedes.service
```

```ini
[Unit]
Description=Aedes Polymarket Trading Bot
After=network.target

[Service]
Type=simple
User=aedes
WorkingDirectory=/home/aedes/aedes_trade/poly-event-sniper
ExecStart=/home/aedes/.local/bin/uv run python main.py
Restart=always
RestartSec=10
Environment=TERM=xterm-256color

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable aedes
sudo systemctl start aedes

# Check status
sudo systemctl status aedes

# View logs
sudo journalctl -u aedes -f
```

---

## Step 6: Local Development Workflow

### VS Code Remote SSH (Recommended)

1. Install "Remote - SSH" extension in VS Code
2. Press `Ctrl+Shift+P` → "Remote-SSH: Connect to Host"
3. Enter `aedes@YOUR_DROPLET_IP`
4. Open folder: `/home/aedes/aedes_trade/poly-event-sniper`

Now you edit code "locally" but it runs on the VPS.

### Git-Based Workflow

Local machine:
```bash
# Make changes locally
git add .
git commit -m "feat: new feature"
git push origin main
```

On VPS:
```bash
cd ~/aedes_trade/poly-event-sniper
git pull
sudo systemctl restart aedes
```

---

## Step 7: Monitoring

### Check Balance

```bash
uv run python -c "
from src.executors.polymarket import PolymarketExecutor
import asyncio

async def check():
    executor = PolymarketExecutor()
    await executor.setup()
    print(f'Balance: \${await executor.get_balance():.2f}')

asyncio.run(check())
"
```

### View Logs

```bash
# If using systemd
sudo journalctl -u aedes -f

# If using tmux
tmux attach -t aedes

# Application logs
tail -f logs/aedes.log
```

### Check Bot Status

```bash
# Is it running?
pgrep -f "python main.py"

# Resource usage
htop
```

---

## Troubleshooting

### "Incorrect padding" Error
- You're still geo-blocked. Check your IP: `curl ifconfig.me`
- Verify the Droplet is in a supported region

### "Failed to derive API credentials"
- Private key format wrong (needs `0x` prefix)
- Wallet has no transaction history on Polygon
- Try funding the wallet with a small amount of MATIC first

### Bot Crashes on Start
- Check logs: `sudo journalctl -u aedes -n 50`
- Verify `.env` exists and is configured
- Run manually to see errors: `uv run python main.py`

### Connection Timeouts
- Polymarket API might be rate limiting
- Check your internet: `ping polymarket.com`
- Restart the bot

---

## Security Best Practices

1. **Use a dedicated trading wallet** - Never use your main wallet
2. **Limit funds** - Only deposit what you're willing to lose
3. **SSH keys only** - Disable password authentication
4. **Firewall** - `ufw allow ssh && ufw enable`
5. **Keep private key secure** - Never commit `.env` to git
6. **Monitor regularly** - Check balance and positions daily

---

## Quick Reference

| Task | Command |
|------|---------|
| Start bot (tmux) | `tmux new -s aedes && uv run python main.py --tui` |
| Attach to session | `tmux attach -t aedes` |
| Detach from session | `Ctrl+B`, then `D` |
| Check balance | See Step 7 |
| View logs | `sudo journalctl -u aedes -f` |
| Restart bot | `sudo systemctl restart aedes` |
| Pull updates | `git pull && sudo systemctl restart aedes` |
