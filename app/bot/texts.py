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

CONFIG_INTRO = (
    "⚙️ <b>Environment Configuration</b>\n\n"
    "I'll ask for each required variable one by one.\n"
    "Just send the value as a message. Use <b>Skip</b> for optional ones.\n\n"
    "🔒 Sensitive values are encrypted and your message is deleted immediately."
)

ASK_ENV = (
    "🔑 <b>Variable {index}/{total}</b>\n\n"
    "Please send the value for:\n"
    "<code>{key}</code>{hint}"
)

ENV_SAVED_SENSITIVE = "🔒 <code>{key}</code> saved (encrypted). Your message was deleted."
ENV_SAVED_PLAIN = "✅ <code>{key}</code> saved."
ENV_SKIPPED = "⏭ <code>{key}</code> skipped."

NO_ENV_DETECTED = (
    "⚙️ <b>Environment Configuration</b>\n\n"
    "No environment variables were detected for this repo, so there's nothing to set.\n"
    "You can deploy directly."
)

EDIT_INTRO = "✏️ <b>Edit a Variable</b>\n\nPick the variable you want to change:"

EDIT_ASK = "✏️ Send the new value for <code>{key}</code>:"

DEPLOY_SAVED = (
    "✅ <b>Configuration Saved!</b>\n\n"
    "🤖 <b>Bot:</b> {name}\n"
    "📦 <b>Repo:</b> <code>{repo}</code>\n"
    "🔑 <b>Variables set:</b> {count}\n"
    "📊 <b>Status:</b> Pending\n\n"
    "Your bot is queued. The actual deployment engine (containers, build, run) "
    "arrives in <i>Phase 4</i> — everything is saved and ready for it."
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
