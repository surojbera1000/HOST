import type Database from "better-sqlite3";
import { db, now } from "./db.js";

export type LedgerKind = "topup" | "order" | "refund" | "admin";

/**
 * Atomically change a user's balance and write a ledger row.
 * Returns false (changing nothing) if a debit would make the balance negative.
 * Pass a transaction connection when combining with other writes.
 */
export function applyBalance(
  conn: Database.Database,
  userId: number,
  deltaPaise: number,
  kind: LedgerKind,
  ref: string | null,
  note: string | null = null,
): boolean {
  if (!Number.isInteger(deltaPaise)) throw new Error("deltaPaise must be an integer");
  const res = conn
    .prepare("UPDATE users SET balance_paise = balance_paise + ? WHERE id = ? AND balance_paise + ? >= 0")
    .run(deltaPaise, userId, deltaPaise);
  if (res.changes !== 1) return false;
  const { balance_paise } = conn.prepare("SELECT balance_paise FROM users WHERE id = ?").get(userId) as {
    balance_paise: number;
  };
  conn
    .prepare(
      "INSERT INTO ledger (user_id, delta_paise, balance_after, kind, ref, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
    )
    .run(userId, deltaPaise, balance_paise, kind, ref, note, now());
  return true;
}

export function balanceOf(userId: number): number {
  const row = db().prepare("SELECT balance_paise FROM users WHERE id = ?").get(userId) as
    | { balance_paise: number }
    | undefined;
  return row?.balance_paise ?? 0;
}
