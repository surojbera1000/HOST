import { countryOptions, popularServices, searchServices, serviceName, type CountryOption } from "./catalog.js";
import { config } from "./config.js";
import { db, getSetting, now } from "./db.js";
import { esc, flag, inr } from "./format.js";
import { getBalanceUsd } from "./grizzly.js";
import { notifyAdmins } from "./notify.js";
import {
  buyNumber,
  cancelOrder,
  checkOrder,
  finishOrder,
  getOrder,
  OrderError,
  orderBelongsTo,
  requestAnotherSms,
  setOrderMessage,
  type OrderRow,
} from "./orders.js";
import {
  cancelPayment,
  createPayment,
  getPayment,
  PaymentError,
  qrPng,
  setPaymentMessage,
} from "./payments.js";
import { depositCaption, depositKeyboard, mainMenu, orderView } from "./render.js";
import {
  answerCallback,
  btn,
  editCaption,
  editMessage,
  kb,
  sendMessage,
  sendPhoto,
  urlBtn,
  type InlineButton,
} from "./tg.js";
import { getOrCreateUser, isAdmin, userByTelegramId, type TgFrom, type User } from "./users.js";

// ---------- lightweight per-user session (search / custom amount) ----------

type Session = { mode: "search" | "amount"; at: number };
const sessions = new Map<number, Session>();
const setSession = (tid: number, mode: Session["mode"]): void => void sessions.set(tid, { mode, at: now() });
const takeSession = (tid: number): Session | undefined => {
  const s = sessions.get(tid);
  if (!s) return undefined;
  sessions.delete(tid);
  if (now() - s.at > 5 * 60_000) return undefined;
  return s;
};

const COUNTRIES_PER_PAGE = 8;

// ---------- update entry point ----------

type Update = {
  update_id: number;
  message?: { message_id: number; chat: { id: number }; from?: TgFrom; text?: string };
  callback_query?: {
    id: string;
    from: TgFrom;
    message?: { message_id: number; chat: { id: number } };
    data?: string;
  };
};

export async function handleUpdate(u: Update): Promise<void> {
  try {
    if (u.message) await onMessage(u.message);
    else if (u.callback_query) await onCallback(u.callback_query);
  } catch (err) {
    console.error("[bot] update error", err);
  }
}

// ---------- messages ----------

async function onMessage(msg: NonNullable<Update["message"]>): Promise<void> {
  if (!msg.from || !msg.text) return;
  const { user, isNew } = getOrCreateUser(msg.from);
  const chatId = msg.chat.id;
  const text = msg.text.trim();

  if (isNew) {
    await notifyAdmins(
      `🆕 New bot user: ${esc(msg.from.first_name ?? "")} ${msg.from.username ? "@" + esc(msg.from.username) : ""} (id ${msg.from.id})`,
    );
  }

  if (text.startsWith("/start")) {
    sessions.delete(msg.from.id);
    const m = mainMenu(user);
    await sendMessage(chatId, m.text, m.keyboard);
    return;
  }
  if (text === "/balance") {
    await sendMessage(chatId, `💰 Your balance: <b>${inr(user.balance_paise)}</b>`);
    return;
  }
  if (text === "/admin" && isAdmin(msg.from.id)) {
    await sendAdminStats(chatId);
    return;
  }

  // Session text (search query or custom deposit amount)
  const session = takeSession(msg.from.id);
  if (session?.mode === "search") {
    await showServiceSearch(chatId, text);
    return;
  }
  if (session?.mode === "amount") {
    await startDeposit(user, chatId, Number(text.replace(/[^\d]/g, "")));
    return;
  }

  // Fallback
  const m = mainMenu(user);
  await sendMessage(chatId, m.text, m.keyboard);
}

// ---------- callbacks ----------

