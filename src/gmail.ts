import { ImapFlow } from "imapflow";
import { simpleParser, type ParsedMail } from "mailparser";
import { config } from "./config.js";
import { db, getState, now, setState } from "./db.js";
import { creditPayment, type PaymentRow } from "./payments.js";

/**
 * Reads FamApp payment emails ("You have successfully received ₹40.0 …",
 * "Transaction ID : FMPIB…", from no-reply@famapp.in) over IMAP and credits the
 * open deposit whose unique amount matches. This is what makes deposits automatic.
 *
 * The exact FamApp layout can change; the parser is generic (₹ amount + FMP/UTR id).
 */

export type ParsedAlert = {
  messageId: string;
  from: string;
  subject: string;
  date: number;
  text: string;
  amountPaise: number | null;
  utr: string | null;
  dkimOk: boolean;
};

export type DepositCredited = { payment: PaymentRow; utr: string | null };

const domainOf = (addr: string): string => addr.split("@")[1]?.toLowerCase() ?? "";
const domainAllowed = (d: string): boolean => config.fampayDomains.some((a) => d === a || d.endsWith("." + a));

const EMAIL_GRACE_MS = 2 * 60_000;

function checkDkim(mail: ParsedMail, fromAddr: string): boolean {
  const first = mail.headerLines.find((h) => h.key === "authentication-results");
  if (!first) return false;
  const value = first.line.replace(/^authentication-results:\s*/i, "").replace(/\s+/g, " ");
  if (!/^mx\.google\.com\b/i.test(value)) return false;
  const re = /dkim=pass[^;]*?header\.(?:i|d)=@?([a-z0-9.-]+)/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(value))) {
    if (domainAllowed(m[1]!.toLowerCase()) && domainAllowed(domainOf(fromAddr))) return true;
  }
  return false;
}

function toText(mail: ParsedMail): string {
  const raw =
    mail.text ||
    (typeof mail.html === "string"
      ? mail.html.replace(/<style[\s\S]*?<\/style>/gi, " ").replace(/<[^>]+>/g, " ")
      : "");
  return raw.replace(/&nbsp;/g, " ").replace(/&#8377;|&#x20b9;/gi, "₹").replace(/\s+/g, " ").trim();
}

export function extractFields(text: string): { amountPaise: number | null; utr: string | null } {
  const amountRe = /(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d{1,2})?)/gi;
  const amounts: { value: number; index: number }[] = [];
  let m: RegExpExecArray | null;
  while ((m = amountRe.exec(text))) {
    const v = Number(m[1]!.replace(/,/g, ""));
    if (Number.isFinite(v) && v > 0) amounts.push({ value: v, index: m.index });
  }
  const kw = /(received|credited|paid you|sent you)/i.exec(text);
  const pick = (kw && amounts.find((a) => a.index > kw.index)) || amounts[0];
  const amountPaise = pick ? Math.round(pick.value * 100) : null;

  const utr =
    /\b(FMP[A-Z0-9]{6,24})\b/i.exec(text)?.[1]?.toUpperCase() ??
    /(?:utr|rrn|upi ref(?:erence)?|ref(?:erence)?\.? ?(?:no|number|id)?|transaction id)[^0-9]{0,25}(\d{12})\b/i.exec(text)?.[1] ??
    /\b(\d{12})\b/.exec(text)?.[1] ??
    null;
  return { amountPaise, utr };
}

export async function parseEmail(source: Buffer): Promise<ParsedAlert> {
  const mail = await simpleParser(source);
  const from = mail.from?.value?.[0]?.address?.toLowerCase() ?? "";
  const text = toText(mail);
  return {
    messageId: mail.messageId ?? `no-id:${from}:${mail.date?.getTime() ?? 0}:${text.slice(0, 40)}`,
    from,
    subject: mail.subject ?? "",
    date: mail.date?.getTime() ?? now(),
    text,
    dkimOk: checkDkim(mail, from),
    ...extractFields(text),
  };
}

