"""All bot message texts — professional, friendly, beginner-focused (English)."""
from app.branding import BRAND_NAME, BRAND_TAGLINE, BRAND_TITLE

# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------
WELCOME = (
    f"{BRAND_TITLE}\n"
    f"<i>{BRAND_TAGLINE}</i>\n\n"
    "Welcome! 👋 Getting your Telegram bot online used to mean renting a server, "
    "opening a terminal, and typing commands. Not here.\n\n"
    "<b>Here's all you do:</b>\n"
    "1️⃣ Share your bot's GitHub link\n"
    "2️⃣ Answer a few quick questions\n"
    "3️⃣ Tap <b>Deploy</b> — your bot goes live 🎉\n\n"
    "No VPS. No setup. We handle the rest.\n\n"
    "👇 <b>Pick an option to begin</b>"
)

# ---------------------------------------------------------------------------
# Host a New Bot — repo step
# ---------------------------------------------------------------------------
ASK_REPO = (
    "🚀 <b>Let's host your bot</b>\n\n"
    "First, send me the <b>GitHub link</b> of your bot's code.\n\n"
    "It looks like this:\n"
    "<code>https://github.com/username/my-bot</code>\n\n"
    "💡 <i>New to this? It's the web address of your project page on GitHub. "
    "Just copy and paste it here.</i>\n\n"
    "<i>Only public repositories are supported for now.</i>"
)

ANALYZING = (
    "🔍 <b>Checking your repository…</b>\n\n"
    "I'm reading your code to figure out what it needs. One moment. ⏳"
)

INVALID_URL = (
    "🤔 <b>That doesn't look like a GitHub link.</b>\n\n"
    "Please send something like:\n"
    "<code>https://github.com/username/my-bot</code>\n\n"
    "Copy it from your project's page on github.com."
)

# ---------------------------------------------------------------------------
# Configuration — env variables
# ---------------------------------------------------------------------------
CONFIG_INTRO = (
    "⚙️ <b>Almost there — let's set things up</b>\n\n"
    "Your bot needs a few settings to run. I'll ask for them one at a time — "
    "just type each value and send it.\n\n"
    "🔒 Secret values are encrypted, and your message is deleted the moment you send it.\n"
    "⏭ Not sure about one? Tap <b>Skip</b>."
)

ASK_ENV = (
    "🔑 <b>Setting {index} of {total}</b>\n\n"
    "Please send the value for:\n"
    "<code>{key}</code>{hint}\n\n"
    "<i>Type it below and send. 🔒 = kept secret &amp; encrypted.</i>"
)

NO_ENV_DETECTED = (
    "⚙️ <b>Nothing to configure</b>\n\n"
    "Good news — your bot doesn't need any extra settings.\n"
    "You're ready to go live! 🚀"
)

EDIT_INTRO = (
    "✏️ <b>Change a setting</b>\n\n"
    "Tap the one you'd like to update:"
)

EDIT_ASK = "✏️ Send the new value for <code>{key}</code>:"

DEPLOYING = (
    "🚀 <b>Deploying your bot…</b>\n\n"
    "⬇️ Getting your code\n"
    "📦 Installing what it needs\n"
    "⚡ Starting it up\n\n"
    "This usually takes under a minute — hang tight! ⏳"
)

DEPLOY_SUCCESS = (
    "🎉 <b>Your bot is live!</b>\n\n"
    "🤖 <b>Bot:</b> {name}\n"
    "🟢 <b>Status:</b> Running\n"
    "📦 <b>Repository:</b> Connected\n"
    "⚡ <b>Hosting:</b> Active\n\n"
    "Open <b>📂 My Bots</b> any time to check on it, view logs, or restart it."
)

DEPLOY_FAILED = (
    "😕 <b>Hmm, your bot didn't start.</b>\n\n"
    "🤖 <b>Bot:</b> {name}\n"
    "🔴 <b>Status:</b> Failed\n\n"
    "{reason}\n\n"
    "<b>Last log lines:</b>\n"
    "<pre>{logs}</pre>\n\n"
    "💡 Don't worry — our AI assistant will help you fix this automatically in an "
    "upcoming update. For now you can check your settings and try again."
)

DEPLOY_ERROR = (
    "⚠️ <b>Couldn't deploy right now.</b>\n\n"
    "{reason}\n\n"
    "Your bot is saved — please try again in a moment."
)

# ---------------------------------------------------------------------------
# My Bots / Stats
# ---------------------------------------------------------------------------
MY_BOTS_EMPTY = (
    "📂 <b>My Bots</b>\n\n"
    "You haven't added a bot yet.\n\n"
    "Tap 🚀 <b>Host a New Bot</b> and you'll be live in a few minutes!"
)

MY_BOTS_HEADER = "📂 <b>My Bots</b>\n"

STATS = (
    "📊 <b>Your Hosting Overview</b>\n\n"
    "🤖 Total bots: <b>{total}</b>\n"
    "🟢 Running: <b>{running}</b>\n"
    "⏹ Stopped: <b>{stopped}</b>"
)

# ---------------------------------------------------------------------------
# Connect GitHub / How It Works / Support
# ---------------------------------------------------------------------------
GITHUB_AUTH = (
    "🔗 <b>Connect GitHub</b>\n\n"
    "Linking your GitHub account lets our AI assistant fix errors in your bot "
    "and open a pull request for you to approve.\n\n"
    "🔒 You stay in full control — nothing changes in your code without your okay.\n\n"
    "<i>This feature is coming in an upcoming update.</i>"
)

DOCS = (
    "📖 <b>How It Works</b>\n\n"
    "Hosting a bot here takes 3 simple steps:\n\n"
    "1️⃣ <b>Share your code</b> — paste your bot's GitHub link\n"
    "2️⃣ <b>Set it up</b> — answer a few questions (we ask one at a time)\n"
    "3️⃣ <b>Deploy</b> — tap the button and your bot comes alive 🎉\n\n"
    "<b>What you DON'T need:</b>\n"
    "❌ A VPS or server\n"
    "❌ A terminal or commands\n"
    "❌ Any coding setup\n\n"
    "If something goes wrong, our AI assistant explains it in plain language and "
    "helps you fix it. That's it — hosting made easy. 💙"
)

SUPPORT = (
    "🆘 <b>Help &amp; Support</b>\n\n"
    "Stuck on something or have a question? We're here for you.\n\n"
    "💬 Send us a message and we'll help you get your bot running.\n"
    f"💙 Thanks for using {BRAND_NAME}!"
)

BACK_HINT = "⬅️ Tap the button below to go back."

# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
ADMIN_PANEL = (
    "👑 <b>Admin Panel</b>\n\n"
    "👥 Total users: <b>{users}</b>\n"
    "🤖 Total bots: <b>{bots}</b>\n"
    "🟢 Running: <b>{running}</b>\n"
    "❌ Failed: <b>{failed}</b>"
)

NOT_ADMIN = "⛔ This command is for the admin only."
