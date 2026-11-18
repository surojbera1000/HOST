# Miku OTP — WhatsApp Bot (Python)

A Telegram bot that rents **WhatsApp numbers (India)** for OTP verification, using the
[Phoenix Store Reseller API](http://phoenixstoreapi.duckdns.org:2557). Customers pay by UPI, and
their wallet is credited **automatically** when the FamApp payment email arrives in Gmail.
Runs on a VPS with `python3 bot.py`.

## What it does

- **Colourful inline-button UI** (Telegram Bot API 9.4 button styles — blue/green/red).
- **Buy a WhatsApp number (India):** tap Buy → confirm the price → get the number. The customer
  requests the OTP in WhatsApp; the **OTP appears in the same message** with copy buttons for the
  number and the code. Cancel for a full refund (after the provider's short lock) if no OTP arrives;
  the order also auto-refunds on timeout.
- **Automatic deposits:** customer taps an amount, the bot shows a UPI **QR with a timer**. When the
  matching FamApp email reaches Gmail, the wallet is credited and the bot replies "₹X added".
- **Default ₹40 margin** on every WhatsApp number (admin can change or remove it).
- **Web admin panel** (password-protected): dashboard (sales, profit, Phoenix balance, Gmail status),
  pricing rules, deposits (auto-matched + manual approve), orders, users, settings.

## Pricing

Selling price = Phoenix price (USD) × **USD→INR rate** (default ₹100), then a rule applies. The
default rule is **Plus ₹40** on WhatsApp (`wa`). Other modes: `default`, `markup %`, `fixed ₹`.
The Phoenix price already includes the supplier's markup; your ₹40 is your profit on top.

> Phoenix allows **one pending WhatsApp order per key at a time**, so the bot processes purchases
> one at a time. WhatsApp rental is **India only** (`country_id 22`).

## Tech

Python 3.10+, `requests` (Phoenix API + Telegram long-polling, no public webhook needed),
stdlib `sqlite3` + `imaplib`/`email` for Gmail, `qrcode`+Pillow for QR codes, Flask for the admin
panel. Background work runs in threads.

## Run on a VPS (Ubuntu)

```bash
sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip git

git clone https://github.com/surojbera1000/HOST.git miku-bot
cd miku-bot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env
nano .env            # fill in the values (below)

.venv/bin/python bot.py
```

### Keep it running with systemd

```bash
sudo tee /etc/systemd/system/miku-bot.service >/dev/null <<EOF
[Unit]
Description=Miku OTP WhatsApp bot
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
sudo journalctl -u miku-bot -f
```

### `.env` values

| Variable | What |
|---|---|
| `TELEGRAM_BOT_TOKEN` | From [@BotFather](https://t.me/BotFather) → `/newbot` |
| `PHOENIX_API_KEY` | Phoenix Store bot → Reseller Api → Request Api (starts with `phx_`). Keep it secret |
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
.venv/bin/python tests/test_offline.py   # pricing (₹40), auto deposits, wallet, bot /start, WhatsApp order lifecycle
```

## Notes

- Keep **one** instance running: the long-polling loop and SQLite expect a single process.
- Keep your Phoenix wallet topped up, otherwise buying fails. The admin dashboard warns when it is low.
- FamApp emails have no note, so each open deposit gets a **unique amount** (e.g. ₹100.37); the exact
  amount identifies the payment. A Transaction ID is never credited twice, and only DKIM-verified
  emails from `famapp.in` are trusted.
