# AI-Powered Telegram Bot Hosting Platform — Build Plan

একটি production-grade প্ল্যাটফর্ম যেখানে একজন ইউজার শুধু GitHub repo দিয়ে, step-by-step env variable দিয়ে, Deploy চাপলেই তার Telegram bot চালু হয়ে যাবে। Deploy fail করলে AI debugging system সমস্যা ধরে secure GitHub integration দিয়ে fix suggest করবে।

---

## 1. High-Level Architecture

তিনটি আলাদা স্তর (separation of concerns + security):

```
┌─────────────────────────────────────────────────────────────┐
│  CONTROL PLANE  (Telegram Bot - Aiogram 3.x)                 │
│  ইউজার এখান থেকেই সব করবে। শুধু UI + command routing.         │
└───────────────┬─────────────────────────────────────────────┘
                │ internal REST / message queue
┌───────────────▼─────────────────────────────────────────────┐
│  HOSTING ENGINE  (FastAPI backend + Celery workers)          │
│  repo analysis, env collection, deploy orchestration,        │
│  AI debugging, GitHub OAuth, billing                         │
└───────────────┬─────────────────────────────────────────────┘
                │ Docker SDK (isolated)
┌───────────────▼─────────────────────────────────────────────┐
│  RUNTIME PLANE  (per-bot Docker containers)                  │
│  প্রতিটি ইউজারের bot আলাদা container-এ, resource-capped,       │
│  কখনোই main process-এ untrusted code চলবে না                 │
└──────────────────────────────────────────────────────────────┘
```

**মূল নীতি:** Telegram bot হলো control panel; আসল hosting engine backend-এ স্বাধীনভাবে চলে। Untrusted repo code কখনোই main bot process-এ execute হবে না — সবসময় isolated container-এ।

---

## 2. Technology Stack (সিদ্ধান্ত + কারণ)

| স্তর | টেক | কেন |
|------|-----|-----|
| Telegram UI | **Aiogram 3.x** | সম্পূর্ণ async, modern FSM (step-by-step env collection-এর জন্য আদর্শ), inline keyboard support ভালো |
| Backend API | **FastAPI** | async, OpenAPI auto-doc, Pydantic validation |
| Task queue | **Celery + Redis** | deploy/build/monitor কাজ background-এ, long-running tasks bot-কে block করবে না |
| Database | **MongoDB** (Motor + Beanie ODM) | users/bots/deployments/env document data, নমনীয় schema |
| Cache/State | **Redis** | FSM state, rate limiting, task broker |
| Isolation | **Docker** (docker-py SDK) | per-bot container, CPU/memory/timeout limits |
| GitHub | **GitHub REST API + OAuth App** | repo inspection + PR-based fixes |
| AI | **Anthropic Claude API** | error analysis + code fix generation |
| Secrets | **cryptography (Fernet)** + env-based master key | env variable encryption at rest |
| Hosting | **Single VPS/Server** (Docker host) | শুরুর জন্য সহজ; পরে scale করা যাবে |
| Payment | পরবর্তী phase-এ যোগ হবে | আপাতত বাদ |

---

## 3. Database Schema (MongoDB collections)

- `users` — telegram_id, username, plan, created_at, github_oauth_token (encrypted), is_banned
- `bots` — owner_id, name, repo_url, status (pending/running/stopped/crashed/failed), container_id, startup_cmd, entrypoint, language, env_vars (embedded: key + value_encrypted + is_sensitive), created_at
- `deployments` — bot_id, status, logs_ref, started_at, finished_at, error_summary
- `plans` — name, max_bots, cpu_limit, mem_limit, price
- `ai_fixes` — deployment_id, error_type, explanation, proposed_pr_url, status
- `audit_logs` — actor, action, target, timestamp

---

## 4. Telegram Bot UX

Main menu (colourful inline keyboard):
```
🚀 Host a New Bot      📂 My Hosted Bots
📊 Hosting Statistics   🔗 GitHub Authentication
📖 Documentation        💎 Plans & Pricing
🆘 Support
```

