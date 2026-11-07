import Database from "better-sqlite3";
import fs from "node:fs";
import path from "node:path";
import { config } from "./config.js";

const SCHEMA = `
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  telegram_id INTEGER NOT NULL UNIQUE,
  username TEXT,
  first_name TEXT,
  balance_paise INTEGER NOT NULL DEFAULT 0 CHECK (balance_paise >= 0),
  blocked INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  delta_paise INTEGER NOT NULL,
  balance_after INTEGER NOT NULL,
  kind TEXT NOT NULL,
  ref TEXT,
  note TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ledger_user ON ledger(user_id, id);

CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  activation_id TEXT UNIQUE,
  phone TEXT,
  service TEXT NOT NULL,
  service_name TEXT NOT NULL,
  country TEXT NOT NULL,
  country_name TEXT NOT NULL,
  cost_usd REAL NOT NULL,
  price_paise INTEGER NOT NULL,
  status TEXT NOT NULL,
  codes TEXT NOT NULL DEFAULT '[]',
  error TEXT,
  chat_id INTEGER,
  message_id INTEGER,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  checked_at INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS orders_user ON orders(user_id, id);
CREATE INDEX IF NOT EXISTS orders_status ON orders(status);

CREATE TABLE IF NOT EXISTS payments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  amount_paise INTEGER NOT NULL,
  status TEXT NOT NULL,
  utr TEXT UNIQUE,
  chat_id INTEGER,
  message_id INTEGER,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  paid_at INTEGER
);
CREATE INDEX IF NOT EXISTS payments_user ON payments(user_id, id);
CREATE INDEX IF NOT EXISTS payments_status ON payments(status);

CREATE TABLE IF NOT EXISTS emails (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id TEXT NOT NULL UNIQUE,
  from_addr TEXT,
  subject TEXT,
  received_at INTEGER,
  amount_paise INTEGER,
  utr TEXT,
  dkim_ok INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  reason TEXT,
  payment_id INTEGER,
  snippet TEXT,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS price_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  service TEXT NOT NULL,
  country TEXT NOT NULL DEFAULT '*',
  mode TEXT NOT NULL,
  value REAL NOT NULL DEFAULT 0,
  hidden INTEGER NOT NULL DEFAULT 0,
  UNIQUE (service, country)
);
`;

let database: Database.Database | null = null;

export function db(): Database.Database {
  if (!database) {
    const file = path.resolve(config.databasePath);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    const d = new Database(file);
    d.pragma("journal_mode = WAL");
    d.pragma("foreign_keys = ON");
    d.pragma("busy_timeout = 5000");
    d.exec(SCHEMA);
    database = d;
    seed(d);
  }
  return database;
}

export const now = (): number => Date.now();

// ---------------- settings ----------------

export const DEFAULT_SETTINGS: Record<string, string> = {
  usd_inr_rate: "100",
  global_markup_pct: "0",
  min_topup_inr: "10",
  max_topup_inr: "5000",
  payment_window_min: "10",
  order_timeout_min: "20",
  upi_id: "Poonambhai@fam",
  upi_name: "Miku OTP",
  welcome_text: "",
};

export function getSetting(key: string): string {
  const row = db().prepare("SELECT value FROM settings WHERE key = ?").get(key) as { value: string } | undefined;
  return row?.value ?? DEFAULT_SETTINGS[key] ?? "";
}

export function getSettingNumber(key: string): number {
  const n = Number(getSetting(key));
  return Number.isFinite(n) ? n : Number(DEFAULT_SETTINGS[key] ?? 0);
}

export function getSettings(): Record<string, string> {
  const out: Record<string, string> = { ...DEFAULT_SETTINGS };
  const rows = db().prepare("SELECT key, value FROM settings").all() as { key: string; value: string }[];
  for (const r of rows) if (!r.key.startsWith("_")) out[r.key] = r.value;
  return out;
}

export function setSetting(key: string, value: string): void {
  db()
    .prepare("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value")
    .run(key, String(value));
}

export function getState(key: string): string | undefined {
  const row = db().prepare("SELECT value FROM settings WHERE key = ?").get(`_${key}`) as { value: string } | undefined;
  return row?.value;
}

export function setState(key: string, value: string): void {
  setSetting(`_${key}`, value);
}

/** One-time defaults: the ₹40 WhatsApp margin the owner asked for (admin can change/delete later). */
function seed(d: Database.Database): void {
  if (getStateRaw(d, "_seeded_v1") === "1") return;
  d.prepare(
    `INSERT INTO price_rules (service, country, mode, value, hidden) VALUES ('wa', '*', 'plus', 40, 0)
     ON CONFLICT(service, country) DO NOTHING`,
  ).run();
  d.prepare(
    "INSERT INTO settings (key, value) VALUES ('_seeded_v1', '1') ON CONFLICT(key) DO UPDATE SET value = '1'",
  ).run();
}

function getStateRaw(d: Database.Database, key: string): string | undefined {
  const row = d.prepare("SELECT value FROM settings WHERE key = ?").get(key) as { value: string } | undefined;
  return row?.value;
}
