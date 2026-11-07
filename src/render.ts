import { config } from "./config.js";
import { getSetting } from "./db.js";
import { countdown, esc, flag, inr } from "./format.js";
import { CANCEL_AFTER_MS, codesOf, type OrderRow } from "./orders.js";
import { type PaymentRow } from "./payments.js";
import { btn, copyBtn, kb, urlBtn, type InlineKeyboard } from "./tg.js";
import type { User } from "./users.js";

export type View = { text: string; keyboard: InlineKeyboard };

const supportUrl = (): string => `https://t.me/${config.supportUsername}`;

export function mainMenu(user: User): View {
  const text =
    `👋 <b>Welcome to Miku OTP</b>\n` +
    `Buy a phone number, receive the OTP here. No OTP? Your money comes back.\n\n` +
    `💰 <b>Balance:</b> ${inr(user.balance_paise)}`;
  return {
    text,
    keyboard: kb([
      [btn("📱  Buy a number", "buy", "primary")],
      [btn("💰  Add money", "dep", "success"), btn("🧾  My numbers", "ords")],
      [btn("🔄  Refresh", "mm"), urlBtn("💬  Support", supportUrl())],
    ]),
  };
}

export function orderView(o: OrderRow, nowMs: number): View {
  const codes = codesOf(o);
  const last = codes[codes.length - 1];
  const head = `${flag(o.country_name)} <b>${esc(o.service_name)}</b> · ${esc(o.country_name)} · ${inr(o.price_paise)}`;
  const number = o.phone ? `+${o.phone}` : "—";

  if (o.status === "received" && last) {
    const earlier = codes.slice(0, -1);
    return {
      text:
        `${head}\n\n` +
        `📱 Number: <code>${esc(number)}</code>\n\n` +
        `🔥 <b>YOUR OTP</b>\n<code>${esc(last)}</code>` +
        (earlier.length ? `\n\nEarlier: ${earlier.map((c) => `<code>${esc(c)}</code>`).join(", ")}` : ""),
      keyboard: kb([
        [copyBtn("📋 Copy OTP", last), copyBtn("📋 Copy number", number)],
        [btn("🔁 Get another OTP", `rty:${o.id}`), btn("✅ Done", `don:${o.id}`, "success")],
        [btn("🏠 Menu", "mm")],
      ]),
    };
  }

  if (o.status === "waiting") {
    const left = o.expires_at - nowMs;
    const cancelIn = o.created_at + CANCEL_AFTER_MS - nowMs;
    const cancelRow =
      cancelIn > 0
        ? [btn(`🚫 Cancel in ${countdown(cancelIn)}`, "noop")]
        : [btn("🚫 Cancel & refund", `ccl:${o.id}`, "danger")];
    return {
      text:
        `${head}\n\n` +
        `📱 Number: <code>${esc(number)}</code>\n` +
        `⏳ <b>Waiting for OTP…</b>\n` +
        `⏱ Time left: ${countdown(left)}\n\n` +
        `Use this number in the app now. The OTP appears here by itself.`,
      keyboard: kb([
        [copyBtn("📋 Copy number", number)],
        [btn("🔄 Check OTP now", `chk:${o.id}`, "primary")],
        cancelRow,
        [btn("🏠 Menu", "mm")],
      ]),
    };
  }

  // completed / cancelled / failed
  const refunded = o.status === "cancelled" || o.status === "failed";
  return {
    text:
      `${head}\n\n` +
      (o.status === "completed" ? "✅ Completed." : refunded ? `↩️ ${esc(o.error ?? "Cancelled")} · refunded.` : "") +
      (codes.length ? `\n\nOTP: ${codes.map((c) => `<code>${esc(c)}</code>`).join(", ")}` : ""),
    keyboard: kb([[btn("📱 Buy another", "buy", "primary"), btn("🏠 Menu", "mm")]]),
  };
}

export function depositCaption(p: PaymentRow, nowMs: number): string {
  if (p.status === "paid") {
    return `✅ <b>${inr(p.amount_paise)} added to your wallet!</b>\n` + (p.utr ? `Transaction ID: <code>${esc(p.utr)}</code>` : "");
  }
  if (p.status !== "pending" || p.expires_at <= nowMs) {
    return `⏰ This deposit timed out. If you already paid, it will still be added automatically within a minute.`;
  }
  return (
    `💰 <b>Add money</b>\n\n` +
    `Pay exactly <b>${inr(p.amount_paise)}</b> to:\n` +
    `<code>${esc(getSetting("upi_id"))}</code>\n\n` +
    `⏱ Pay within <b>${countdown(p.expires_at - nowMs)}</b>\n\n` +
    `1️⃣ Scan the QR in any UPI app (GPay, PhonePe, Paytm, FamApp)\n` +
    `2️⃣ Pay the <b>exact</b> amount, including paise\n` +
    `3️⃣ Stay here — money is added automatically`
  );
}

export function depositKeyboard(p: PaymentRow): InlineKeyboard {
  if (p.status === "pending") {
    return kb([
      [copyBtn(`📋 Copy ₹${(p.amount_paise / 100).toFixed(2)}`, (p.amount_paise / 100).toFixed(2))],
      [btn("🚫 Cancel", `dcl:${p.id}`, "danger")],
      [urlBtn("💬 Support", supportUrl())],
    ]);
  }
  return kb([[btn("💰 Add again", "dep", "success"), btn("🏠 Menu", "mm")]]);
}
