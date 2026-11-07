import { db, getSettingNumber, now } from "./db.js";
import * as grizzly from "./grizzly.js";
import { makePricer } from "./pricing.js";
import { applyBalance } from "./wallet.js";

export type OrderRow = {
  id: number;
  user_id: number;
  activation_id: string | null;
  phone: string | null;
  service: string;
  service_name: string;
  country: string;
  country_name: string;
  cost_usd: number;
  price_paise: number;
  status: "buying" | "waiting" | "received" | "completed" | "cancelled" | "failed";
  codes: string;
  error: string | null;
  chat_id: number | null;
  message_id: number | null;
  created_at: number;
  expires_at: number;
  updated_at: number;
  checked_at: number;
};

export class OrderError extends Error {}

export function getOrder(id: number): OrderRow | undefined {
  return db().prepare("SELECT * FROM orders WHERE id = ?").get(id) as OrderRow | undefined;
}

export function orderBelongsTo(o: OrderRow, userId: number): boolean {
  return o.user_id === userId;
}

export function codesOf(o: OrderRow): string[] {
  return JSON.parse(o.codes) as string[];
}

export function setOrderMessage(id: number, chatId: number, messageId: number): void {
  db().prepare("UPDATE orders SET chat_id = ?, message_id = ? WHERE id = ?").run(chatId, messageId, id);
}

/** Cancels the order locally and refunds the customer exactly once. */
export function refundOrder(orderId: number, status: "cancelled" | "failed", error: string | null): void {
  const conn = db();
  conn.transaction(() => {
    const res = conn
      .prepare(
        "UPDATE orders SET status = ?, error = ?, updated_at = ? WHERE id = ? AND status IN ('buying', 'waiting')",
      )
      .run(status, error, now(), orderId);
    if (res.changes !== 1) return;
    const o = getOrder(orderId)!;
    applyBalance(conn, o.user_id, o.price_paise, "refund", `order:${o.id}`, `Refund: ${o.service_name}`);
  })();
}

export async function buyNumber(userId: number, service: string, country: string): Promise<OrderRow> {
  const [services, countries, prices] = await Promise.all([
    grizzly.getServices(),
    grizzly.getCountries(),
    grizzly.getServicePrices(service, true),
  ]);
  const svc = services.find((s) => s.code === service);
  const entry = prices.find((p) => p.country === country);
  if (!svc || !entry || !countries.has(country)) throw new OrderError("This service is not available.");
  if (entry.count <= 0) throw new OrderError("No numbers available right now. Try another country.");

  const { pricePaise, hidden } = makePricer()(service, country, entry.costUsd);
  if (hidden) throw new OrderError("This service is not available.");

  const t = now();
  const timeoutMs = getSettingNumber("order_timeout_min") * 60_000;
  const conn = db();

  // 1) Reserve the money and create the order atomically.
  const orderId = conn.transaction((): number => {
    const info = conn
      .prepare(
        `INSERT INTO orders (user_id, service, service_name, country, country_name, cost_usd, price_paise, status, created_at, expires_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, 'buying', ?, ?, ?)`,
      )
      .run(userId, service, svc.name, country, countries.get(country)!, entry.costUsd, pricePaise, t, t + timeoutMs, t);
    const id = Number(info.lastInsertRowid);
    if (!applyBalance(conn, userId, -pricePaise, "order", `order:${id}`, `Number: ${svc.name}`)) {
      throw new OrderError("Not enough balance. Please add money first.");
    }
    return id;
  })();

  // 2) Buy from GrizzlySMS, never paying more than the cost we priced at.
  try {
    const { activationId, phone } = await grizzly.getNumber({ service, country, maxPrice: entry.costUsd });
    const t2 = now();
    conn
      .prepare(
        "UPDATE orders SET activation_id = ?, phone = ?, status = 'waiting', created_at = ?, expires_at = ?, updated_at = ? WHERE id = ?",
      )
      .run(activationId, phone, t2, t2 + timeoutMs, t2, orderId);
    return getOrder(orderId)!;
  } catch (err) {
    const code = err instanceof grizzly.GrizzlyError ? err.code : "NETWORK_ERROR";
    console.error("[order] getNumber failed", orderId, err);
    refundOrder(orderId, "failed", code);
    throw new OrderError(grizzly.friendlyError(code));
  }
}