async function onCallback(cq: NonNullable<Update["callback_query"]>): Promise<void> {
  const data = cq.data ?? "";
  const chatId = cq.message?.chat.id;
  const messageId = cq.message?.message_id;
  const { user } = getOrCreateUser(cq.from);
  if (chatId === undefined || messageId === undefined) {
    await answerCallback(cq.id);
    return;
  }
  if (user.blocked) {
    await answerCallback(cq.id, "Your account is blocked. Contact support.", true);
    return;
  }

  const ack = (text?: string, alert = false): Promise<unknown> => answerCallback(cq.id, text, alert);
  const edit = (text: string, keyboard?: ReturnType<typeof kb>): Promise<void> =>
    editMessage(chatId, messageId, text, keyboard);
  const [cmd, ...args] = data.split(":");

  try {
    switch (cmd) {
      case "noop":
        return void (await ack());
      case "mm":
      case "bal": {
        const fresh = userByTelegramId(cq.from.id)!;
        const m = mainMenu(fresh);
        await edit(m.text, m.keyboard);
        return void (await ack());
      }
      case "buy":
        await showServices(edit);
        return void (await ack());
      case "ss":
        setSession(cq.from.id, "search");
        await edit("🔍 <b>Search app</b>\n\nSend me the app name (for example: <i>WhatsApp</i>, <i>Telegram</i>, <i>Instagram</i>).");
        return void (await ack());
      case "sv":
        await showCountries(edit, args[0]!, 0);
        return void (await ack());
      case "ct":
        await showCountries(edit, args[0]!, Number(args[1] ?? 0));
        return void (await ack());
      case "cf":
        await showConfirm(edit, user, args[0]!, args[1]!);
        return void (await ack());
      case "bx":
        await doBuy(cq.from, chatId, messageId, args[0]!, args[1]!, ack);
        return;
      case "dep":
        await showDepositMenu(edit);
        return void (await ack());
      case "da":
        await ack("Creating your QR…");
        await startDeposit(user, chatId, Number(args[0]));
        return;
      case "dc":
        setSession(cq.from.id, "amount");
        await edit("💰 <b>Add money</b>\n\nSend the amount in ₹ (whole number), for example <b>100</b>.");
        return void (await ack());
      case "dcl": {
        const p = getPayment(Number(args[0]));
        if (p && p.user_id === user.id) cancelPayment(p.id);
        await editCaption(chatId, messageId, "🚫 Deposit cancelled.", depositKeyboard({ ...p!, status: "cancelled" }));
        return void (await ack("Cancelled"));
      }
      case "ords":
        await showOrders(edit, user);
        return void (await ack());
      case "op":
        await openOrder(edit, user, Number(args[0]));
        return void (await ack());
      case "chk":
        await checkNow(chatId, messageId, user, Number(args[0]), ack);
        return;
      case "ccl":
        await doCancel(chatId, messageId, user, Number(args[0]), ack);
        return;
      case "rty":
        await doRetry(chatId, messageId, user, Number(args[0]), ack);
        return;
      case "don":
        await doDone(chatId, messageId, user, Number(args[0]), ack);
        return;
      default:
        return void (await ack());
    }
  } catch (err) {
    console.error("[bot] callback error", data, err);
    const msg = err instanceof OrderError || err instanceof PaymentError ? err.message : "Something went wrong. Try again.";
    await ack(msg, true);
  }
}

type EditFn = (text: string, keyboard?: ReturnType<typeof kb>) => Promise<void>;

// ---------- buy flow ----------

async function showServices(edit: EditFn): Promise<void> {
  const services = await popularServices();
  const rows: InlineButton[][] = [];
  for (let i = 0; i < services.length; i += 2) {
    rows.push(
      services.slice(i, i + 2).map((s) => btn(s.name.length > 20 ? s.name.slice(0, 19) + "…" : s.name, `sv:${s.code}`)),
    );
  }
  rows.push([btn("🔍 Search other app", "ss", "primary")]);
  rows.push([btn("🏠 Menu", "mm")]);
  await edit("📱 <b>Choose an app</b>\n\nPick the app you want a number for:", kb(rows));
}

