from __future__ import annotations

import sqlite3
from datetime import datetime
from .models import (
    User,
    SELLER_STATUS_NONE,
    SELLER_STATUS_APPLIED,
    SELLER_STATUS_SELLER,
    SELLER_STATUS_REJECTED,
)

DB_PATH = "data.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _create_balance_event(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    delta: int,
    event_type: str,
    reason: str,
    actor_id: int | None = None,
    ref_type: str | None = None,
    ref_id: int | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO balance_events (user_id, delta, event_type, reason, actor_id, ref_type, ref_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(user_id),
            int(delta),
            str(event_type),
            (reason or "").strip() or "-",
            int(actor_id) if actor_id is not None else None,
            (ref_type or "").strip() or None,
            int(ref_id) if ref_id is not None else None,
        ),
    )


def init_storage() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance INTEGER NOT NULL DEFAULT 0,

                phone TEXT,
                seller_verified_phone INTEGER NOT NULL DEFAULT 0,

                seller_status TEXT NOT NULL DEFAULT 'none',
                seller_review_admin_id INTEGER,
                is_seller INTEGER NOT NULL DEFAULT 0,
                is_admin INTEGER NOT NULL DEFAULT 0,
                is_banned INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )

        # Ensure new moderation columns exist (for older DBs)
        with _connect() as conn2:
            cols = {row["name"] for row in conn2.execute("PRAGMA table_info(users)")}
            if "is_admin" not in cols:
                conn2.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
            if "is_banned" not in cols:
                conn2.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER NOT NULL DEFAULT 0")
            if "created_at" not in cols:
                conn2.execute("ALTER TABLE users ADD COLUMN created_at TEXT")
            if "seller_review_admin_id" not in cols:
                conn2.execute("ALTER TABLE users ADD COLUMN seller_review_admin_id INTEGER")
            conn2.execute("UPDATE users SET created_at = COALESCE(created_at, datetime('now'))")


        # Предложения продавцов
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS listings (
                listing_id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL,

                game TEXT NOT NULL,
                subcategory TEXT NOT NULL,
                amount INTEGER,

                title TEXT NOT NULL,
                short_desc TEXT NOT NULL,
                full_desc TEXT NOT NULL,
                price INTEGER NOT NULL,

                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),

                FOREIGN KEY (seller_id) REFERENCES users(user_id)
            )
            """
        )

        # Начальная модель заказа (покупка предложения)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                listing_id INTEGER NOT NULL,
                buyer_id INTEGER NOT NULL,
                seller_id INTEGER NOT NULL,
                price INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'created',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),

                FOREIGN KEY (listing_id) REFERENCES listings(listing_id),
                FOREIGN KEY (buyer_id) REFERENCES users(user_id),
                FOREIGN KEY (seller_id) REFERENCES users(user_id)
            )
            """
        )

        # Reviews for completed deals (seller/buyer feedback)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                review_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                target_role TEXT NOT NULL, -- 'seller' | 'buyer'
                rating INTEGER NOT NULL,
                review_text TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(order_id, author_id, target_role),
                FOREIGN KEY (order_id) REFERENCES orders(order_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS withdraw_requests (
                request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                reason TEXT NOT NULL,
                payout_tg TEXT NOT NULL,
                payout_phone TEXT,
                payout_bank TEXT,
                status TEXT NOT NULL DEFAULT 'pending', -- pending|approved|rejected
                admin_id INTEGER,
                admin_note TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                reviewed_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS topup_payments (
                payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                stars_amount INTEGER NOT NULL,
                payment_method TEXT NOT NULL DEFAULT 'stars', -- stars|cryptobot|yoomoney
                payload TEXT NOT NULL UNIQUE,
                external_payment_id TEXT,
                status TEXT NOT NULL DEFAULT 'pending', -- pending|paid|failed|canceled
                telegram_payment_charge_id TEXT,
                provider_payment_charge_id TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                paid_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS balance_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                delta INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                reason TEXT NOT NULL,
                actor_id INTEGER,
                ref_type TEXT,
                ref_id INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            """
        )
        cols_wr = {row["name"] for row in conn.execute("PRAGMA table_info(withdraw_requests)")}
        if "payout_phone" not in cols_wr:
            conn.execute("ALTER TABLE withdraw_requests ADD COLUMN payout_phone TEXT")
        if "payout_bank" not in cols_wr:
            conn.execute("ALTER TABLE withdraw_requests ADD COLUMN payout_bank TEXT")
        cols_tp = {row["name"] for row in conn.execute("PRAGMA table_info(topup_payments)")}
        if "telegram_payment_charge_id" not in cols_tp:
            conn.execute("ALTER TABLE topup_payments ADD COLUMN telegram_payment_charge_id TEXT")
        if "provider_payment_charge_id" not in cols_tp:
            conn.execute("ALTER TABLE topup_payments ADD COLUMN provider_payment_charge_id TEXT")
        if "paid_at" not in cols_tp:
            conn.execute("ALTER TABLE topup_payments ADD COLUMN paid_at TEXT")
        if "payment_method" not in cols_tp:
            conn.execute("ALTER TABLE topup_payments ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'stars'")
        if "external_payment_id" not in cols_tp:
            conn.execute("ALTER TABLE topup_payments ADD COLUMN external_payment_id TEXT")
        cols_be = {row["name"] for row in conn.execute("PRAGMA table_info(balance_events)")}
        if "reason" not in cols_be:
            conn.execute("ALTER TABLE balance_events ADD COLUMN reason TEXT NOT NULL DEFAULT '-'")
        if "actor_id" not in cols_be:
            conn.execute("ALTER TABLE balance_events ADD COLUMN actor_id INTEGER")
        if "ref_type" not in cols_be:
            conn.execute("ALTER TABLE balance_events ADD COLUMN ref_type TEXT")
        if "ref_id" not in cols_be:
            conn.execute("ALTER TABLE balance_events ADD COLUMN ref_id INTEGER")
        conn.commit()


def create_listing(
    *,
    seller_id: int,
    game: str,
    subcategory: str,
    title: str,
    short_desc: str,
    full_desc: str,
    price: int,
    amount: int | None = None,
) -> int:
    title = (title or "").strip()
    short_desc = (short_desc or "").strip()
    full_desc = (full_desc or "").strip()
    if not title:
        raise ValueError("title is empty")
    if not short_desc:
        raise ValueError("short_desc is empty")
    if not full_desc:
        raise ValueError("full_desc is empty")
    if int(price) <= 0:
        raise ValueError("price must be > 0")

    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO listings (seller_id, game, subcategory, amount, title, short_desc, full_desc, price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(seller_id),
                str(game),
                str(subcategory),
                int(amount) if amount is not None else None,
                title,
                short_desc,
                full_desc,
                int(price),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_listing(listing_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM listings WHERE listing_id = ?",
            (int(listing_id),),
        ).fetchone()
        return dict(row) if row else None


def list_listings(
    *,
    game: str,
    subcategory: str,
    amount: int | None = None,
    page: int = 1,
    per_page: int = 5,
) -> tuple[list[dict], int]:
    page = max(int(page), 1)
    per_page = max(int(per_page), 1)
    offset = (page - 1) * per_page

    where = "WHERE is_active = 1 AND game = ? AND subcategory = ?"
    params: list = [str(game), str(subcategory)]
    if amount is not None:
        where += " AND amount = ?"
        params.append(int(amount))

    with _connect() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) as c FROM listings {where}",
            tuple(params),
        ).fetchone()["c"]

        rows = conn.execute(
            f"SELECT * FROM listings {where} ORDER BY listing_id DESC LIMIT ? OFFSET ?",
            tuple(params + [per_page, offset]),
        ).fetchall()

    items = [dict(r) for r in rows]
    pages = max((int(total) + per_page - 1) // per_page, 1)
    return items, pages


def create_order(*, listing_id: int, buyer_id: int) -> int:
    listing = get_listing(int(listing_id))
    if not listing:
        raise ValueError("listing not found")
    if int(listing.get("is_active", 0)) != 1:
        raise ValueError("listing inactive")

    buyer = get_user(int(buyer_id))
    price = int(listing["price"])
    if buyer.balance < price:
        raise ValueError("not enough balance")

    # простая покупка, cписываем с покупателя и создаем заказ
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET balance = COALESCE(balance, 0) - ? WHERE user_id = ?",
            (price, int(buyer_id)),
        )
        cur = conn.execute(
            """
            INSERT INTO orders (listing_id, buyer_id, seller_id, price, status)
            VALUES (?, ?, ?, ?, 'created')
            """,
            (
                int(listing_id),
                int(buyer_id),
                int(listing["seller_id"]),
                price,
            ),
        )
        order_id = int(cur.lastrowid)
        _create_balance_event(
            conn,
            user_id=int(buyer_id),
            delta=-price,
            event_type="order_payment",
            reason=f"Оплата заказа #{order_id} (лот #{int(listing_id)})",
            ref_type="order",
            ref_id=order_id,
        )
        conn.commit()
        return order_id


def get_order(order_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM orders WHERE order_id = ?",
            (int(order_id),),
        ).fetchone()
        return dict(row) if row else None


def set_order_status(order_id: int, status: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE orders SET status = ? WHERE order_id = ?",
            (str(status), int(order_id)),
        )
        conn.commit()


def complete_order_and_release_escrow(order_id: int) -> tuple[bool, str]:
    """
    Mark order as completed and transfer escrow to seller atomically.

    Returns:
    - (True, "ok") on success
    - (False, reason) on business/state error
    """
    oid = int(order_id)
    with _connect() as conn:
        row = conn.execute(
            "SELECT seller_id, price, status FROM orders WHERE order_id = ?",
            (oid,),
        ).fetchone()
        if not row:
            return False, "order_not_found"

        status = str(row["status"])
        if status != "delivered":
            return False, f"invalid_status:{status}"

        seller_id = int(row["seller_id"])
        price = int(row["price"])

        conn.execute(
            "UPDATE users SET balance = COALESCE(balance, 0) + ? WHERE user_id = ?",
            (price, seller_id),
        )
        _create_balance_event(
            conn,
            user_id=seller_id,
            delta=price,
            event_type="order_income",
            reason=f"Выплата по заказу #{oid}",
            ref_type="order",
            ref_id=oid,
        )
        conn.execute(
            "UPDATE orders SET status = 'completed' WHERE order_id = ?",
            (oid,),
        )
        conn.commit()
        return True, "ok"


def cancel_paid_order_by_seller(*, order_id: int, seller_id: int, max_seconds: int = 300) -> tuple[bool, str]:
    """Cancel a paid order by seller within a short grace period.

    Business rules:
    - only seller can cancel
    - only when order status is 'paid'
    - only within `max_seconds` from order creation (payment moment)
    - buyer funds are refunded
    - listing is returned to 'approved' if it was marked 'sold'
    """
    oid = int(order_id)
    sid = int(seller_id)
    limit = max(1, int(max_seconds))

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT order_id, listing_id, buyer_id, seller_id, price, status, created_at
            FROM orders
            WHERE order_id = ?
            """,
            (oid,),
        ).fetchone()
        if not row:
            return False, "order_not_found"

        if int(row["seller_id"]) != sid:
            return False, "not_seller"

        status = str(row["status"] or "")
        if status != "paid":
            return False, f"invalid_status:{status}"

        created_at_raw = row["created_at"]
        try:
            created_at = datetime.fromisoformat(str(created_at_raw))
        except Exception:
            return False, "invalid_created_at"

        elapsed = (datetime.utcnow() - created_at).total_seconds()
        if elapsed > float(limit):
            return False, "too_late"

        buyer_id = int(row["buyer_id"])
        price = int(row["price"])
        listing_id = int(row["listing_id"])

        cur = conn.execute(
            """
            UPDATE orders
            SET status = 'canceled_by_seller'
            WHERE order_id = ?
              AND seller_id = ?
              AND status = 'paid'
            """,
            (oid, sid),
        )
        if int(cur.rowcount or 0) != 1:
            return False, "already_changed"

        conn.execute(
            "UPDATE users SET balance = COALESCE(balance, 0) + ? WHERE user_id = ?",
            (price, buyer_id),
        )
        _create_balance_event(
            conn,
            user_id=buyer_id,
            delta=price,
            event_type="order_refund",
            reason=f"Возврат за отмену заказа #{oid} продавцом",
            ref_type="order",
            ref_id=oid,
        )
        conn.execute(
            "UPDATE listings SET status = 'approved' WHERE listing_id = ? AND status = 'sold'",
            (listing_id,),
        )
        conn.commit()
        return True, "ok"


def get_open_order_by_listing(listing_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM orders
            WHERE listing_id = ?
              AND status IN ('paid', 'delivered')
            ORDER BY order_id DESC
            LIMIT 1
            """,
            (int(listing_id),),
        ).fetchone()
        return dict(row) if row else None


def create_order_with_escrow(
    *,
    listing_id: int,
    buyer_id: int,
    seller_id: int,
    price: int,
) -> int:
    """Create order and freeze buyer funds (escrow)."""
    buyer_id = int(buyer_id)
    seller_id = int(seller_id)
    listing_id = int(listing_id)
    price = int(price)
    if price <= 0:
        raise ValueError("price must be > 0")

    # Ensure users exist in DB.
    get_user(buyer_id)
    get_user(seller_id)

    with _connect() as conn:
        row = conn.execute("SELECT balance FROM users WHERE user_id = ?", (buyer_id,)).fetchone()
        bal = int(row["balance"]) if row else 0
        if bal < price:
            raise ValueError("not enough balance")

        conn.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id = ?",
            (price, buyer_id),
        )
        cur = conn.execute(
            """
            INSERT INTO orders (listing_id, buyer_id, seller_id, price, status)
            VALUES (?, ?, ?, ?, 'paid')
            """,
            (listing_id, buyer_id, seller_id, price),
        )
        order_id = int(cur.lastrowid)
        _create_balance_event(
            conn,
            user_id=buyer_id,
            delta=-price,
            event_type="order_payment",
            reason=f"Оплата заказа #{order_id} (лот #{listing_id})",
            ref_type="order",
            ref_id=order_id,
        )
        conn.commit()
        return order_id


def list_active_orders_for_user(user_id: int) -> list[dict]:
    """Active orders are paid/delivered (not fully closed)."""
    uid = int(user_id)
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                o.order_id,
                o.listing_id,
                o.buyer_id,
                o.seller_id,
                o.price,
                o.status,
                o.created_at,
                COALESCE(l.title, '(без названия)') AS listing_title
            FROM orders o
            LEFT JOIN listings l ON l.listing_id = o.listing_id
            WHERE (o.buyer_id = ? OR o.seller_id = ?)
              AND o.status IN ('paid', 'delivered')
            ORDER BY o.order_id DESC
            """,
            (uid, uid),
        ).fetchall()
        return [dict(r) for r in rows]


def list_orders_for_user(user_id: int) -> list[dict]:
    """All user orders (active + completed history)."""
    uid = int(user_id)
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                o.order_id,
                o.listing_id,
                o.buyer_id,
                o.seller_id,
                o.price,
                o.status,
                o.created_at,
                COALESCE(l.title, '(без названия)') AS listing_title
            FROM orders o
            LEFT JOIN listings l ON l.listing_id = o.listing_id
            WHERE (o.buyer_id = ? OR o.seller_id = ?)
            ORDER BY o.order_id DESC
            """,
            (uid, uid),
        ).fetchall()
        return [dict(r) for r in rows]


def create_withdraw_request(*, user_id: int, amount: int, reason: str, payout_phone: str, payout_bank: str) -> int:
    uid = int(user_id)
    amt = int(amount)
    if amt <= 0:
        raise ValueError("amount must be > 0")
    rsn = (reason or "").strip()
    phone = (payout_phone or "").strip()
    bank = (payout_bank or "").strip()
    if not rsn:
        raise ValueError("reason is empty")
    if not phone:
        raise ValueError("payout_phone is empty")
    if not bank:
        raise ValueError("payout_bank is empty")

    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO withdraw_requests (user_id, amount, reason, payout_tg, payout_phone, payout_bank, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
            """,
            (uid, amt, rsn, phone, phone, bank),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_withdraw_request(request_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM withdraw_requests WHERE request_id = ?",
            (int(request_id),),
        ).fetchone()
        return dict(row) if row else None


def review_withdraw_request(*, request_id: int, admin_id: int, approve: bool, admin_note: str | None = None) -> tuple[bool, str]:
    rid = int(request_id)
    aid = int(admin_id)
    note = (admin_note or "").strip() or None
    with _connect() as conn:
        req = conn.execute(
            "SELECT user_id, amount, status, admin_id FROM withdraw_requests WHERE request_id = ?",
            (rid,),
        ).fetchone()
        if not req:
            return False, "request_not_found"

        status = str(req["status"])
        if status != "pending":
            return False, f"already_processed:{status}"

        assigned_admin = req["admin_id"]
        if assigned_admin is None:
            return False, "not_taken"
        if int(assigned_admin) != aid:
            return False, f"taken_by_other:{int(assigned_admin)}"

        uid = int(req["user_id"])
        amt = int(req["amount"])

        if approve:
            bal_row = conn.execute("SELECT balance FROM users WHERE user_id = ?", (uid,)).fetchone()
            bal = int(bal_row["balance"]) if bal_row else 0
            if bal < amt:
                return False, "insufficient_balance"

            conn.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amt, uid))
            _create_balance_event(
                conn,
                user_id=uid,
                delta=-amt,
                event_type="withdraw_approved",
                reason=f"Вывод средств по заявке #{rid}",
                actor_id=aid,
                ref_type="withdraw_request",
                ref_id=rid,
            )
            conn.execute(
                """
                UPDATE withdraw_requests
                SET status = 'approved', admin_id = ?, admin_note = ?, reviewed_at = datetime('now')
                WHERE request_id = ?
                """,
                (aid, note, rid),
            )
        else:
            conn.execute(
                """
                UPDATE withdraw_requests
                SET status = 'rejected', admin_id = ?, admin_note = ?, reviewed_at = datetime('now')
                WHERE request_id = ?
                """,
                (aid, note, rid),
            )
        conn.commit()
        return True, "ok"