/** Stores a relevant email and, if it matches an open deposit, credits it. Returns the credited deposit. */
export function processAlert(a: ParsedAlert): DepositCredited | null {
  const relevant = domainAllowed(domainOf(a.from));
  if (!relevant) return null;
  const conn = db();
  if (conn.prepare("SELECT id FROM emails WHERE message_id = ?").get(a.messageId)) return null;

  let status = "unmatched";
  let reason: string | null = null;
  let payment: PaymentRow | undefined;

  if (config.requireDkim && !a.dkimOk) {
    status = "ignored";
    reason = "Sender not verified (DKIM failed)";
  } else if (a.amountPaise === null) {
    reason = "Amount not found in email";
  } else if (a.utr && conn.prepare("SELECT id FROM payments WHERE utr = ?").get(a.utr)) {
    status = "ignored";
    reason = "Transaction ID already used";
  } else {
    const candidates = conn
      .prepare(
        `SELECT * FROM payments
         WHERE amount_paise = ? AND status IN ('pending', 'expired')
           AND created_at <= ? AND expires_at >= ?`,
      )
      .all(a.amountPaise, a.date + 60_000, a.date - EMAIL_GRACE_MS) as PaymentRow[];
    if (candidates.length === 1) payment = candidates[0];
    else if (candidates.length > 1) reason = "More than one open deposit with this amount";
    else reason = "No open deposit with this exact amount";
  }

  const info = conn
    .prepare(
      `INSERT INTO emails (message_id, from_addr, subject, received_at, amount_paise, utr, dkim_ok, status, reason, snippet, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .run(
      a.messageId,
      a.from,
      a.subject.slice(0, 200),
      a.date,
      a.amountPaise,
      a.utr,
      a.dkimOk ? 1 : 0,
      status,
      reason,
      a.text.slice(0, 600),
      now(),
    );

  if (!payment) return null;
  const paid = creditPayment(payment.id, a.utr, Number(info.lastInsertRowid));
  if (!paid) {
    conn.prepare("UPDATE emails SET status = 'ignored', reason = 'Duplicate' WHERE id = ?").run(info.lastInsertRowid);
    return null;
  }
  return { payment: paid, utr: a.utr };
}

export function gmailConfigured(): boolean {
  return Boolean(config.gmailUser && config.gmailAppPassword);
}

/** Connects to Gmail, processes new emails, and returns the deposits credited this run. */
export async function pollGmail(): Promise<DepositCredited[]> {
  if (!gmailConfigured()) return [];
  const client = new ImapFlow({
    host: "imap.gmail.com",
    port: 993,
    secure: true,
    auth: { user: config.gmailUser, pass: config.gmailAppPassword },
    logger: false,
  });
  client.on("error", (err: Error) => console.error("[gmail] connection error", err.message));
  await client.connect();
  const credited: DepositCredited[] = [];
  try {
    const lock = await client.getMailboxLock("INBOX");
    try {
      const mailbox = client.mailbox && typeof client.mailbox === "object" ? client.mailbox : null;
      const validity = mailbox ? String(mailbox.uidValidity) : "0";
      const sameBox = getState("gmail_uidvalidity") === validity;
      let lastUid = sameBox ? Number(getState("gmail_last_uid") ?? 0) : 0;

      let uids: number[];
      if (!lastUid) {
        const found = await client.search({ since: new Date(Date.now() - 3_600_000) }, { uid: true });
        uids = Array.isArray(found) ? found : [];
      } else {
        const found = await client.search({ uid: `${lastUid + 1}:*` }, { uid: true });
        uids = (Array.isArray(found) ? found : []).filter((u) => u > lastUid);
      }

      for (const uid of uids.sort((x, y) => x - y).slice(0, 100)) {
        const msg = await client.fetchOne(String(uid), { source: true }, { uid: true });
        if (msg && msg.source) {
          try {
            const got = processAlert(await parseEmail(msg.source));
            if (got) credited.push(got);
          } catch (err) {
            console.error("[gmail] failed to process uid", uid, err);
          }
        }
        lastUid = Math.max(lastUid, uid);
      }
      if (!lastUid && mailbox) lastUid = Math.max(0, Number(mailbox.uidNext) - 1);
      setState("gmail_last_uid", String(lastUid));
      setState("gmail_uidvalidity", validity);
      setState("gmail_last_ok", String(now()));
    } finally {
      lock.release();
    }
  } finally {
    await client.logout().catch(() => client.close());
  }
  return credited;
}