async function showServiceSearch(chatId: number, query: string): Promise<void> {
  const found = await searchServices(query);
  if (!found.length) {
    await sendMessage(chatId, `No app found for “${esc(query)}”. Try another name.`, kb([[btn("🔍 Search again", "ss"), btn("🏠 Menu", "mm")]]));
    return;
  }
  const rows: InlineButton[][] = [];
  for (let i = 0; i < found.length; i += 2) {
    rows.push(found.slice(i, i + 2).map((s) => btn(s.name.length > 20 ? s.name.slice(0, 19) + "…" : s.name, `sv:${s.code}`)));
  }
  rows.push([btn("🏠 Menu", "mm")]);
  await sendMessage(chatId, `🔍 Results for “${esc(query)}”:`, kb(rows));
}

async function showCountries(edit: EditFn, service: string, page: number): Promise<void> {
  const all = await popularServices();
  const name = serviceName(all, service);
  let list: CountryOption[];
  try {
    list = await countryOptions(service);
  } catch {
    await edit("Could not load prices. Please try again.", kb([[btn("🔄 Retry", `sv:${service}`), btn("🏠 Menu", "mm")]]));
    return;
  }
  if (!list.length) {
    await edit(`No numbers available for <b>${esc(name)}</b> right now.`, kb([[btn("⬅️ Back", "buy"), btn("🏠 Menu", "mm")]]));
    return;
  }
  const pages = Math.ceil(list.length / COUNTRIES_PER_PAGE);
  const p = Math.max(0, Math.min(page, pages - 1));
  const slice = list.slice(p * COUNTRIES_PER_PAGE, (p + 1) * COUNTRIES_PER_PAGE);
  const rows: InlineButton[][] = slice.map((c) => [
    btn(`${flag(c.name)} ${c.name} · ${inr(c.pricePaise)} · ${c.count > 999 ? Math.floor(c.count / 1000) + "k" : c.count}`, `cf:${service}:${c.country}`),
  ]);
  const nav: InlineButton[] = [];
  if (p > 0) nav.push(btn("⬅️ Prev", `ct:${service}:${p - 1}`));
  if (p < pages - 1) nav.push(btn("Next ➡️", `ct:${service}:${p + 1}`));
  if (nav.length) rows.push(nav);
  rows.push([btn("⬅️ Apps", "buy"), btn("🏠 Menu", "mm")]);
  await edit(`${flag("")} <b>${esc(name)}</b> — choose a country\n<i>Cheapest first · page ${p + 1}/${pages}</i>`, kb(rows));
}

async function showConfirm(edit: EditFn, user: User, service: string, country: string): Promise<void> {
  const list = await countryOptions(service);
  const c = list.find((x) => x.country === country);
  const all = await popularServices();
  const name = serviceName(all, service);
  if (!c) {
    await edit("That option is gone. Please pick again.", kb([[btn("⬅️ Back", `sv:${service}`), btn("🏠 Menu", "mm")]]));
    return;
  }
  const enough = user.balance_paise >= c.pricePaise;
  const text =
    `🧾 <b>Confirm purchase</b>\n\n` +
    `App: <b>${esc(name)}</b>\n` +
    `Country: ${flag(c.name)} <b>${esc(c.name)}</b>\n` +
    `Price: <b>${inr(c.pricePaise)}</b>\n` +
    `Your balance: ${inr(user.balance_paise)}\n\n` +
    (enough ? `✅ If no OTP comes, you can cancel and get a refund.` : `❌ Not enough balance. Add money first.`);
  const rows: InlineButton[][] = enough
    ? [[btn(`✅ Buy for ${inr(c.pricePaise)}`, `bx:${service}:${country}`, "success")], [btn("⬅️ Back", `sv:${service}`), btn("🏠 Menu", "mm")]]
    : [[btn("💰 Add money", "dep", "success")], [btn("⬅️ Back", `sv:${service}`), btn("🏠 Menu", "mm")]];
  await edit(text, kb(rows));
}

