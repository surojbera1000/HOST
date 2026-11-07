# Miku OTP — Telegram Bot (Python)

A Telegram bot that sells phone numbers for OTP/SMS verification. Numbers come from the
[GrizzlySMS API](https://grizzlysms.com). Customers pay by UPI, and their wallet is credited
**automatically** when the FamApp payment email arrives in Gmail. Runs on a VPS.

## What it does

- **Colourful inline-button UI** (Telegram Bot API 9.4 button styles — blue/green/red).
- **Buy a number:** pick an app → pick a country (cheapest first, with flags and live prices) → confirm → get the number. The **OTP appears in the same message** by itself, with **copy buttons** for the number and the OTP. Cancel for a full refund if no OTP arrives.
- **Automatic deposits:** customer taps an amount, the bot shows a UPI **QR with a timer**. When the matching FamApp email reaches Gmail, the wallet is credited and the bot replies "₹X added" — no manual step.
- **Default ₹40 WhatsApp margin:** every WhatsApp number is priced at *cost + ₹40* by default. The admin can change or remove it.
- **Web admin panel** (password-protected): dashboard (sales, profit, GrizzlySMS balance, Gmail status), pricing rules, deposits (auto-matched + manual approve), orders, users (adjust balance, block), settings.

## Pricing

Selling price = GrizzlySMS cost (USD) × **USD→INR rate** (default ₹100), then a rule may apply.
Rule modes: `default`, `plus ₹` (add a flat amount — this is the WhatsApp ₹40), `markup %`, `fixed ₹`.
The bot buys with the cost as `maxPrice`, so you never pay more than the price shown.

## Tech

Python 3.10+, `requests` (Telegram + GrizzlySMS over long-polling, no public webhook needed),
stdlib `sqlite3` (single-file DB) + `imaplib`/`email` for Gmail, `qrcode`+Pillow for QR codes,
and Flask for the admin panel. Background work runs in threads.

## Run on a VPS (Ubuntu)

```bash
sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip git

git clone https://github.com/surojbera1000/HOST.git miku-bot
cd miku-bot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env
nano .env            # fill in the values (below)

# Start it
.venv/bin/python bot.py
```

### Keep it running with systemd

```bash
sudo tee /etc/systemd/system/miku-bot.service >/dev/null <<EOF
[Unit]
Description=Miku OTP Telegram bot
After=network.target

[Service]
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/.venv/bin/python bot.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now miku-bot
sudo journalctl -u miku-bot -f     # watch the logs
```

(Or simply `nohup .venv/bin/python bot.py &` for a quick start.)

### `.env` values

| Variable | What |
|---|---|
| `TELEGRAM_BOT_TOKEN` | From [@BotFather](https://t.me/BotFather) → `/newbot` |
| `GRIZZLY_API_KEY` | grizzlysms.com → Settings |
| `ADMIN_TELEGRAM_IDS` | Your Telegram numeric ID (from @userinfobot). Gets notifications + `/admin` |
| `ADMIN_PANEL_PASSWORD` | Password for the web admin panel |
| `ADMIN_PANEL_PORT` | Default 8080 — open `http://SERVER_IP:8080` |
| `GMAIL_USER` / `GMAIL_APP_PASSWORD` | Gmail that receives FamApp emails. Needs 2-Step Verification + an App Password + IMAP on |
| `FAMPAY_SENDER_DOMAINS` | Default `famapp.in` |
| `SUPPORT_USERNAME` | Telegram username on Support buttons (default OverrMaxx) |

The database is created automatically at `DATABASE_PATH` (default `./data/bot.sqlite`). Back up that
folder. On first run a default **WhatsApp +₹40** price rule is seeded; change it in the admin panel.

### Admin panel

Open `http://SERVER_IP:8080` and log in with `ADMIN_PANEL_PASSWORD`. For HTTPS, put Nginx or Caddy in
front (e.g. Caddy: `admin.yourdomain.com { reverse_proxy localhost:8080 }`).

## Tests

```bash
.venv/bin/python tests/test_offline.py   # pricing (incl. ₹40 WhatsApp), auto deposits, wallet, bot /start
```

## Notes

- Keep **one** instance running: the long-polling loop and SQLite expect a single process.
- Top up your GrizzlySMS balance, otherwise buying fails. The admin dashboard warns when it is low.
- FamApp emails have no note, so each open deposit gets a **unique amount** (e.g. ₹100.37); the exact
  amount identifies the payment. A Transaction ID is never credited twice, and only DKIM-verified emails
  from `famapp.in` are trusted.
