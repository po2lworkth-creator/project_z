from __future__ import annotations

import sqlite3
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
                is_seller INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.commit()


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        user_id=int(row["user_id"]),
        username=row["username"],
        balance=int(row["balance"]),
        phone=row["phone"],
        seller_verified_phone=bool(row["seller_verified_phone"]),
        seller_status=row["seller_status"],
        is_seller=bool(row["is_seller"]),
    )


def get_user(user_id: int, username: str | None = None) -> User:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

        if row is None:
            conn.execute(
                """
                INSERT INTO users (user_id, username, balance, phone, seller_verified_phone, seller_status, is_seller)
                VALUES (?, ?, 0, NULL, 0, ?, 0)
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


def set_balance(user_id: int, amount: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE users SET balance = ? WHERE user_id = ?", (amount, user_id))
        conn.commit()


def add_balance(user_id: int, delta: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE users SET balance = COALESCE(balance, 0) + ? WHERE user_id = ?", (delta, user_id))
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

    # Жестко запрещаем подачу заявки без подтвержденного телефона
    if u.seller_verified_phone is not True:
        return False
    if not u.phone or not str(u.phone).strip():
        return False

    # Нельзя повторно, если уже подано/одобрено
    if u.seller_status in (SELLER_STATUS_APPLIED, SELLER_STATUS_SELLER):
        return False

    with _connect() as conn:
        conn.execute(
            "UPDATE users SET seller_status = ?, is_seller = 0 WHERE user_id = ?",
            (SELLER_STATUS_APPLIED, user_id),
        )
        conn.commit()
    return True


def approve_seller(user_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET seller_status = ?, is_seller = 1 WHERE user_id = ?",
            (SELLER_STATUS_SELLER, user_id),
        )
        conn.commit()


def reject_seller(user_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET seller_status = ?, is_seller = 0 WHERE user_id = ?",
            (SELLER_STATUS_REJECTED, user_id),
        )
        conn.commit()
