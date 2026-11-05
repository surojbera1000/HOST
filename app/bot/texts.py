"""Bot-এর সব message text (বাংলা + ইংরেজি mix)।"""

WELCOME = (
    "🚀 <b>AI Bot Hosting Platform</b>-এ স্বাগতম!\n\n"
    "এখান থেকে আপনি <b>VPS ছাড়াই</b> আপনার Telegram bot host করতে পারবেন।\n"
    "শুধু GitHub repo দিন → env variable বসান → <b>Deploy</b> চাপুন। ✨\n\n"
    "নিচের মেনু থেকে একটা অপশন বেছে নিন 👇"
)

HOST_NEW = (
    "🚀 <b>নতুন Bot Host করা</b>\n\n"
    "এই ফিচারটি <i>Phase 2</i>-এ যুক্ত হবে।\n"
    "তখন আপনি GitHub repo-র লিংক দিলেই সিস্টেম নিজে থেকে repo analyze করবে।"
)

MY_BOTS_EMPTY = (
    "📂 <b>আমার Hosted Bots</b>\n\n"
    "আপনি এখনো কোনো bot host করেননি।\n"
    "🚀 <b>Host a New Bot</b> চেপে শুরু করুন!"
)

STATS = (
    "📊 <b>Hosting Statistics</b>\n\n"
    "🤖 মোট Bot: <b>{total}</b>\n"
    "🟢 Running: <b>{running}</b>\n"
    "⏹ Stopped: <b>{stopped}</b>"
)

GITHUB_AUTH = (
    "🔗 <b>GitHub Authentication</b>\n\n"
    "AI দিয়ে কোড fix করতে GitHub connect করতে হবে।\n"
    "এই ফিচারটি <i>Phase 6</i>-এ যুক্ত হবে (secure OAuth)।"
)

DOCS = (
    "📖 <b>Documentation</b>\n\n"
    "১️⃣ GitHub repo-র লিংক দিন\n"
    "২️⃣ প্রয়োজনীয় env variable ধাপে ধাপে বসান\n"
    "৩️⃣ <b>Confirm &amp; Deploy</b> চাপুন\n"
    "৪️⃣ আপনার bot চালু! 🎉\n\n"
    "সমস্যা হলে AI নিজে থেকে কারণ বুঝিয়ে fix suggest করবে।"
)

PLANS = (
    "💎 <b>Plans &amp; Pricing</b>\n\n"
    "🆓 <b>Free</b> — ১টি bot, basic resource\n"
    "⭐ <b>Pro</b> — শীঘ্রই আসছে\n\n"
    "<i>Payment সিস্টেম পরবর্তী phase-এ যুক্ত হবে।</i>"
)

SUPPORT = (
    "🆘 <b>Support</b>\n\n"
    "কোনো সমস্যা বা প্রশ্ন থাকলে এখানে জানান।\n"
    "আমরা দ্রুত সাহায্য করব! 💬"
)

BACK_HINT = "⬅️ মূল মেনুতে ফিরতে নিচের বাটন চাপুন।"

ADMIN_PANEL = (
    "👑 <b>Admin Panel</b>\n\n"
    "👥 মোট ইউজার: <b>{users}</b>\n"
    "🤖 মোট Bot: <b>{bots}</b>\n"
    "🟢 Running: <b>{running}</b>\n"
    "❌ Failed: <b>{failed}</b>"
)

NOT_ADMIN = "⛔ এই কমান্ড শুধু admin-এর জন্য।"
