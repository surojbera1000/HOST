import crypto from "node:crypto";
import QRCode from "qrcode";
import { db, getSetting, getSettingNumber, now } from "./db.js";
import { applyBalance } from "./wallet.js";

export type PaymentRow = {
  id: number;
  user_id: number;
  amount_paise: number;
  status: "pending" | "paid" | "expired" | "cancelled";
  utr: string | null;
  chat_id: number | null;
  message_id: number | null;
  created_at: number;
  expires_at: number;
  paid_at: number | null;
};

export class PaymentError extends Error {}

export function upiLink(amountPaise: number): string {
  const id = getSetting("upi_id");
  const name = getSetting("upi_name");
  return `upi://pay?pa=${id}&pn=${encodeURIComponent(name)}&am=${(amountPaise / 100).toFixed(2)}&cu=INR`;
}

export function qrPng(amountPaise: number): Promise<Buffer> {
  return QRCode.toBuffer(upiLink(amountPaise), { margin: 1, width: 512, errorCorrectionLevel: "M" });
}

export function expireOldPayments(): void {
  db().prepare("UPDATE payments SET status = 'expired' WHERE status = 'pending' AND expires_at < ?").run(now());
}

/**
 * FamApp emails don't carry a note, so each open deposit gets a unique amount
 * (the rupees asked for + random paise, e.g. ₹100 → ₹100.37). The exact amount
 * then identifies the payment. The customer is credited the full amount they pay.
 */
function uniqueAmountPaise(baseRupees: number): number {
  const basePaise = baseRupees * 100;
  const since = now() - 60 * 60_000;
  const used = new Set(
    (
      db()
        .prepare(
          `SELECT amount_paise FROM payments
           WHERE amount_paise BETWEEN ? AND ? AND (status = 'pending' OR created_at >= ?)`,
        )
        .all(basePaise, basePaise + 99, since) as { amount_paise: number }[]
    ).map((r) => r.amount_paise),
  );
  const free: number[] = [];
  for (let p = 1; p <= 99; p++) if (!used.has(basePaise + p)) free.push(basePaise + p);
  if (!free.length) throw new PaymentError("Too many deposits of this amount right now. Try a slightly different amount.");
  return free[crypto.randomInt(free.length)]!;
}

export function createPayment(userId: number, amountRupees: number): PaymentRow {
  const min = getSettingNumber("min_topup_inr");
  const max = getSettingNumber("max_topup_inr");
  if (!Number.isInteger(amountRupees) || amountRupees < min || amountRupees > max) {
    throw new PaymentError(`Enter a whole amount between ₹${min} and ₹${max}.`);
  }
  expireOldPayments();
  const open = db()
    .prepare("SELECT COUNT(*) n FROM payments WHERE user_id = ? AND status = 'pending'")
    .get(userId) as { n: number };
  if (open.n >= 3) throw new PaymentError("You already have open deposits. Finish or cancel them first.");

  const amountPaise = uniqueAmountPaise(amountRupees);
  const t = now();
  const windowMs = getSettingNumber("payment_window_min") * 60_000;
  const info = db()
    .prepare("INSERT INTO payments (user_id, amount_paise, status, created_at, expires_at) VALUES (?, ?, 'pending', ?, ?)")
    .run(userId, amountPaise, t, t + windowMs);
  return db().prepare("SELECT * FROM payments WHERE id = ?").get(Number(info.lastInsertRowid)) as PaymentRow;
}

export function cancelPayment(id: number): void {
  db().prepare("UPDATE payments SET status = 'cancelled' WHERE id = ? AND status = 'pending'").run(id);
}

export function getPayment(id: number): PaymentRow | undefined {
  return db().prepare("SELECT * FROM payments WHERE id = ?").get(id) as PaymentRow | undefined;
}

export function setPaymentMessage(id: number, chatId: number, messageId: number): void {
  db().prepare("UPDATE payments SET chat_id = ?, message_id = ? WHERE id = ?").run(chatId, messageId, id);
}

/**
 * Marks a payment paid and credits the wallet exactly once.
 * Returns the paid row (for notifying the user) or null if it was already paid / the UTR was used.
 */
export function creditPayment(paymentId: number, utr: string | null, emailId: number | null): PaymentRow | null {
  const conn = db();
  const result = conn.transaction((): PaymentRow | null => {
    if (utr) {
      const used = conn.prepare("SELECT id FROM payments WHERE utr = ?").get(utr) as { id: number } | undefined;
      if (used) return null;
    }
    const res = conn
      .prepare(
        `UPDATE payments SET status = 'paid', utr = ?, paid_at = ?
         WHERE id = ? AND status IN ('pending', 'expired', 'cancelled')`,
      )
      .run(utr, now(), paymentId);
    if (res.changes !== 1) return null;
    const p = conn.prepare("SELECT * FROM payments WHERE id = ?").get(paymentId) as PaymentRow;
    applyBalance(conn, p.user_id, p.amount_paise, "topup", `payment:${p.id}`, `UPI ${utr ?? "deposit"}`);
    if (emailId) {
      conn.prepare("UPDATE emails SET status = 'matched', reason = NULL, payment_id = ? WHERE id = ?").run(p.id, emailId);
    }
    return p;
  })();
  return result;
}
