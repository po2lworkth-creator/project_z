from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import (
    User,
    SELLER_STATUS_NONE,
    SELLER_STATUS_APPLIED,
    SELLER_STATUS_SELLER,
    SELLER_STATUS_REJECTED,
)

DB_PATH = Path(__file__).resolve().parent.parent / "data.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def init_storage() -> None:
    """Создает таблицы и выполняет простые миграции, если нужно."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance INTEGER NOT NULL DEFAULT 0,
                is_seller INTEGER NOT NULL DEFAULT 0,
                is_admin INTEGER NOT NULL DEFAULT 0,
                is_banned INTEGER NOT NULL DEFAULT 0,
                seller_status TEXT NOT NULL DEFAULT 'none',
                seller_verified_phone INTEGER NOT NULL DEFAULT 0,
                phone TEXT,
                created_at TEXT NOT NULL
            );
            """
        )

        cols = {r["name"] for r in conn.execute("PRAGMA table_info(users);").fetchall()}

        def add_col(name: str, ddl: str) -> None:
            if name not in cols:
                conn.execute(f"ALTER TABLE users ADD COLUMN {ddl};")

        add_col("username", "username TEXT")
        add_col("balance", "balance INTEGER NOT NULL DEFAULT 0")
        add_col("is_seller", "is_seller INTEGER NOT NULL DEFAULT 0")
        add_col("is_admin", "is_admin INTEGER NOT NULL DEFAULT 0")
        add_col("is_banned", "is_banned INTEGER NOT NULL DEFAULT 0")
        add_col("seller_status", "seller_status TEXT NOT NULL DEFAULT 'none'")
        add_col("seller_verified_phone", "seller_verified_phone INTEGER NOT NULL DEFAULT 0")
        add_col("phone", "phone TEXT")
        add_col("created_at", "created_at TEXT")

        conn.execute(
            "UPDATE users SET created_at = COALESCE(created_at, ?) WHERE created_at IS NULL",
            (_now_iso(),),
        )
        conn.commit()


def get_user(user_id: int, username: str | None = None) -> User:
    """Возвращает пользователя. Если его нет - создает."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            created_at = _now_iso()
            conn.execute(
                """
                INSERT INTO users(
                    user_id,
                    username,
                    balance,
                    is_seller,
                    is_admin,
                    is_banned,
                    seller_status,
                    seller_verified_phone,
                    phone,
                    created_at
                )
                VALUES(?, ?, 0, 0, 0, 0, ?, 0, NULL, ?)
                """,
                (user_id, username, SELLER_STATUS_NONE, created_at),
            )
            conn.commit()
            return User(
                user_id=user_id,
                username=username,
                balance=0,
                is_seller=False,
                is_admin=False,
                is_banned=False,
                seller_status=SELLER_STATUS_NONE,
                seller_verified_phone=False,
                phone=None,
                created_at=_parse_dt(created_at),
            )

        if username and not row["username"]:
            conn.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
            conn.commit()

        effective_username = username if (username and not row["username"]) else row["username"]

        return User(
            user_id=int(row["user_id"]),
            username=effective_username,
            balance=int(row["balance"]),
            is_seller=bool(row["is_seller"]),
            is_admin=bool(row["is_admin"]),
            is_banned=bool(row["is_banned"]),
            seller_status=(row["seller_status"] or SELLER_STATUS_NONE),
            seller_verified_phone=bool(row["seller_verified_phone"]),
            phone=row["phone"],
            created_at=_parse_dt(row["created_at"]),
        )


def find_user(user_id: int) -> Optional[User]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        return User(
            user_id=int(row["user_id"]),
            username=row["username"],
            balance=int(row["balance"]),
            is_seller=bool(row["is_seller"]),
            is_admin=bool(row["is_admin"]),
            is_banned=bool(row["is_banned"]),
            seller_status=(row["seller_status"] or SELLER_STATUS_NONE),
            seller_verified_phone=bool(row["seller_verified_phone"]),
            phone=row["phone"],
            created_at=_parse_dt(row["created_at"]),
        )


def set_admin(user_id: int, value: bool) -> None:
    get_user(int(user_id))
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET is_admin = ? WHERE user_id = ?",
            (1 if value else 0, user_id),
        )
        conn.commit()


def is_admin(user_id: int) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return bool(row and int(row[0]) == 1)


def set_banned(user_id: int, value: bool) -> None:
    get_user(int(user_id))
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET is_banned = ? WHERE user_id = ?",
            (1 if value else 0, user_id),
        )
        conn.commit()


def is_banned(user_id: int) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return bool(row and int(row[0]) == 1)


def ensure_bootstrap_admins(super_admin_id: int, admin_ids: list[int]) -> None:
    get_user(int(super_admin_id))
    set_admin(int(super_admin_id), True)
    set_banned(int(super_admin_id), False)

    for aid in admin_ids or []:
        get_user(int(aid))
        set_admin(int(aid), True)


def verify_user_phone(user_id: int, phone: str) -> None:
    """Сохраняет телефон и помечает его как подтвержденный для seller-flow."""
    phone = (phone or "").strip()
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET phone = ?, seller_verified_phone = 1 WHERE user_id = ?",
            (phone, user_id),
        )
        conn.commit()


def apply_seller(user_id: int) -> bool:
    """Подача заявки на продавца."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE users SET seller_status = ? WHERE user_id = ?",
            (SELLER_STATUS_APPLIED, user_id),
        )
        conn.commit()
        return cur.rowcount > 0


def approve_seller(user_id: int) -> None:
    """Подтверждение заявки - превращаем пользователя в продавца."""
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET seller_status = ?, is_seller = 1 WHERE user_id = ?",
            (SELLER_STATUS_SELLER, user_id),
        )
        conn.commit()


def reject_seller(user_id: int) -> None:
    """Отклонение заявки."""
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET seller_status = ?, is_seller = 0 WHERE user_id = ?",
            (SELLER_STATUS_REJECTED, user_id),
        )
        conn.commit()


def set_balance(user_id: int, amount: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE users SET balance = ? WHERE user_id = ?", (amount, user_id))
        conn.commit()


def add_balance(user_id: int, delta: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (delta, user_id))
        conn.commit()


def set_seller(user_id: int, is_seller: bool) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET is_seller = ? WHERE user_id = ?",
            (1 if is_seller else 0, user_id),
        )
        conn.commit()


def set_seller_phone_verified(user_id: int, verified: bool) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET seller_verified_phone = ? WHERE user_id = ?",
            (1 if verified else 0, user_id),
        )
        conn.commit()


def set_phone(user_id: int, phone: Optional[str]) -> None:
    """Доп функция - сохраняем телефон (нужна для профиля 'привязан телефон')."""
    with _connect() as conn:
        conn.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, user_id))
        conn.commit()
