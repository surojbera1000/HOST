"""All bot message texts (English)."""

WELCOME = (
    "🚀 <b>Welcome to the AI Bot Hosting Platform!</b>\n\n"
    "Host your own Telegram bots <b>without a VPS</b>.\n"
    "Just drop a GitHub repo → set your env variables → press <b>Deploy</b>. ✨\n\n"
    "Pick an option from the menu below 👇"
)

ASK_REPO = (
    "🚀 <b>Host a New Bot</b>\n\n"
    "Send me your <b>GitHub repository URL</b> and I'll analyze it automatically.\n\n"
    "Example:\n"
    "<code>https://github.com/username/my-telegram-bot</code>\n\n"
    "<i>Only public repositories are supported for now.</i>"
)

ANALYZING = "🔍 <b>Analyzing repository…</b>\nThis may take a few seconds."

INVALID_URL = (
    "❌ That doesn't look like a valid GitHub URL.\n\n"
    "Please send something like:\n"
    "<code>https://github.com/username/repo</code>"
)

CONFIGURE_SOON = (
    "⚙️ <b>Environment Configuration</b>\n\n"
    "Step-by-step env variable setup arrives in <i>Phase 3</i>.\n"
    "Your analysis is saved — we'll continue from here next."
)

MY_BOTS_EMPTY = (
    "📂 <b>My Hosted Bots</b>\n\n"
    "You haven't hosted any bot yet.\n"
    "Tap 🚀 <b>Host a New Bot</b> to get started!"
)

MY_BOTS_HEADER = "📂 <b>Your Hosted Bots</b>\n"

STATS = (
    "📊 <b>Hosting Statistics</b>\n\n"
    "🤖 Total Bots: <b>{total}</b>\n"
    "🟢 Running: <b>{running}</b>\n"
    "⏹ Stopped: <b>{stopped}</b>"
)

GITHUB_AUTH = (
    "🔗 <b>GitHub Authentication</b>\n\n"
    "Connect your GitHub account so the AI can fix your code.\n"
    "This feature arrives in <i>Phase 6</i> (secure OAuth)."
)

DOCS = (
    "📖 <b>Documentation</b>\n\n"
    "1️⃣ Share your GitHub repo URL\n"
    "2️⃣ Set the required env variables step by step\n"
    "3️⃣ Press <b>Confirm &amp; Deploy</b>\n"
    "4️⃣ Your bot is live! 🎉\n\n"
    "If anything fails, the AI explains the cause and suggests a fix."
)

SUPPORT = (
    "🆘 <b>Support</b>\n\n"
    "Got a problem or question? Let us know here.\n"
    "We'll help you out quickly! 💬"
)

BACK_HINT = "⬅️ Tap the button below to return to the main menu."

ADMIN_PANEL = (
    "👑 <b>Admin Panel</b>\n\n"
    "👥 Total Users: <b>{users}</b>\n"
    "🤖 Total Bots: <b>{bots}</b>\n"
    "🟢 Running: <b>{running}</b>\n"
    "❌ Failed: <b>{failed}</b>"
)

NOT_ADMIN = "⛔ This command is for the admin only."