async function doBuy(
  from: TgFrom,
  chatId: number,
  messageId: number,
  service: string,
  country: string,
  ack: (t?: string, a?: boolean) => Promise<unknown>,
): Promise<void> {
  const user = userByTelegramId(from.id)!;
  await ack("Getting your number…");
  let order: OrderRow;
  try {
    order = await buyNumber(user.id, service, country);
  } catch (err) {
    const m = err instanceof OrderError ? err.message : "Could not buy. Try again.";
    await editMessage(chatId, messageId, `❌ ${esc(m)}`, kb([[btn("⬅️ Back", `sv:${service}`), btn("🏠 Menu", "mm")]]));
    return;
  }
  setOrderMessage(order.id, chatId, messageId);
  const v = orderView(order, now());
  await editMessage(chatId, messageId, v.text, v.keyboard);
}

// ---------- orders ----------

async function showOrders(edit: EditFn, user: User): Promise<void> {
  const rows = db()
    .prepare("SELECT * FROM orders WHERE user_id = ? AND status != 'buying' ORDER BY id DESC LIMIT 10")
    .all(user.id) as OrderRow[];
  if (!rows.length) {
    await edit("🧾 You have no numbers yet.", kb([[btn("📱 Buy a number", "buy", "primary"), btn("🏠 Menu", "mm")]]));
    return;
  }
  const buttons: InlineButton[][] = rows.map((o) => {
    const tag =
      o.status === "received" ? "🔥 OTP" : o.status === "waiting" ? "⏳ waiting" : o.status === "completed" ? "✅" : "↩️";
    return [btn(`${flag(o.country_name)} ${o.service_name} · ${tag}`, `op:${o.id}`)];
  });
  buttons.push([btn("🏠 Menu", "mm")]);
  await edit("🧾 <b>My numbers</b>\n\nTap one to open:", kb(buttons));
}

async function openOrder(edit: EditFn, user: User, orderId: number): Promise<void> {
  const o = getOrder(orderId);
  if (!o || !orderBelongsTo(o, user.id)) {
    await edit("Order not found.", kb([[btn("🏠 Menu", "mm")]]));
    return;
  }
  const v = orderView(o, now());
  setOrderMessage(o.id, 0, 0); // detach old live message; this view becomes the live one below
  await edit(v.text, v.keyboard);
}

async function checkNow(
  chatId: number,
  messageId: number,
  user: User,
  orderId: number,
  ack: (t?: string, a?: boolean) => Promise<unknown>,
): Promise<void> {
  const o = getOrder(orderId);
  if (!o || !orderBelongsTo(o, user.id)) return void (await ack("Order not found.", true));
  setOrderMessage(o.id, chatId, messageId);
  if (o.status === "waiting" || o.status === "received") {
    try {
      await checkOrder(o, 0);
    } catch (err) {
      console.error("[bot] checkNow", err);
    }
  }
  const fresh = getOrder(orderId)!;
  const v = orderView(fresh, now());
  await editMessage(chatId, messageId, v.text, v.keyboard);
  await ack(codesOfHasNew(o, fresh) ? "OTP received!" : fresh.status === "waiting" ? "No OTP yet. Keep waiting." : "Updated");
}

function codesOfHasNew(before: OrderRow, after: OrderRow): boolean {
  return (JSON.parse(after.codes) as string[]).length > (JSON.parse(before.codes) as string[]).length;
}

async function doCancel(
  chatId: number,
  messageId: number,
  user: User,
  orderId: number,
  ack: (t?: string, a?: boolean) => Promise<unknown>,
): Promise<void> {
  const o = getOrder(orderId);
  if (!o || !orderBelongsTo(o, user.id)) return void (await ack("Order not found.", true));
  setOrderMessage(o.id, chatId, messageId);
  try {
    const updated = await cancelOrder(o);
    const v = orderView(updated, now());
    await editMessage(chatId, messageId, v.text, v.keyboard);
    await ack("Cancelled and refunded");
  } catch (err) {
    const m = err instanceof OrderError ? err.message : "Could not cancel.";
    await ack(m, true);
    const fresh = getOrder(orderId)!;
    const v = orderView(fresh, now());
    await editMessage(chatId, messageId, v.text, v.keyboard);
  }
}