def take_withdraw_request(*, request_id: int, admin_id: int) -> tuple[bool, str]:
    rid = int(request_id)
    aid = int(admin_id)
    with _connect() as conn:
        req = conn.execute(
            "SELECT status, admin_id FROM withdraw_requests WHERE request_id = ?",
            (rid,),
        ).fetchone()
        if not req:
            return False, "request_not_found"

        status = str(req["status"] or "")
        if status != "pending":
            return False, f"already_processed:{status}"

        owner = req["admin_id"]
        if owner is None:
            cur = conn.execute(
                """
                UPDATE withdraw_requests
                SET admin_id = ?
                WHERE request_id = ?
                  AND status = 'pending'
                  AND admin_id IS NULL
                """,
                (aid, rid),
            )
            conn.commit()
            if int(cur.rowcount or 0) == 1:
                return True, "ok"
            return False, "race_conflict"

        owner_id = int(owner)
        if owner_id == aid:
            return False, "already_taken_by_you"
        return False, f"taken_by_other:{owner_id}"


def create_topup_payment(
    *,
    user_id: int,
    amount: int,
    stars_amount: int,
    payload: str,
    payment_method: str = "stars",
    external_payment_id: str | None = None,
) -> int:
    uid = int(user_id)
    amt = int(amount)
    stars = int(stars_amount)
    pay = (payload or "").strip()
    if amt <= 0:
        raise ValueError("amount must be > 0")
    if stars < 0:
        raise ValueError("stars_amount must be >= 0")
    if not pay:
        raise ValueError("payload is empty")
    method = (payment_method or "").strip().lower()
    if method not in ("stars", "cryptobot", "yoomoney"):
        raise ValueError("unsupported payment_method")
    ext = (external_payment_id or "").strip() or None

    # Ensure user exists.
    get_user(uid)

    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO topup_payments (user_id, amount, stars_amount, payment_method, payload, external_payment_id, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
            """,
            (uid, amt, stars, method, pay, ext),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_topup_payment_by_payload(payload: str) -> dict | None:
    pay = (payload or "").strip()
    if not pay:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM topup_payments WHERE payload = ?",
            (pay,),
        ).fetchone()
        return dict(row) if row else None


def get_topup_payment(payment_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM topup_payments WHERE payment_id = ?",
            (int(payment_id),),
        ).fetchone()
        return dict(row) if row else None


def complete_topup_payment(
    *,
    payload: str,
    telegram_payment_charge_id: str | None = None,
    provider_payment_charge_id: str | None = None,
) -> tuple[bool, str]:
    pay = (payload or "").strip()
    if not pay:
        return False, "payload_empty"

    with _connect() as conn:
        row = conn.execute(
            "SELECT payment_id, user_id, amount, status, payment_method FROM topup_payments WHERE payload = ?",
            (pay,),
        ).fetchone()
        if not row:
            return False, "payment_not_found"

        status = str(row["status"])
        if status == "paid":
            return False, "already_paid"
        if status != "pending":
            return False, f"invalid_status:{status}"

        payment_id = int(row["payment_id"])
        uid = int(row["user_id"])
        amount = int(row["amount"])
        method = str(row["payment_method"] or "").strip().lower() or "unknown"

        cur = conn.execute(
            """
            UPDATE topup_payments
            SET status = 'paid',
                telegram_payment_charge_id = ?,
                provider_payment_charge_id = ?,
                paid_at = datetime('now')
            WHERE payment_id = ?
              AND status = 'pending'
            """,
            (
                (telegram_payment_charge_id or "").strip() or None,
                (provider_payment_charge_id or "").strip() or None,
                payment_id,
            ),
        )
        if int(cur.rowcount or 0) != 1:
            return False, "already_paid"
        conn.execute(
            "UPDATE users SET balance = COALESCE(balance, 0) + ? WHERE user_id = ?",
            (amount, uid),
        )
        method_name_map = {
            "stars": "Stars",
            "cryptobot": "CryptoBot",
            "yoomoney": "YooMoney",
        }
        method_name = method_name_map.get(method, method)
        _create_balance_event(
            conn,
            user_id=uid,
            delta=amount,
            event_type="topup",
            reason=f"Пополнение через {method_name}, платеж #{payment_id}",
            ref_type="topup_payment",
            ref_id=payment_id,
        )
        conn.commit()
        return True, "ok"


def list_topup_payments(user_id: int, *, limit: int = 20) -> list[dict]:
    uid = int(user_id)
    lim = max(1, int(limit))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT payment_id, amount, stars_amount, payment_method, status, created_at, paid_at
            FROM topup_payments
            WHERE user_id = ?
            ORDER BY payment_id DESC
            LIMIT ?
            """,
            (uid, lim),
        ).fetchall()
        return [dict(r) for r in rows]