export function addCode(o: OrderRow, code: string): boolean {
  const codes = codesOf(o);
  if (codes[codes.length - 1] === code) return false;
  codes.push(code);
  const res = db()
    .prepare(
      "UPDATE orders SET codes = ?, status = 'received', updated_at = ? WHERE id = ? AND status IN ('waiting', 'received')",
    )
    .run(JSON.stringify(codes), now(), o.id);
  return res.changes === 1;
}

const cancelled = (res: string): boolean =>
  res === "ACCESS_CANCEL" || res === "NO_ACTIVATION" || res === "STATUS_CANCEL";

/** How long after purchase a customer may cancel (GrizzlySMS refuses earlier). */
export const CANCEL_AFTER_MS = 5 * 60_000;

export async function cancelOrder(o: OrderRow): Promise<OrderRow> {
  if (o.status !== "waiting") throw new OrderError("This order can't be cancelled.");
  if (now() < o.created_at + CANCEL_AFTER_MS) {
    throw new OrderError("You can cancel about 5 minutes after purchase. Please wait a little.");
  }
  const res = await grizzly.setStatus(o.activation_id!, 8);
  if (cancelled(res)) {
    refundOrder(o.id, "cancelled", null);
    return getOrder(o.id)!;
  }
  const st = await grizzly.getStatus(o.activation_id!).catch(() => null);
  if (st?.state === "code") addCode(o, st.code);
  throw new OrderError(grizzly.friendlyError(res));
}

export async function requestAnotherSms(o: OrderRow): Promise<void> {
  if (o.status !== "received") throw new OrderError("No OTP received yet.");
  const res = await grizzly.setStatus(o.activation_id!, 3);
  if (!res.startsWith("ACCESS_RETRY_GET") && !res.startsWith("ACCESS_READY")) {
    throw new OrderError(grizzly.friendlyError(res));
  }
}

export async function finishOrder(o: OrderRow): Promise<void> {
  await grizzly.setStatus(o.activation_id!, 6).catch((e) => console.error("[order] finish", e));
  db().prepare("UPDATE orders SET status = 'completed', updated_at = ? WHERE id = ? AND status = 'received'").run(now(), o.id);
}

/**
 * Background check for one active order. Returns "code" when a new OTP arrived,
 * "closed" when it was refunded/completed, or null when nothing changed.
 * minGapMs avoids hitting the API twice when the user and the worker both poll.
 */
export async function checkOrder(o: OrderRow, minGapMs: number): Promise<"code" | "closed" | null> {
  const t = now();
  const claim = db()
    .prepare("UPDATE orders SET checked_at = ? WHERE id = ? AND checked_at < ?")
    .run(t, o.id, t - minGapMs);
  if (claim.changes !== 1) return null;

  const st = await grizzly.getStatus(o.activation_id!);
  let gotCode = false;
  if (st.state === "code") gotCode = addCode(o, st.code);
  const fresh = getOrder(o.id)!;

  if (st.state === "cancelled" && fresh.status === "waiting") {
    refundOrder(o.id, "cancelled", "Cancelled by provider");
    return "closed";
  }
  if (gotCode) return "code";
  if (now() < fresh.expires_at) return null;

  if (fresh.status === "received") {
    await finishOrder(fresh);
    return "closed";
  }
  if (fresh.status === "waiting") {
    const res = await grizzly.setStatus(o.activation_id!, 8).catch(() => "ERROR");
    if (cancelled(res)) {
      refundOrder(o.id, "cancelled", "No OTP received in time");
      return "closed";
    }
    if (now() > fresh.expires_at + 10 * 60_000) {
      refundOrder(o.id, "cancelled", "No OTP received in time");
      return "closed";
    }
  }
  return null;
}

export function activeOrders(): OrderRow[] {
  return db()
    .prepare("SELECT * FROM orders WHERE status IN ('waiting', 'received') ORDER BY id LIMIT 300")
    .all() as OrderRow[];
}
