"""Reads FamApp payment emails from Gmail over IMAP and auto-credits the matching deposit."""
import email
import imaplib
import re
from email.message import Message
from typing import Optional

import config
import db
from payments import credit_payment

EMAIL_GRACE_MS = 2 * 60_000


class GmailAuthError(Exception):
    """Raised when Gmail rejects the login (wrong App Password / IMAP off)."""


def _domain_of(addr: str) -> str:
    return addr.split("@")[1].lower() if "@" in addr else ""


def _domain_allowed(d: str) -> bool:
    return any(d == a or d.endswith("." + a) for a in config.FAMPAY_DOMAINS)


def _check_dkim(msg: Message, from_addr: str) -> bool:
    headers = msg.get_all("Authentication-Results") or []
    if not headers:
        return False
    value = re.sub(r"\s+", " ", headers[0])  # top-most = the one Gmail added
    if not re.match(r"^\s*mx\.google\.com\b", value, re.I):
        return False
    for m in re.finditer(r"dkim=pass[^;]*?header\.(?:i|d)=@?([a-z0-9.-]+)", value, re.I):
        if _domain_allowed(m.group(1).lower()) and _domain_allowed(_domain_of(from_addr)):
            return True
    return False


def _body_text(msg: Message) -> str:
    text = ""
    html = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain" and not text:
                text = _decode(part)
            elif ctype == "text/html" and not html:
                html = _decode(part)
    else:
        if msg.get_content_type() == "text/html":
            html = _decode(msg)
        else:
            text = _decode(msg)
    raw = text or re.sub(r"<[^>]+>", " ", re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.I))
    raw = raw.replace("\u00a0", " ").replace("&nbsp;", " ")
    raw = re.sub(r"&#8377;|&#x20b9;", "\u20b9", raw, flags=re.I)
    return re.sub(r"\s+", " ", raw).strip()


def _decode(part: Message) -> str:
    try:
        payload = part.get_payload(decode=True)
        if payload is None:
            return ""
        return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def extract_fields(text: str) -> tuple[Optional[int], Optional[str]]:
    amounts = []
    for m in re.finditer(r"(?:\u20b9|rs\.?|inr)\s*([\d,]+(?:\.\d{1,2})?)", text, re.I):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if v > 0:
            amounts.append((v, m.start()))
    kw = re.search(r"(received|credited|paid you|sent you)", text, re.I)
    pick = None
    if kw:
        after = [a for a in amounts if a[1] > kw.start()]
        pick = after[0] if after else None
    if pick is None and amounts:
        pick = amounts[0]
    amount_paise = round(pick[0] * 100) if pick else None

    utr = None
    m = re.search(r"\b(FMP[A-Z0-9]{6,24})\b", text, re.I)
    if m:
        utr = m.group(1).upper()
    else:
        m = re.search(r"(?:utr|rrn|upi ref(?:erence)?|ref(?:erence)?\.? ?(?:no|number|id)?|transaction id)[^0-9]{0,25}(\d{12})\b", text, re.I)
        if m:
            utr = m.group(1)
        else:
            m = re.search(r"\b(\d{12})\b", text)
            utr = m.group(1) if m else None
    return amount_paise, utr


def parse_email(source: bytes) -> dict:
    msg = email.message_from_bytes(source)
    from_tuple = email.utils.parseaddr(msg.get("From", ""))
    from_addr = from_tuple[1].lower()
    text = _body_text(msg)
    amount_paise, utr = extract_fields(text)
    date_ms = db.now()
    try:
        dt = email.utils.parsedate_to_datetime(msg.get("Date", ""))
        if dt:
            date_ms = int(dt.timestamp() * 1000)
    except (TypeError, ValueError):
        pass
    return {
        "message_id": msg.get("Message-ID") or f"no-id:{from_addr}:{date_ms}:{text[:40]}",
        "from": from_addr,
        "subject": msg.get("Subject", ""),
        "date": date_ms,
        "text": text,
        "amount_paise": amount_paise,
        "utr": utr,
        "dkim_ok": _check_dkim(msg, from_addr),
    }


