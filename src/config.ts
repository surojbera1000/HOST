import "dotenv/config";

function env(name: string, fallback = ""): string {
  return (process.env[name] ?? fallback).trim();
}

function list(name: string): string[] {
  return env(name)
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export const config = {
  botToken: env("TELEGRAM_BOT_TOKEN"),
  grizzlyApiKey: env("GRIZZLY_API_KEY"),
  grizzlyBaseUrl: env("GRIZZLY_BASE_URL", "https://api.grizzlysms.com/stubs/handler_api.php"),
  databasePath: env("DATABASE_PATH", "./data/bot.sqlite"),

  // Telegram numeric user IDs that are admins (get notifications + /admin in the bot).
  adminTelegramIds: list("ADMIN_TELEGRAM_IDS").map(Number).filter((n) => Number.isFinite(n)),

  // Web admin panel
  adminPanelPort: Number(env("ADMIN_PANEL_PORT", "8080")) || 8080,
  adminPanelPassword: env("ADMIN_PANEL_PASSWORD"),

  // Gmail that receives FamApp payment emails (for automatic deposits)
  gmailUser: env("GMAIL_USER"),
  gmailAppPassword: env("GMAIL_APP_PASSWORD").replace(/\s+/g, ""),
  gmailPollSeconds: Number(env("GMAIL_POLL_SECONDS", "15")) || 15,
  fampayDomains: list("FAMPAY_SENDER_DOMAINS").length ? list("FAMPAY_SENDER_DOMAINS") : ["famapp.in"],
  requireDkim: env("GMAIL_REQUIRE_DKIM", "true") !== "false",

  supportUsername: env("SUPPORT_USERNAME", "OverrMaxx").replace(/^@/, ""),
};

export function assertConfig(): void {
  const missing: string[] = [];
  if (!config.botToken) missing.push("TELEGRAM_BOT_TOKEN");
  if (!config.grizzlyApiKey) missing.push("GRIZZLY_API_KEY");
  if (!config.adminPanelPassword) missing.push("ADMIN_PANEL_PASSWORD");
  if (missing.length) {
    throw new Error(`Missing required env vars: ${missing.join(", ")}. Copy .env.example to .env and fill them in.`);
  }
}