async function doRetry(
  chatId: number,
  messageId: number,
  user: User,
  orderId: number,
  ack: (t?: string, a?: boolean) => Promise<unknown>,
): Promise<void> {
  const o = getOrder(orderId);
  if (!o || !orderBelongsTo(o, user.id)) return void (await ack("Order not found.", true));
  try {
    await requestAnotherSms(o);
    await ack("Asked for another OTP. Wait a moment.");
  } catch (err) {
    await ack(err instanceof OrderError ? err.message : "Could not request.", true);
  }
}

async function doDone(
  chatId: number,
  messageId: number,
  user: User,
  orderId: number,
  ack: (t?: string, a?: boolean) => Promise<unknown>,
): Promise<void> {
  const o = getOrder(orderId);
  if (!o || !orderBelongsTo(o, user.id)) return void (await ack("Order not found.", true));
  if (o.status === "received") await finishOrder(o);
  const fresh = getOrder(orderId)!;
  const v = orderView(fresh, now());
  await editMessage(chatId, messageId, v.text, v.keyboard);
  await ack("Done");
}

// ---------- deposits ----------

async function showDepositMenu(edit: EditFn): Promise<void> {
  const amounts = [20, 50, 100, 200, 500, 1000];
  const rows: InlineButton[][] = [];
  for (let i = 0; i < amounts.length; i += 3) {
    rows.push(amounts.slice(i, i + 3).map((a) => btn(`₹${a}`, `da:${a}`, "success")));
  }
  rows.push([btn("✏️ Other amount", "dc")]);
  rows.push([btn("🏠 Menu", "mm")]);
  await edit(`💰 <b>Add money</b>\n\nChoose an amount to pay by UPI (min ₹${getSetting("min_topup_inr")}):`, kb(rows));
}

async function startDeposit(user: User, chatId: number, rupees: number): Promise<void> {
  let payment;
  try {
    payment = createPayment(user.id, rupees);
  } catch (err) {
    const m = err instanceof PaymentError ? err.message : "Could not create deposit.";
    await sendMessage(chatId, `❌ ${esc(m)}`, kb([[btn("💰 Try again", "dep", "success"), btn("🏠 Menu", "mm")]]));
    return;
  }
  const png = await qrPng(payment.amount_paise);
  const sent = await sendPhoto(chatId, png, depositCaption(payment, now()), depositKeyboard(payment));
  setPaymentMessage(payment.id, chatId, sent.message_id);
}

// ---------- admin ----------

async function sendAdminStats(chatId: number): Promise<void> {
  const d = db();
  const startOfDay = new Date();
  startOfDay.setHours(0, 0, 0, 0);
  const since = startOfDay.getTime();
  const users = (d.prepare("SELECT COUNT(*) n FROM users").get() as { n: number }).n;
  const sales = d
    .prepare("SELECT COUNT(*) n, COALESCE(SUM(price_paise),0) s FROM orders WHERE status IN ('received','completed') AND created_at >= ?")
    .get(since) as { n: number; s: number };
  const topups = d
    .prepare("SELECT COALESCE(SUM(amount_paise),0) s FROM payments WHERE status = 'paid' AND paid_at >= ?")
    .get(since) as { s: number };
  let bal = "unavailable";
  try {
    bal = `$${(await getBalanceUsd()).toFixed(2)}`;
  } catch {
    /* ignore */
  }
  await sendMessage(
    chatId,
    `📊 <b>Today</b>\n` +
      `Users: ${users}\n` +
      `Numbers sold: ${sales.n} (${inr(sales.s)})\n` +
      `Deposits: ${inr(topups.s)}\n` +
      `GrizzlySMS balance: ${bal}\n\n` +
      `Full controls: open the web admin panel.`,
    kb([[urlBtn("💬 Support", `https://t.me/${config.supportUsername}`)]]),
  );
}