def process_alert(a: dict) -> Optional[dict]:
    """Store a relevant email; if it matches an open deposit, credit it. Returns the paid deposit."""
    if not _domain_allowed(_domain_of(a["from"])):
        return None
    if db.one("SELECT id FROM emails WHERE message_id = ?", (a["message_id"],)):
        return None

    status, reason, payment = "unmatched", None, None
    if config.REQUIRE_DKIM and not a["dkim_ok"]:
        status, reason = "ignored", "Sender not verified (DKIM failed)"
    elif a["amount_paise"] is None:
        reason = "Amount not found in email"
    elif a["utr"] and db.one("SELECT id FROM payments WHERE utr = ?", (a["utr"],)):
        status, reason = "ignored", "Transaction ID already used"
    else:
        # 1) A customer who submitted this exact Transaction ID for a deposit of this amount.
        claimed = None
        if a["utr"]:
            claimed = db.one(
                "SELECT * FROM payments WHERE claimed_utr = ? AND amount_paise = ? AND status IN ('pending', 'expired')",
                (a["utr"], a["amount_paise"]),
            )
        if claimed:
            payment = dict(claimed)
        else:
            # 2) Otherwise match by the unique amount within the window.
            rows = db.q(
                "SELECT * FROM payments WHERE amount_paise = ? AND status IN ('pending', 'expired') "
                "AND created_at <= ? AND expires_at >= ?",
                (a["amount_paise"], a["date"] + 60_000, a["date"] - EMAIL_GRACE_MS),
            )
            if len(rows) == 1:
                payment = dict(rows[0])
            elif len(rows) > 1:
                reason = "More than one open deposit with this amount"
            else:
                reason = "No open deposit with this exact amount"

    cur = db.execute(
        "INSERT INTO emails (message_id, from_addr, subject, received_at, amount_paise, utr, dkim_ok, status, reason, "
        "snippet, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (a["message_id"], a["from"], a["subject"][:200], a["date"], a["amount_paise"], a["utr"],
         1 if a["dkim_ok"] else 0, status, reason, a["text"][:600], db.now()),
    )
    if not payment:
        return None
    paid = credit_payment(payment["id"], a["utr"], cur.lastrowid)
    if not paid:
        db.execute("UPDATE emails SET status = 'ignored', reason = 'Duplicate' WHERE id = ?", (cur.lastrowid,))
        return None
    return paid


def poll_gmail() -> list[dict]:
    """Connect, process new emails, return credited deposits."""
    if not config.gmail_configured():
        return []
    credited: list[dict] = []
    imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    try:
        try:
            imap.login(config.GMAIL_USER, config.GMAIL_APP_PASSWORD)
        except imaplib.IMAP4.error as e:
            db.set_state("gmail_status", "auth_failed")
            raise GmailAuthError(str(e))
        db.set_state("gmail_status", "ok")
        imap.select("INBOX")
        last_uid = int(db.get_state("gmail_last_uid") or 0)
        if last_uid:
            typ, data = imap.uid("search", None, f"UID {last_uid + 1}:*")
        else:
            import time as _t

            since = _t.strftime("%d-%b-%Y", _t.gmtime(_t.time() - 3600))
            typ, data = imap.uid("search", None, f"(SINCE {since})")
        uids = [int(x) for x in (data[0].split() if data and data[0] else [])]
        uids = [u for u in sorted(uids) if u > last_uid][:100]
        for uid in uids:
            typ, msg_data = imap.uid("fetch", str(uid), "(RFC822)")
            if msg_data and msg_data[0] and isinstance(msg_data[0], tuple):
                try:
                    paid = process_alert(parse_email(msg_data[0][1]))
                    if paid:
                        credited.append(paid)
                except Exception as e:  # noqa: BLE001
                    print("[gmail] process uid", uid, e)
            last_uid = max(last_uid, uid)
        if uids or not db.get_state("gmail_last_uid"):
            db.set_state("gmail_last_uid", str(last_uid))
        db.set_state("gmail_last_ok", str(db.now()))
    finally:
        try:
            imap.logout()
        except Exception:  # noqa: BLE001
            pass
    return credited
