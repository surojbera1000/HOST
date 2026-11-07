import { config } from "./config.js";
import { db, now } from "./db.js";

export type User = {
  id: number;
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  balance_paise: number;
  blocked: number;
  created_at: number;
};

export type TgFrom = { id: number; username?: string; first_name?: string };

/** Finds or creates the account for a Telegram user. Returns [user, isNew]. */
export function getOrCreateUser(from: TgFrom): { user: User; isNew: boolean } {
  const existing = db().prepare("SELECT * FROM users WHERE telegram_id = ?").get(from.id) as User | undefined;
  if (existing) {
    // Keep name/username fresh.
    if (existing.username !== (from.username ?? null) || existing.first_name !== (from.first_name ?? null)) {
      db()
        .prepare("UPDATE users SET username = ?, first_name = ? WHERE id = ?")
        .run(from.username ?? null, from.first_name ?? null, existing.id);
    }
    return { user: { ...existing, username: from.username ?? null, first_name: from.first_name ?? null }, isNew: false };
  }
  const info = db()
    .prepare("INSERT INTO users (telegram_id, username, first_name, created_at) VALUES (?, ?, ?, ?)")
    .run(from.id, from.username ?? null, from.first_name ?? null, now());
  const user = db().prepare("SELECT * FROM users WHERE id = ?").get(Number(info.lastInsertRowid)) as User;
  return { user, isNew: true };
}

export function userByTelegramId(telegramId: number): User | undefined {
  return db().prepare("SELECT * FROM users WHERE telegram_id = ?").get(telegramId) as User | undefined;
}

export function isAdmin(telegramId: number): boolean {
  return config.adminTelegramIds.includes(telegramId);
}
