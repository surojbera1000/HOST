"""Password-protected web admin panel (Flask), runs in a background thread."""
import hmac
import secrets
import threading

from flask import Flask, Response, jsonify, request

import config
import db
import grizzly
from admin_html import ADMIN_HTML
from payments import credit_payment
from pricing import get_price_rules
from wallet import apply_balance

_tokens: set[str] = set()


def _authed(req) -> bool:
    cookie = req.headers.get("Cookie", "")
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith("miku_admin="):
            return part[len("miku_admin="):] in _tokens
    return False


def create_app() -> Flask:
    app = Flask(__name__)

    def guard():
        if not _authed(request):
            return jsonify({"error": "Not logged in"}), 401
        return None

    @app.get("/")
    def index():
        return Response(ADMIN_HTML, mimetype="text/html")

    @app.post("/api/login")
    def login():
        password = str((request.json or {}).get("password", ""))
        ok = len(password) == len(config.ADMIN_PANEL_PASSWORD) and hmac.compare_digest(password, config.ADMIN_PANEL_PASSWORD)
        if not ok:
            return jsonify({"error": "Wrong password"}), 401
        token = secrets.token_urlsafe(24)
        _tokens.add(token)
        resp = jsonify({"ok": True})
        resp.headers["Set-Cookie"] = f"miku_admin={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=86400"
        return resp

    @app.post("/api/logout")
    def logout():
        cookie = request.headers.get("Cookie", "")
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("miku_admin="):
                _tokens.discard(part[len("miku_admin="):])
        resp = jsonify({"ok": True})
        resp.headers["Set-Cookie"] = "miku_admin=; Path=/; Max-Age=0"
        return resp

    @app.get("/api/overview")
    def overview():
        g = guard()
        if g:
            return g
        start = _start_of_day()
        users_n = db.one("SELECT COUNT(*) n FROM users")["n"]
        wallets = db.one("SELECT COALESCE(SUM(balance_paise),0) s FROM users")["s"]
        sales = db.one("SELECT COUNT(*) n, COALESCE(SUM(price_paise),0) s, COALESCE(SUM(cost_usd),0) c FROM orders WHERE status IN ('received','completed') AND created_at >= ?", (start,))
        topups = db.one("SELECT COALESCE(SUM(amount_paise),0) s FROM payments WHERE status = 'paid' AND paid_at >= ?", (start,))
        rate = db.get_setting_number("usd_inr_rate")
        try:
            gusd = grizzly.get_balance_usd()
        except Exception:  # noqa: BLE001
            gusd = None
        return jsonify({
            "users": users_n,
            "walletTotalPaise": wallets,
            "today": {"orders": sales["n"], "salesPaise": sales["s"], "costPaise": round(sales["c"] * rate * 100), "topupPaise": topups["s"]},
            "grizzlyUsd": gusd,
            "grizzlyInrPaise": None if gusd is None else round(gusd * rate * 100),
            "gmail": {"configured": config.gmail_configured(), "lastOk": int(db.get_state("gmail_last_ok") or 0) or None},
        })

    @app.get("/api/settings")
    def get_settings():
        g = guard()
        if g:
            return g
        return jsonify({"settings": db.get_settings()})

    @app.post("/api/settings")
    def set_settings():
        g = guard()
        if g:
            return g
        body = request.json or {}
        for key in db.DEFAULT_SETTINGS:
            if key in body:
                db.set_setting(key, str(body[key]))
        return jsonify({"settings": db.get_settings()})

    @app.get("/api/services")
    def services():
        g = guard()
        if g:
            return g
        try:
            return jsonify({"services": grizzly.get_services()})
        except Exception:  # noqa: BLE001
            return jsonify({"services": []})

    @app.get("/api/rules")
    def rules():
        g = guard()
        if g:
            return g
        return jsonify({"rules": get_price_rules()})

    @app.post("/api/rules")
    def save_rule():
        g = guard()
        if g:
            return g
        import re

        b = request.json or {}
        service = str(b.get("service", "")).strip()
        country = str(b.get("country", "*")).strip() or "*"
        mode = str(b.get("mode", ""))
        value = float(b.get("value", 0) or 0)
        hidden = 1 if b.get("hidden") else 0
        if not re.match(r"^(\*|[a-z0-9_]{1,20})$", service, re.I) or not re.match(r"^(\*|\d{1,5})$", country):
            return jsonify({"error": "Invalid service or country"}), 400
        if mode not in ("default", "markup", "fixed", "plus"):
            return jsonify({"error": "Invalid mode"}), 400
        db.execute(
            "INSERT INTO price_rules (service, country, mode, value, hidden) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(service, country) DO UPDATE SET mode = excluded.mode, value = excluded.value, hidden = excluded.hidden",
            (service, country, mode, value, hidden),
        )
        return jsonify({"rules": get_price_rules()})

    @app.delete("/api/rules/<int:rid>")
    def del_rule(rid):
        g = guard()
        if g:
            return g
        db.execute("DELETE FROM price_rules WHERE id = ?", (rid,))
        return jsonify({"rules": get_price_rules()})

    @app.get("/api/users")
    def list_users():
        g = guard()
        if g:
            return g
        q = "%" + str(request.args.get("q", "")).lower().replace("%", "").replace("_", "") + "%"
        rows = db.q(
            "SELECT u.id, u.telegram_id, u.username, u.first_name, u.balance_paise, u.blocked, u.created_at, "
            "(SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id AND o.status IN ('received','completed')) AS orders, "
            "(SELECT COALESCE(SUM(amount_paise),0) FROM payments p WHERE p.user_id = u.id AND p.status = 'paid') AS topup_paise "
            "FROM users u WHERE CAST(u.telegram_id AS TEXT) LIKE ? OR LOWER(COALESCE(u.username,'')) LIKE ? "
            "OR LOWER(COALESCE(u.first_name,'')) LIKE ? ORDER BY u.id DESC LIMIT 200",
            (q, q, q),
        )
        return jsonify({"users": [dict(r) for r in rows]})

    @app.post("/api/users/<int:uid>/balance")
    def adj_balance(uid):
        g = guard()
        if g:
            return g
        paise = round(float((request.json or {}).get("amount", 0)) * 100)
        note = str((request.json or {}).get("note", "Admin adjustment"))[:200]
        if not paise:
            return jsonify({"error": "Amount can't be zero"}), 400
        with db.tx() as c:
            ok = apply_balance(c, uid, int(paise), "admin", "admin", note)
        if not ok:
            return jsonify({"error": "Balance can't go below \u20b90"}), 400
        return jsonify({"ok": True})

    @app.post("/api/users/<int:uid>/block")
    def block_user(uid):
        g = guard()
        if g:
            return g
        db.execute("UPDATE users SET blocked = ? WHERE id = ?", (1 if (request.json or {}).get("blocked") else 0, uid))
        return jsonify({"ok": True})

    @app.get("/api/deposits")
    def deposits():
        g = guard()
        if g:
            return g
        status = str(request.args.get("status", "all"))
        if status == "all":
            rows = db.q("SELECT p.*, u.telegram_id, u.username FROM payments p JOIN users u ON u.id = p.user_id ORDER BY p.id DESC LIMIT 200")
        else:
            rows = db.q("SELECT p.*, u.telegram_id, u.username FROM payments p JOIN users u ON u.id = p.user_id WHERE p.status = ? ORDER BY p.id DESC LIMIT 200", (status,))
        return jsonify({"deposits": [dict(r) for r in rows]})

    @app.post("/api/deposits/<int:pid>/approve")
    def approve_deposit(pid):
        g = guard()
        if g:
            return g
        utr = (request.json or {}).get("utr")
        utr = str(utr).strip().upper() if utr else None
        paid = credit_payment(pid, utr, None)
        if not paid:
            return jsonify({"error": "Already credited, or this UTR was used before"}), 409
        return jsonify({"ok": True})

    @app.post("/api/deposits/<int:pid>/reject")
    def reject_deposit(pid):
        g = guard()
        if g:
            return g
        db.execute("UPDATE payments SET status = 'cancelled' WHERE id = ? AND status != 'paid'", (pid,))
        return jsonify({"ok": True})

    @app.get("/api/orders")
    def orders_list():
        g = guard()
        if g:
            return g
        rows = db.q(
            "SELECT o.id, o.phone, o.service_name, o.country_name, o.cost_usd, o.price_paise, o.status, o.codes, o.error, "
            "o.created_at, u.telegram_id, u.username FROM orders o JOIN users u ON u.id = o.user_id "
            "WHERE o.status != 'buying' ORDER BY o.id DESC LIMIT 200"
        )
        return jsonify({"orders": [dict(r) for r in rows]})

    return app


def _start_of_day() -> int:
    import time

    lt = time.localtime()
    return int(time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)) * 1000)


def start_admin_panel() -> None:
    app = create_app()

    def run():
        app.run(host="0.0.0.0", port=config.ADMIN_PANEL_PORT, threaded=True)

    threading.Thread(target=run, name="admin", daemon=True).start()
    print(f"[admin] panel on http://localhost:{config.ADMIN_PANEL_PORT}")
