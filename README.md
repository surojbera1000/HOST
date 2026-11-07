# Miku OTP — Telegram Bot

A Telegram bot that sells phone numbers for OTP/SMS verification. Numbers come from the
[GrizzlySMS API](https://grizzlysms.com). Customers pay by UPI, and their wallet is credited
**automatically** when the FamApp payment email arrives in Gmail. Runs on a VPS.

## What it does

- **Colourful inline-button UI** (Telegram Bot API 9.4 button styles — blue/green/red).
- **Buy a number:** pick an app → pick a country (cheapest first, with flags and live prices) → confirm → get the number. The **OTP appears in the same message** by itself, inside a highlighted box, with **copy buttons** for the number and the OTP. Cancel for a full refund if no OTP arrives.
- **Automatic deposits:** customer taps an amount, the bot shows a UPI **QR with a timer**. When the matching FamApp email reaches Gmail, the wallet is credited and the bot replies "₹X added" — no manual step.
- **Default ₹40 WhatsApp margin:** every WhatsApp number is priced at *cost + ₹40* by default. The admin can change or remove it.
- **Web admin panel** (password-protected, on the VPS): dashboard (sales, profit, GrizzlySMS balance, Gmail status), pricing rules, deposits (auto-matched + manual approve), orders, users (adjust balance, block), settings.

## Pricing

Selling price = GrizzlySMS cost (USD) × **USD→INR rate** (default ₹100), then a rule may apply.
Rule modes: `default`, `plus ₹` (add a flat amount — this is the WhatsApp ₹40), `markup %`, `fixed ₹`.
Rule priority: service+country → service (all countries) → global. The bot buys with the cost as
`maxPrice`, so you never pay more than the price shown.

## Tech

Node.js 20+, TypeScript, `better-sqlite3` (single file DB), raw Telegram Bot API over long-polling
(no public webhook needed), `imapflow` + `mailparser` for Gmail, `qrcode`, and Express for the admin panel.

## Setup on a VPS (Ubuntu)

```bash
# 1. Node 20+ and pm2
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs
sudo npm i -g pm2

# 2. Get the code
git clone https://github.com/surojbera1000/HOST.git miku-bot
cd miku-bot
npm install
cp .env.example .env
nano .env          # fill in the values (see below)

# 3. Build and run
npm run build
pm2 start ecosystem.config.cjs
pm2 save && pm2 startup
```

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
| `SUPPORT_USERNAME` | Telegram username shown on Support buttons (default OverrMaxx) |

The database is created automatically at `DATABASE_PATH` (default `./data/bot.sqlite`). Back up that
folder. On first run a default **WhatsApp +₹40** price rule is seeded; change it in the admin panel.

### Open the admin panel

Go to `http://SERVER_IP:8080`, log in with `ADMIN_PANEL_PASSWORD`. For HTTPS, put Nginx or Caddy in
front (e.g. Caddy: `admin.yourdomain.com { reverse_proxy localhost:8080 }`).

## Tests

```bash
npm test     # offline: pricing (incl. ₹40 WhatsApp), auto deposit matching, wallet safety, bot /start
```

## Notes

- Keep **one** instance running (pm2 `instances: 1`): the long-polling loop and SQLite expect a single process.
- Top up your GrizzlySMS balance, otherwise buying fails. The admin dashboard warns when it is low.
- FamApp emails do not include a note, so each open deposit gets a **unique amount** (e.g. ₹100.37); the
  exact amount identifies the payment. A Transaction ID is never credited twice, and only DKIM-verified
  emails from `famapp.in` are trusted.