def list_balance_events(user_id: int, *, limit: int = 30) -> list[dict]:
    uid = int(user_id)
    lim = max(1, int(limit))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT event_id, delta, event_type, reason, actor_id, ref_type, ref_id, created_at
            FROM balance_events
            WHERE user_id = ?
            ORDER BY event_id DESC
            LIMIT ?
            """,
            (uid, lim),
        ).fetchall()
        return [dict(r) for r in rows]


def _row_to_user(row: sqlite3.Row) -> User:
    # sqlite3.Row behaves like a mapping, but doesn't always expose .get()
    keys = set(row.keys())
    created_at_raw = row["created_at"] if "created_at" in keys else None
    created_at = None
    if created_at_raw:
        try:
            created_at = datetime.fromisoformat(str(created_at_raw))
        except Exception:
            created_at = None
    return User(
        user_id=int(row["user_id"]),
        username=row["username"],
        balance=int(row["balance"]),
        phone=row["phone"],
        seller_verified_phone=bool(row["seller_verified_phone"]),
        seller_status=row["seller_status"],
        is_seller=bool(row["is_seller"]),
        is_admin=bool(row["is_admin"]) if "is_admin" in keys else False,
        is_banned=bool(row["is_banned"]) if "is_banned" in keys else False,
        created_at=created_at,
    )




def get_user(user_id: int, username: str | None = None) -> User:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

        if row is None:
            conn.execute(
                """
                INSERT INTO users (user_id, username, balance, phone, seller_verified_phone, seller_status, is_seller, created_at)
                VALUES (?, ?, 0, NULL, 0, ?, 0, datetime('now'))
                """,
                (user_id, username, SELLER_STATUS_NONE),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        else:
            if username and not row["username"]:
                conn.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
                conn.commit()
                row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

        return _row_to_user(row)


def set_balance(
    user_id: int,
    amount: int,
    *,
    actor_id: int | None = None,
    reason: str | None = None,
) -> None:
    uid = int(user_id)
    new_amount = int(amount)
    with _connect() as conn:
        row = conn.execute("SELECT balance FROM users WHERE user_id = ?", (uid,)).fetchone()
        if not row:
            return
        old_amount = int(row["balance"] or 0)
        conn.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_amount, uid))
        delta = new_amount - old_amount
        if delta != 0:
            _create_balance_event(
                conn,
                user_id=uid,
                delta=delta,
                event_type="admin_adjustment",
                reason=(reason or "").strip() or "Ручная корректировка баланса администратором",
                actor_id=int(actor_id) if actor_id is not None else None,
                ref_type="user",
                ref_id=uid,
            )
        conn.commit()


def add_balance(
    user_id: int,
    delta: int,
    *,
    actor_id: int | None = None,
    reason: str | None = None,
    event_type: str = "manual_adjustment",
) -> None:
    uid = int(user_id)
    delta_val = int(delta)
    if delta_val == 0:
        return
    with _connect() as conn:
        cur = conn.execute("UPDATE users SET balance = COALESCE(balance, 0) + ? WHERE user_id = ?", (delta_val, uid))
        if int(cur.rowcount or 0) != 1:
            return
        _create_balance_event(
            conn,
            user_id=uid,
            delta=delta_val,
            event_type=(event_type or "").strip() or "manual_adjustment",
            reason=(reason or "").strip() or "Ручное изменение баланса",
            actor_id=int(actor_id) if actor_id is not None else None,
            ref_type="user",
            ref_id=uid,
        )
        conn.commit()


def set_seller(user_id: int, is_seller: bool) -> None:
    status = SELLER_STATUS_SELLER if is_seller else SELLER_STATUS_NONE
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET is_seller = ?, seller_status = ? WHERE user_id = ?",
            (1 if is_seller else 0, status, user_id),
        )
        conn.commit()


def set_seller_phone_verified(user_id: int, verified: bool) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET seller_verified_phone = ? WHERE user_id = ?",
            (1 if verified else 0, user_id),
        )
        conn.commit()


def set_user_phone(user_id: int, phone: str | None) -> None:
    with _connect() as conn:
        conn.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, user_id))
        conn.commit()


def verify_user_phone(user_id: int, phone: str) -> None:
    phone = (phone or "").strip()
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET phone = ?, seller_verified_phone = 1 WHERE user_id = ?",
            (phone, user_id),
        )
        conn.commit()


def apply_seller(user_id: int) -> bool:
    u = get_user(user_id)

    # Запрещаем подачу заявки без подтвержденного телефона
    if u.seller_verified_phone is not True:
        return False
    if not u.phone or not str(u.phone).strip():
        return False

    # Нельзя повторно
    if u.seller_status in (SELLER_STATUS_APPLIED, SELLER_STATUS_SELLER):
        return False

    with _connect() as conn:
        conn.execute(
            "UPDATE users SET seller_status = ?, is_seller = 0, seller_review_admin_id = NULL WHERE user_id = ?",
            (SELLER_STATUS_APPLIED, user_id),
        )
        conn.commit()
    return True


def approve_seller(user_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET seller_status = ?, is_seller = 1, seller_review_admin_id = NULL WHERE user_id = ?",
            (SELLER_STATUS_SELLER, user_id),
        )
        conn.commit()


def reject_seller(user_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET seller_status = ?, is_seller = 0, seller_review_admin_id = NULL WHERE user_id = ?",
            (SELLER_STATUS_REJECTED, user_id),
        )
        conn.commit()


def take_seller_application_review(*, user_id: int, admin_id: int) -> tuple[bool, str]:
    uid = int(user_id)
    aid = int(admin_id)
    with _connect() as conn:
        row = conn.execute(
            "SELECT seller_status, seller_review_admin_id FROM users WHERE user_id = ?",
            (uid,),
        ).fetchone()
        if not row:
            return False, "user_not_found"

        status = str(row["seller_status"] or "")
        if status != SELLER_STATUS_APPLIED:
            return False, f"invalid_status:{status}"

        owner = row["seller_review_admin_id"]
        if owner is None:
            cur = conn.execute(
                """
                UPDATE users
                SET seller_review_admin_id = ?
                WHERE user_id = ?
                  AND seller_status = ?
                  AND seller_review_admin_id IS NULL
                """,
                (aid, uid, SELLER_STATUS_APPLIED),
            )
            conn.commit()
            if int(cur.rowcount or 0) == 1:
                return True, "ok"
            return False, "race_conflict"

        owner_id = int(owner)
        if owner_id == aid:
            return False, "already_taken_by_you"
        return False, f"taken_by_other:{owner_id}"


def can_review_seller_application(*, user_id: int, admin_id: int) -> tuple[bool, str]:
    uid = int(user_id)
    aid = int(admin_id)
    with _connect() as conn:
        row = conn.execute(
            "SELECT seller_status, seller_review_admin_id FROM users WHERE user_id = ?",
            (uid,),
        ).fetchone()
        if not row:
            return False, "user_not_found"

        status = str(row["seller_status"] or "")
        if status != SELLER_STATUS_APPLIED:
            return False, f"invalid_status:{status}"

        owner = row["seller_review_admin_id"]
        if owner is None:
            return False, "not_taken"
        owner_id = int(owner)
        if owner_id != aid:
            return False, f"taken_by_other:{owner_id}"
        return True, "ok"


# --- Admin / Ban helpers ---

def set_admin(user_id: int, is_admin: bool) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET is_admin = ? WHERE user_id = ?",
            (1 if is_admin else 0, user_id),
        )
        conn.commit()


def set_banned(user_id: int, is_banned: bool) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET is_banned = ? WHERE user_id = ?",
            (1 if is_banned else 0, user_id),
        )
        conn.commit()


def is_admin(user_id: int) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return bool(row["is_admin"]) if row else False


def is_banned(user_id: int) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return bool(row["is_banned"]) if row else False


def ensure_bootstrap_admins(super_admin_ids: list[int], admin_ids: list[int]) -> None:
    """Ensure super-admin/admin IDs exist in DB and have proper flags.

    - super-admin is always admin too
    - admins from ADMIN_IDS get admin flag
    """
    # create users if missing
    for sid in super_admin_ids:
        get_user(int(sid))
        set_admin(int(sid), True)

    for aid in admin_ids:
        get_user(int(aid))
        set_admin(int(aid), True)


def find_user(user_id: int) -> User | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return _row_to_user(row) if row else None


def list_user_ids(*, only_sellers: bool = False, only_admins: bool = False) -> list[int]:
    where_parts: list[str] = []
    params: list[int] = []
    if only_sellers:
        where_parts.append("is_seller = ?")
        params.append(1)
    if only_admins:
        where_parts.append("is_admin = ?")
        params.append(1)
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    with _connect() as conn:
        rows = conn.execute(
            f"SELECT user_id FROM users {where_sql} ORDER BY user_id ASC",
            tuple(params),
        ).fetchall()
        return [int(r["user_id"]) for r in rows]


def count_completed_orders_as_seller(seller_id: int) -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM orders WHERE seller_id = ? AND status = 'completed'",
            (int(seller_id),),
        ).fetchone()
        return int(row["cnt"]) if row else 0


def has_review_for_order(order_id: int, author_id: int, target_role: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM reviews
            WHERE order_id = ? AND author_id = ? AND target_role = ?
            LIMIT 1
            """,
            (int(order_id), int(author_id), str(target_role)),
        ).fetchone()
        return bool(row)


