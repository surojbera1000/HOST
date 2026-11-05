# 🪺 BotNest — AI-Powered Telegram Bot Hosting

<i>Host Telegram bots in minutes — no VPS, no code.</i>

VPS ছাড়াই Telegram bot host করার সম্পূর্ণ স্বয়ংক্রিয় platform। ইউজার শুধু GitHub repo দেবে, env variable ধাপে ধাপে বসাবে, Deploy চাপবে — bot চালু। Deploy fail করলে AI (Claude) সমস্যা ধরে GitHub PR-এর মাধ্যমে fix suggest করবে।

> বিস্তারিত আর্কিটেকচার ও roadmap-এর জন্য দেখুন **[PLAN.md](./PLAN.md)**

## 🧩 Tech Stack
- **Aiogram 3.x** — Telegram bot (control panel)
- **MongoDB** (Motor + Beanie) — ডেটা
- **Redis** — FSM state + Celery broker
- **Celery** — background deploy worker
- **Docker** — প্রতি bot isolated container
- **Anthropic Claude** — AI error debugging
- **GitHub API + OAuth** — repo analysis + PR fixes

## ✅ এখন পর্যন্ত যা হয়েছে (Phase 0 → 4)
- পুরো project scaffold + Docker setup
- MongoDB models (User, HostedBot, Deployment)
- Secret encryption (Fernet) + secret-redacting logger
- Telegram bot: `/start`, রঙিন inline main menu (Bot API 9.4 styled buttons)
- **Phase 2:** GitHub repo analysis — language/framework/entry-point/deps/env detect
- **Phase 3:** ধাপে ধাপে env variable সংগ্রহ (encrypted) + review/edit + summary
- **Phase 4:** আসল Docker deployment engine — isolated container-এ clone → install → run
- `/admin` panel (owner-only basic stats)

## 🛠 সেটআপ (কীভাবে চালাবেন)

### ১. Secret key বানান
```bash
python3 -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

### ২. `.env` ফাইল তৈরি করুন
```bash
cp .env.example .env
```
তারপর `.env` ফাইলে বসান:
- `BOT_TOKEN` — [@BotFather](https://t.me/BotFather) থেকে
- `API_ID`, `API_HASH` — https://my.telegram.org থেকে
- `OWNER_ID` — [@userinfobot](https://t.me/userinfobot) থেকে আপনার Telegram ID
- `FERNET_KEY` — উপরের কমান্ডে পাওয়া key
- `ANTHROPIC_API_KEY` — Claude API key (AI ফিচারের জন্য)

### ৩. Docker দিয়ে চালান (সবচেয়ে সহজ)
```bash
docker compose up --build
```
এটি bot + MongoDB + Redis একসাথে চালু করবে।

### অথবা লোকালি চালান
```bash
pip install -r requirements.txt
# আলাদাভাবে MongoDB ও Redis চালু থাকতে হবে
python -m app.main
```

### ৪. টেস্ট করুন
Telegram-এ আপনার bot খুলে `/start` পাঠান → রঙিন মেনু দেখবেন। 🎉

## 🗺 পরবর্তী ধাপ
- ✅ **Phase 2** — GitHub repo analysis engine
- ✅ **Phase 3** — ধাপে ধাপে env variable সংগ্রহ (FSM)
- ✅ **Phase 4** — Docker deploy engine
- ⏳ **Phase 5** — bot management dashboard (start/stop/restart/logs/delete)
- ⏳ **Phase 6** — AI debugging + GitHub OAuth + PR fixes
- ⏳ **Phase 7** — admin panel + billing
