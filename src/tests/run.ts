/**
 * Offline tests — no network, temp SQLite DB, Telegram API stubbed.
 * Run: npm test
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

process.env.DATABASE_PATH = path.join(os.tmpdir(), `miku-bot-test-${Date.now()}.sqlite`);
process.env.GRIZZLY_API_KEY = "test";
process.env.FAMPAY_SENDER_DOMAINS = "famapp.in";

process.env.TELEGRAM_BOT_TOKEN = "test:token";

// ---- stub the Telegram API by intercepting fetch to api.telegram.org ----
const sent: { method: string; params: Record<string, unknown> }[] = [];
const realFetch = globalThis.fetch;
globalThis.fetch = (async (url: string | URL, init?: RequestInit) => {
  const u = String(url);
  if (u.includes("api.telegram.org")) {
    const method = u.split("/").pop() ?? "";
    let params: Record<string, unknown> = {};
    if (typeof init?.body === "string") {
      try {
        params = JSON.parse(init.body) as Record<string, unknown>;
      } catch {
        /* multipart (sendPhoto) */
      }
    }
    sent.push({ method, params });
    return new Response(JSON.stringify({ ok: true, result: { message_id: sent.length, chat: { id: 0 } } }), {
      headers: { "content-type": "application/json" },
    });
  }
  return realFetch(url as never, init);
}) as typeof fetch;

const { db, getSettingNumber } = await import("../db.js");
const { makePricer } = await import("../pricing.js");
const { parseEmail, processAlert } = await import("../gmail.js");
const { createPayment } = await import("../payments.js");
const { getOrCreateUser } = await import("../users.js");
const { applyBalance } = await import("../wallet.js");

let passed = 0;
const ok = (name: string): void => {
  passed++;
  console.log("  ✓", name);
};

// ---------- 1. Default ₹40 WhatsApp margin ----------
{
  // $1 = ₹100 by default. A WhatsApp number costing $0.50 → 50 + 40 = ₹90.
  const price = makePricer();
  assert.equal(getSettingNumber("usd_inr_rate"), 100);
  const wa = price("wa", "22", 0.5);
  assert.equal(wa.pricePaise, 9000, "WhatsApp $0.50 → ₹90 (cost ₹50 + ₹40 margin)");
  const wa2 = price("wa", "6", 0.092);
  assert.equal(wa2.pricePaise, Math.ceil((9.2 + 40) * 100), "WhatsApp $0.092 → ₹49.20");
  // Telegram has no rule → default = cost × rate.
  const tg2 = price("tg", "6", 0.09);
  assert.equal(tg2.pricePaise, 900, "Telegram $0.09 → ₹9 (no margin)");
  ok("default ₹40 WhatsApp margin, Telegram unchanged");
}

// ---------- 2. Admin can change the margin ----------
{
  db().prepare("UPDATE price_rules SET value = 25 WHERE service = 'wa' AND country = '*'").run();
  const price = makePricer();
  assert.equal(price("wa", "22", 0.5).pricePaise, 7500, "margin changed to ₹25 → ₹75");
  db().prepare("UPDATE price_rules SET value = 40 WHERE service = 'wa' AND country = '*'").run();
  ok("admin can change the WhatsApp margin");
}

// ---------- 3. Automatic deposit matching from FamApp email ----------
function famapp(opts: { id: string; amount: string; txn: string; from?: string; auth?: string }): Buffer {
  const from = opts.from ?? "no-reply@famapp.in";
  const auth =
    opts.auth ??
    `Authentication-Results: mx.google.com;\r\n       dkim=pass header.i=@famapp.in header.s=s1;\r\n       spf=pass smtp.mailfrom=${from}`;
  const html = `<html><body><p>Hey Poonam,</p><p>You have successfully received</p><h1>&#8377;${opts.amount}</h1><p>from RAJ</p><p>Transaction ID :</p><p>${opts.txn}</p></body></html>`;
  return Buffer.from(
    [
      auth,
      `From: FamApp <${from}>`,
      "To: me@gmail.com",
      `Message-ID: <${opts.id}@famapp.in>`,
      "Subject: You received money",
      `Date: ${new Date().toUTCString()}`,
      "MIME-Version: 1.0",
      "Content-Type: text/html; charset=utf-8",
      "",
      html,
    ].join("\r\n"),
  );
}

