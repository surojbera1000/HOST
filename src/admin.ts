import crypto from "node:crypto";
import express, { type NextFunction, type Request, type Response } from "express";
import { config } from "./config.js";
import { db, DEFAULT_SETTINGS, getSettings, getState, setSetting } from "./db.js";
import { getBalanceUsd, getServices } from "./grizzly.js";
import { gmailConfigured } from "./gmail.js";
import { getPriceRules } from "./pricing.js";
import { creditPayment } from "./payments.js";
import { applyBalance } from "./wallet.js";
import { ADMIN_HTML } from "./admin-html.js";

const tokens = new Set<string>();

function authed(req: Request): boolean {
  const cookie = req.headers.cookie ?? "";
  const m = /(?:^|;\s*)miku_admin=([^;]+)/.exec(cookie);
  return Boolean(m && tokens.has(m[1]!));
}

function requireAuth(req: Request, res: Response, next: NextFunction): void {
  if (!authed(req)) {
    res.status(401).json({ error: "Not logged in" });
    return;
  }
  next();
}

const EDITABLE = Object.keys(DEFAULT_SETTINGS);

export function startAdminPanel(): void {
  const app = express();
  app.use(express.json());

  app.get("/", (_req, res) => res.type("html").send(ADMIN_HTML));

  app.post("/api/login", (req, res) => {
    const password = String(req.body?.password ?? "");
    const ok =
      password.length === config.adminPanelPassword.length &&
      crypto.timingSafeEqual(Buffer.from(password), Buffer.from(config.adminPanelPassword));
    if (!ok) {
      res.status(401).json({ error: "Wrong password" });
      return;
    }
    const token = crypto.randomBytes(24).toString("base64url");
    tokens.add(token);
    res.setHeader("Set-Cookie", `miku_admin=${token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=86400`);
    res.json({ ok: true });
  });

  app.post("/api/logout", (req, res) => {
    const m = /(?:^|;\s*)miku_admin=([^;]+)/.exec(req.headers.cookie ?? "");
    if (m) tokens.delete(m[1]!);
    res.setHeader("Set-Cookie", "miku_admin=; Path=/; Max-Age=0");
    res.json({ ok: true });
  });

  app.get("/api/overview", requireAuth, async (_req, res) => {
    const d = db();
    const startOfDay = new Date();
    startOfDay.setHours(0, 0, 0, 0);
    const since = startOfDay.getTime();
    const users = (d.prepare("SELECT COUNT(*) n FROM users").get() as { n: number }).n;
    const wallets = (d.prepare("SELECT COALESCE(SUM(balance_paise),0) s FROM users").get() as { s: number }).s;
    const sales = d
      .prepare(
        "SELECT COUNT(*) n, COALESCE(SUM(price_paise),0) s, COALESCE(SUM(cost_usd),0) c FROM orders WHERE status IN ('received','completed') AND created_at >= ?",
      )
      .get(since) as { n: number; s: number; c: number };
    const topups = d
      .prepare("SELECT COALESCE(SUM(amount_paise),0) s FROM payments WHERE status = 'paid' AND paid_at >= ?")
      .get(since) as { s: number };
    const rate = Number(getSettings().usd_inr_rate);
    let grizzlyUsd: number | null = null;
    try {
      grizzlyUsd = await getBalanceUsd();
    } catch {
      /* unavailable */
    }
    res.json({
      users,
      walletTotalPaise: wallets,
      today: {
        orders: sales.n,
        salesPaise: sales.s,
        costPaise: Math.round(sales.c * rate * 100),
        topupPaise: topups.s,
      },
      grizzlyUsd,
      grizzlyInrPaise: grizzlyUsd === null ? null : Math.round(grizzlyUsd * rate * 100),
      gmail: { configured: gmailConfigured(), lastOk: Number(getState("gmail_last_ok") ?? 0) || null },
    });
  });

  app.get("/api/settings", requireAuth, (_req, res) => res.json({ settings: getSettings() }));
  app.post("/api/settings", requireAuth, (req, res) => {
    const body = (req.body ?? {}) as Record<string, unknown>;
    for (const key of EDITABLE) {
      if (body[key] !== undefined) setSetting(key, String(body[key]));
    }
    res.json({ settings: getSettings() });
  });

  app.get("/api/services", requireAuth, async (_req, res) => {
    try {
      res.json({ services: await getServices() });
    } catch {
      res.json({ services: [] });
    }
  });

  app.get("/api/rules", requireAuth, (_req, res) => res.json({ rules: getPriceRules() }));
  app.post("/api/rules", requireAuth, (req, res) => {
    const b = req.body ?? {};
    const service = String(b.service ?? "").trim();
    const country = String(b.country ?? "*").trim() || "*";
    const mode = String(b.mode ?? "");
    const value = Number(b.value ?? 0);
    const hidden = b.hidden ? 1 : 0;
    if (!/^(\*|[a-z0-9_]{1,20})$/i.test(service) || !/^(\*|\d{1,5})$/.test(country)) {
      res.status(400).json({ error: "Invalid service or country" });
      return;
    }
    if (!["default", "markup", "fixed", "plus"].includes(mode)) {
      res.status(400).json({ error: "Invalid mode" });
      return;
    }
    db()
      .prepare(
        `INSERT INTO price_rules (service, country, mode, value, hidden) VALUES (?, ?, ?, ?, ?)
         ON CONFLICT(service, country) DO UPDATE SET mode = excluded.mode, value = excluded.value, hidden = excluded.hidden`,
      )
      .run(service, country, mode, value, hidden);
    res.json({ rules: getPriceRules() });
  });
  app.delete("/api/rules/:id", requireAuth, (req, res) => {
    db().prepare("DELETE FROM price_rules WHERE id = ?").run(Number(req.params.id));
    res.json({ rules: getPriceRules() });
  });

  app.get("/api/users", requireAuth, (req, res) => {
    const q = String(req.query.q ?? "").toLowerCase().replace(/[%_]/g, "");
    const users = db()
      .prepare(
        `SELECT u.id, u.telegram_id, u.username, u.first_name, u.balance_paise, u.blocked, u.created_at,
           (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id AND o.status IN ('received','completed')) AS orders,
           (SELECT COALESCE(SUM(amount_paise),0) FROM payments p WHERE p.user_id = u.id AND p.status = 'paid') AS topup_paise
         FROM users u
         WHERE CAST(u.telegram_id AS TEXT) LIKE ? OR LOWER(COALESCE(u.username,'')) LIKE ? OR LOWER(COALESCE(u.first_name,'')) LIKE ?
         ORDER BY u.id DESC LIMIT 200`,
      )
      .all(`%${q}%`, `%${q}%`, `%${q}%`);
    res.json({ users });
  });

  app.post("/api/users/:id/balance", requireAuth, (req, res) => {
    const id = Number(req.params.id);
    const paise = Math.round(Number(req.body?.amount ?? 0) * 100);
    const note = String(req.body?.note ?? "Admin adjustment").slice(0, 200);
    if (!paise) {
      res.status(400).json({ error: "Amount can't be zero" });
      return;
    }
    const ok = db().transaction(() => applyBalance(db(), id, paise, "admin", "admin", note))();
    if (!ok) {
      res.status(400).json({ error: "Balance can't go below ₹0" });
      return;
    }
    res.json({ ok: true });
  });

  app.post("/api/users/:id/block", requireAuth, (req, res) => {
    db()
      .prepare("UPDATE users SET blocked = ? WHERE id = ?")
      .run(req.body?.blocked ? 1 : 0, Number(req.params.id));
    res.json({ ok: true });
  });

  app.get("/api/deposits", requireAuth, (req, res) => {
    const status = String(req.query.status ?? "all");
    const where = status === "all" ? "" : "WHERE p.status = @status";
    const rows = db()
      .prepare(
        `SELECT p.*, u.telegram_id, u.username FROM payments p JOIN users u ON u.id = p.user_id
         ${where} ORDER BY p.id DESC LIMIT 200`,
      )
      .all({ status });
    res.json({ deposits: rows });
  });

  app.post("/api/deposits/:id/approve", requireAuth, (req, res) => {
    const id = Number(req.params.id);
    const utr = req.body?.utr ? String(req.body.utr).trim().toUpperCase() : null;
    const paid = creditPayment(id, utr, null);
    if (!paid) {
      res.status(409).json({ error: "Already credited, or this UTR was used before" });
      return;
    }
    res.json({ ok: true });
  });

  app.post("/api/deposits/:id/reject", requireAuth, (req, res) => {
    db().prepare("UPDATE payments SET status = 'cancelled' WHERE id = ? AND status != 'paid'").run(Number(req.params.id));
    res.json({ ok: true });
  });

  app.get("/api/orders", requireAuth, (_req, res) => {
    const orders = db()
      .prepare(
        `SELECT o.id, o.phone, o.service_name, o.country_name, o.cost_usd, o.price_paise, o.status, o.codes, o.error, o.created_at,
           u.telegram_id, u.username
         FROM orders o JOIN users u ON u.id = o.user_id WHERE o.status != 'buying' ORDER BY o.id DESC LIMIT 200`,
      )
      .all();
    res.json({ orders });
  });

  app.listen(config.adminPanelPort, () => {
    console.log(`[admin] panel on http://localhost:${config.adminPanelPort}`);
  });
}