- **FSM flow** দিয়ে env variable step-by-step জিজ্ঞেস করা হবে (একটা একটা করে, repo থেকে detect করা অনুযায়ী dynamic)।
- Sensitive value (BOT_TOKEN ইত্যাদি) পাওয়ার সাথে সাথে message delete + encrypted store, log-এ কখনো দেখানো হবে না।
- Deployment summary → **Confirm & Deploy** button।

---

## 5. Repo Analysis Engine

`Host a New Bot` → repo URL → analysis worker:
1. URL validate + GitHub API দিয়ে repo access
2. Language/framework detect (Python / Pyrogram / Aiogram / Telethon)
3. Entry-point খোঁজা (`main.py`, `bot.py`, `__main__.py`, `app.py`, Procfile)
4. Dependencies: `requirements.txt` / `pyproject.toml` / `Pipfile`
5. Env var detect: `.env.example`, `config.py`, `os.environ`/`getenv` static scan, `sample.env`
6. Startup command detect (Procfile / start script / `python main.py`)
7. Missing file / config issue report
8. **Structured deployment report** তৈরি

---

## 6. Deployment Pipeline (Celery)

Confirm → `clone → build image → inject env → run container (capped) → health check → status update`
- Resource caps: CPU quota, memory limit, deploy timeout, restart policy
- Crash detection + auto-restart policy (plan অনুযায়ী)
- Success message:
```
🎉 Your Bot Has Been Successfully Hosted!
🤖 Bot Name: ... | 🟢 Status: Running | 📦 Repository: Connected | ⚡ Hosting: Active
```

---

## 7. AI Debugging System

Deploy fail হলে:
1. Container/build log capture + parse
2. Error classify (missing dep / import error / config / version conflict / runtime)
3. সহজ ভাষায় explanation + suggested fix
4. **🔐 GitHub Authentication** button → OAuth
5. OAuth-এর পর: relevant file inspect → fix generate → **নতুন branch → commit → Pull Request**
6. ইউজারের explicit authorization ছাড়া original code কখনো পরিবর্তন হবে না; re-deploy-এর আগে fix verify

---

## 8. Management Dashboard (Telegram-এর ভেতরে)

Start / Stop / Restart / Live status / Logs / Uptime / Update env / Redeploy / Delete / Resource usage — প্রতিটি inline button।

---

## 9. Admin Panel

Total users, total/active/stopped/failed bots, server resources, user management, hosting limits, deploy history, system logs, broadcast, subscription/payment।

---

## 10. Security Checklist

- GitHub OAuth (state param, scoped permissions)
- Env encryption at rest (Fernet)
- প্রতি bot isolated container, no host network by default
- Repo security scan (dangerous pattern detection)
- CPU/memory/timeout limits, rate limiting
- Secure logging (secret redaction)
- Infra credential কখনো container-এ expose হবে না

---

## 11. Phased Delivery Roadmap

| Phase | Deliverable |
|-------|-------------|
| **0. Foundation** | Repo scaffold, docker-compose (Postgres+Redis), config, DB models + migrations |
| **1. Bot skeleton** | Aiogram bot, main menu, inline keyboards, FSM base |
| **2. Repo analysis** | GitHub API inspection + deployment report |
| **3. Env collection** | Step-by-step FSM, encryption, summary |
| **4. Deploy engine** | Celery worker, Docker build/run, isolation, status |
| **5. Management** | Start/stop/restart/logs/delete dashboard |
| **6. AI debugging** | Log analysis + OAuth + PR-based fixes |
| **7. Admin + billing** | Admin panel, plans, broadcast |
| **8. Hardening** | Security scan, rate limit, monitoring, load test |

---

## খোলা প্রশ্ন (শুরুর আগে ঠিক করা দরকার)

1. **Database:** PostgreSQL (আমার suggestion) নাকি MongoDB?
2. **AI provider:** কোন LLM API (OpenAI / Anthropic / অন্য)?
3. **Deployment target:** একটা single VPS/server নাকি Kubernetes-ভিত্তিক scaling?
4. **Payment:** এখনই billing লাগবে নাকি পরে?
5. **শুরু কোথা থেকে:** পুরো scaffold (Phase 0+1) থেকে নাকি নির্দিষ্ট কোনো অংশ আগে?
