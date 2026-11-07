import { config } from "./config.js";
import { db, now, setState } from "./db.js";
import { gmailConfigured, pollGmail } from "./gmail.js";
import { inr } from "./format.js";
import { notifyAdmins } from "./notify.js";
import { activeOrders, checkOrder, codesOf, getOrder, type OrderRow } from "./orders.js";
import { depositCaption, depositKeyboard, orderView } from "./render.js";
import { expireOldPayments, type PaymentRow } from "./payments.js";
import { editCaption, editMessage, sendMessage } from "./tg.js";

/** Runs a job on an interval without overlapping runs. */
function every(name: string, ms: number, job: () => Promise<void>): void {
  let running = false;
  const tick = async (): Promise<void> => {
    if (running) return;
    running = true;
    try {
      await job();
    } catch (err) {
      console.error(`[worker:${name}]`, err instanceof Error ? err.message : err);
    } finally {
      running = false;
    }
  };
  setInterval(() => void tick(), ms).unref();
  void tick();
}

async function renderOrder(o: OrderRow): Promise<void> {
  if (!o.chat_id || !o.message_id) return;
  const v = orderView(o, now());
  await editMessage(o.chat_id, o.message_id, v.text, v.keyboard).catch((e) =>
    console.error("[worker] render order", o.id, e instanceof Error ? e.message : e),
  );
}

async function ordersJob(): Promise<void> {
  for (const o of activeOrders()) {
    try {
      const result = await checkOrder(o, 20_000);
      if (result === "code" || result === "closed") {
        const fresh = getOrder(o.id)!;
        await renderOrder(fresh);
        if (result === "code" && fresh.chat_id) {
          const last = codesOf(fresh).slice(-1)[0];
          await sendMessage(fresh.chat_id, `🔥 <b>OTP received:</b> <code>${last}</code>`).catch(() => undefined);
        }
      }
    } catch (err) {
      console.error("[worker:orders]", o.id, err instanceof Error ? err.message : err);
    }
  }
}

async function depositsJob(): Promise<void> {
  // Edit any deposit messages whose timer just ended.
  const expiring = db()
    .prepare("SELECT * FROM payments WHERE status = 'pending' AND expires_at < ? AND message_id IS NOT NULL")
    .all(now()) as PaymentRow[];
  expireOldPayments();
  for (const p of expiring) {
    const fresh = db().prepare("SELECT * FROM payments WHERE id = ?").get(p.id) as PaymentRow;
    if (fresh.status !== "paid" && fresh.chat_id && fresh.message_id) {
      await editCaption(fresh.chat_id, fresh.message_id, depositCaption(fresh, now()), depositKeyboard(fresh)).catch(
        () => undefined,
      );
    }
  }
}

async function gmailJob(): Promise<void> {
  const credited = await pollGmail();
  for (const { payment } of credited) {
    const fresh = db().prepare("SELECT * FROM payments WHERE id = ?").get(payment.id) as PaymentRow;
    if (fresh.chat_id && fresh.message_id) {
      await editCaption(fresh.chat_id, fresh.message_id, depositCaption(fresh, now()), depositKeyboard(fresh)).catch(
        () => undefined,
      );
      await sendMessage(fresh.chat_id, `✅ <b>${inr(fresh.amount_paise)} added to your wallet.</b>`).catch(() => undefined);
    }
    await notifyAdmins(`💰 Deposit credited: ${inr(fresh.amount_paise)} (payment #${fresh.id})`);
  }
  setState("gmail_last_run", String(now()));
}

export function startWorkers(): void {
  every("orders", 10_000, ordersJob);
  every("deposits", 60_000, depositsJob);
  if (gmailConfigured()) every("gmail", config.gmailPollSeconds * 1000, gmailJob);
  else console.warn("[workers] GMAIL_USER / GMAIL_APP_PASSWORD not set — automatic deposits are OFF");
  console.log("[workers] started");
}