def create_review(
    *,
    order_id: int,
    author_id: int,
    target_id: int,
    target_role: str,
    rating: int,
    review_text: str | None,
) -> bool:
    rating = int(rating)
    if rating < 1 or rating > 5:
        raise ValueError("rating must be 1..5")

    if target_role not in ("seller", "buyer"):
        raise ValueError("target_role must be seller|buyer")

    with _connect() as conn:
        try:
            conn.execute(
                """
                INSERT INTO reviews (order_id, author_id, target_id, target_role, rating, review_text)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(order_id),
                    int(author_id),
                    int(target_id),
                    str(target_role),
                    rating,
                    (review_text or "").strip() or None,
                ),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def get_user_rating(target_id: int, target_role: str) -> tuple[float, int]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT AVG(rating) AS avg_rating, COUNT(*) AS cnt
            FROM reviews
            WHERE target_id = ? AND target_role = ?
            """,
            (int(target_id), str(target_role)),
        ).fetchone()
        if not row:
            return 0.0, 0
        avg_rating = float(row["avg_rating"]) if row["avg_rating"] is not None else 0.0
        return avg_rating, int(row["cnt"] or 0)


def list_user_reviews(target_id: int, target_role: str, page: int = 1, per_page: int = 5) -> tuple[list[dict], int]:
    page = max(1, int(page))
    per_page = max(1, int(per_page))
    offset = (page - 1) * per_page
    with _connect() as conn:
        total_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM reviews WHERE target_id = ? AND target_role = ?",
            (int(target_id), str(target_role)),
        ).fetchone()
        total = int(total_row["cnt"]) if total_row else 0
        pages = max((total + per_page - 1) // per_page, 1)
        page = min(page, pages)
        offset = (page - 1) * per_page

        rows = conn.execute(
            """
            SELECT review_id, order_id, author_id, rating, review_text, created_at
            FROM reviews
            WHERE target_id = ? AND target_role = ?
            ORDER BY review_id DESC
            LIMIT ? OFFSET ?
            """,
            (int(target_id), str(target_role), per_page, offset),
        ).fetchall()
        return [dict(r) for r in rows], pages


def list_reviews_received(user_id: int, *, limit: int = 20) -> list[dict]:
    uid = int(user_id)
    lim = max(1, int(limit))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT review_id, order_id, author_id, target_role, rating, review_text, created_at
            FROM reviews
            WHERE target_id = ?
            ORDER BY review_id DESC
            LIMIT ?
            """,
            (uid, lim),
        ).fetchall()
        return [dict(r) for r in rows]


def list_reviews_authored(user_id: int, *, limit: int = 20) -> list[dict]:
    uid = int(user_id)
    lim = max(1, int(limit))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT review_id, order_id, target_id, target_role, rating, review_text, created_at
            FROM reviews
            WHERE author_id = ?
            ORDER BY review_id DESC
            LIMIT ?
            """,
            (uid, lim),
        ).fetchall()
        return [dict(r) for r in rows]