{
  const u = getOrCreateUser({ id: 111, username: "alice", first_name: "Alice" }).user;
  const pay = createPayment(u.id, 100); // ₹100 + unique paise
  const rupees = (pay.amount_paise / 100).toFixed(2).replace(/0$/, "");
  const credited = processAlert(await parseEmail(famapp({ id: "m1", amount: rupees, txn: "FMPIB0001" })));
  assert.ok(credited, "matching email credits the deposit");
  const bal = (db().prepare("SELECT balance_paise b FROM users WHERE id=?").get(u.id) as { b: number }).b;
  assert.equal(bal, pay.amount_paise, "wallet credited the exact amount");

  // duplicate email / same txn → no double credit
  processAlert(await parseEmail(famapp({ id: "m1", amount: rupees, txn: "FMPIB0001" })));
  const pay2 = createPayment(u.id, 100);
  const r2 = (pay2.amount_paise / 100).toFixed(2).replace(/0$/, "");
  processAlert(await parseEmail(famapp({ id: "m2", amount: r2, txn: "FMPIB0001" })));
  const bal2 = (db().prepare("SELECT balance_paise b FROM users WHERE id=?").get(u.id) as { b: number }).b;
  assert.equal(bal2, pay.amount_paise, "transaction ID cannot be reused");

  // spoofed sender ignored
  processAlert(await parseEmail(famapp({ id: "m3", amount: r2, txn: "FMPIB0003", from: "x@evil.com", auth: "X-Fake: 1" })));
  const bal3 = (db().prepare("SELECT balance_paise b FROM users WHERE id=?").get(u.id) as { b: number }).b;
  assert.equal(bal3, pay.amount_paise, "spoofed email ignored");

  // wrong amount not credited
  processAlert(await parseEmail(famapp({ id: "m4", amount: "77.00", txn: "FMPIB0004" })));
  const bal4 = (db().prepare("SELECT balance_paise b FROM users WHERE id=?").get(u.id) as { b: number }).b;
  assert.equal(bal4, pay.amount_paise, "unknown amount left for admin");
  ok("automatic deposit matching (credit once, no reuse, spoof/wrong-amount rejected)");
}

// ---------- 4. Unique deposit amounts ----------
{
  const u = getOrCreateUser({ id: 222 }).user;
  const amounts = new Set<number>();
  for (let i = 0; i < 3; i++) {
    const p = createPayment(u.id, 100);
    assert.ok(!amounts.has(p.amount_paise), "each open ₹100 deposit gets a unique amount");
    amounts.add(p.amount_paise);
  }
  ok("concurrent same-amount deposits get unique amounts");
}

// ---------- 5. Wallet never goes negative ----------
{
  const u = getOrCreateUser({ id: 333 }).user;
  const okCredit = db().transaction(() => applyBalance(db(), u.id, 5000, "admin", null, "t"))();
  assert.equal(okCredit, true);
  const bad = db().transaction(() => applyBalance(db(), u.id, -9000, "order", null, "t"))();
  assert.equal(bad, false, "overspend refused");
  const bal = (db().prepare("SELECT balance_paise b FROM users WHERE id=?").get(u.id) as { b: number }).b;
  assert.equal(bal, 5000, "balance unchanged after refused debit");
  ok("wallet cannot go negative");
}

// ---------- 6. Bot /start renders a menu with coloured buttons ----------
{
  sent.length = 0;
  const { handleUpdate } = await import("../bot.js");
  await handleUpdate({ update_id: 1, message: { message_id: 1, chat: { id: 999 }, from: { id: 999, first_name: "Bob" }, text: "/start" } });
  const msg = sent.find((s) => s.method === "sendMessage");
  assert.ok(msg, "sent a message on /start");
  const t = String((msg!.params as { text: string }).text);
  assert.ok(t.includes("Welcome to Miku OTP"), "welcome text");
  const keyboard = JSON.stringify((msg!.params as { reply_markup: unknown }).reply_markup);
  assert.ok(keyboard.includes('"primary"') && keyboard.includes('"success"'), "coloured buttons present");
  assert.ok(keyboard.includes('"buy"') && keyboard.includes('"dep"'), "buy + deposit buttons present");
  ok("bot /start shows coloured menu");
}

console.log(`\nAll ${passed} test groups passed ✓`);
fs.rmSync(process.env.DATABASE_PATH!, { force: true });
fs.rmSync(process.env.DATABASE_PATH! + "-wal", { force: true });
fs.rmSync(process.env.DATABASE_PATH! + "-shm", { force: true });
