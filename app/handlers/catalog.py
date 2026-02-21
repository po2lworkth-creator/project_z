from __future__ import annotations

import sqlite3
from datetime import datetime
from math import ceil
from typing import Optional

from telebot import TeleBot
from telebot.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..callbacks import Cb, pack, unpack
from ..config import Config
from ..storage import (
    DB_PATH,
    get_user,
    find_user,
    create_order_with_escrow,
    get_open_order_by_listing,
    count_completed_orders_as_seller,
    get_user_rating,
    list_user_reviews,
)
from .chat import open_chat
from ..utils import edit_message_any, format_display_datetime
from .start import is_home_text, show_home




SUBCATS = {
    # Brawl Stars
    "bs_gems": {"game": "brawlstars", "subcategory": "gems", "title": "Gems"},
    "bs_bpplus": {"game": "brawlstars", "subcategory": "brawlpass_plus", "title": "Brawl Pass Plus"},
    "bs_bp": {"game": "brawlstars", "subcategory": "brawlpass", "title": "Brawl Pass"},
    # Roblox
    "rb_robux": {"game": "roblox", "subcategory": "robux", "title": "Robux"},
    "rb_brainrots": {"game": "roblox", "subcategory": "brainrots", "title": "Steal a Brainrots"},
}

ALLOWED_GEM_AMOUNTS = [30, 80, 170, 360, 950, 2000]
PER_PAGE = 5

_NEW_OFFER: dict[int, dict] = {}


def _go_home(bot: TeleBot, m: Message) -> None:
    cfg = getattr(bot, "_cfg", None)
    if cfg is not None:
        show_home(bot, cfg, chat_id=m.chat.id, user_id=m.from_user.id, username=m.from_user.username)
    else:
        bot.send_message(m.chat.id, "Введите /start для перехода в главное меню.")


def _home_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🏠 Главное меню", callback_data=pack(Cb.NAV, "home")))
    return kb




def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _table_cols(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def init_catalog_storage() -> None:
    """
    Создает/мигрирует таблицу listings.
    Поддерживает старые схемы - добавляет недостающие колонки.
    """
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS listings (
                listing_id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL,
                game TEXT NOT NULL,
                subcategory TEXT NOT NULL,
                amount INTEGER NULL,

                title TEXT NOT NULL,
                full_desc TEXT NOT NULL,
                price INTEGER NOT NULL DEFAULT 0,

                status TEXT NOT NULL DEFAULT 'pending',
                review_admin_id INTEGER NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cols = _table_cols(conn, "listings")

        if "seller_id" not in cols:
            conn.execute("ALTER TABLE listings ADD COLUMN seller_id INTEGER")
        if "game" not in cols:
            conn.execute("ALTER TABLE listings ADD COLUMN game TEXT")
        if "subcategory" not in cols:
            conn.execute("ALTER TABLE listings ADD COLUMN subcategory TEXT")
        if "amount" not in cols:
            conn.execute("ALTER TABLE listings ADD COLUMN amount INTEGER")

        if "title" not in cols:
            conn.execute("ALTER TABLE listings ADD COLUMN title TEXT")
        if "full_desc" not in cols:
            conn.execute("ALTER TABLE listings ADD COLUMN full_desc TEXT")
        if "price" not in cols:
            conn.execute("ALTER TABLE listings ADD COLUMN price INTEGER NOT NULL DEFAULT 0")


        if "status" not in cols:
            conn.execute("ALTER TABLE listings ADD COLUMN status TEXT NOT NULL DEFAULT 'approved'")
        if "review_admin_id" not in cols:
            conn.execute("ALTER TABLE listings ADD COLUMN review_admin_id INTEGER NULL")
        if "created_at" not in cols:
            conn.execute("ALTER TABLE listings ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

        try:
            conn.execute("UPDATE listings SET status = COALESCE(status, 'approved')")
        except Exception:
            pass

        conn.commit()


def _get_listing(listing_id: int) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM listings WHERE listing_id = ?", (listing_id,)).fetchone()
        return dict(row) if row else None


def _set_status(listing_id: int, status: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE listings SET status = ?, review_admin_id = NULL WHERE listing_id = ?",
            (status, listing_id),
        )
        conn.commit()


def _take_listing_for_review(*, listing_id: int, admin_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE listings
            SET status = 'in_review', review_admin_id = ?
            WHERE listing_id = ?
              AND status = 'pending'
            """,
            (int(admin_id), int(listing_id)),
        )
        conn.commit()
        return int(cur.rowcount or 0) == 1


def _create_pending_listing(
    *,
    seller_id: int,
    game: str,
    subcategory: str,
    amount: Optional[int],
    title: str,
    full_desc: str,
    price: int,
) -> int:
    short_desc = (title or "").strip()
    if not short_desc:
        short_desc = (full_desc or "").strip()
    short_desc = short_desc.replace("\n", " ").strip()
    if len(short_desc) > 60:
        short_desc = short_desc[:57] + "..."

    with _connect() as conn:
        cols = _table_cols(conn, "listings")

        if "short_desc" in cols:
            cur = conn.execute(
                """
                INSERT INTO listings (seller_id, game, subcategory, amount, title, short_desc, full_desc, price, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (seller_id, game, subcategory, amount, title, short_desc, full_desc, price),
            )
        else:
            cur = conn.execute(
                """
                INSERT INTO listings (seller_id, game, subcategory, amount, title, full_desc, price, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (seller_id, game, subcategory, amount, title, full_desc, price),
            )

        conn.commit()
        return int(cur.lastrowid)


def _fetch_approved_listings(
    *,
    game: str,
    subcategory: str,
    amount: Optional[int],
    page: int,
) -> tuple[list[dict], int, int]:
    where = "WHERE status = 'approved' AND game = ? AND subcategory = ?"
    params: list = [game, subcategory]
    if amount is not None:
        where += " AND amount = ?"
        params.append(amount)

    with _connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS cnt FROM listings {where}", params).fetchone()["cnt"]
        pages = max(1, ceil(total / PER_PAGE))
        page = max(1, min(page, pages))
        offset = (page - 1) * PER_PAGE

        rows = conn.execute(
            f"""
            SELECT listing_id, title, price
            FROM listings
            {where}
            ORDER BY listing_id DESC
            LIMIT ? OFFSET ?
            """,
            params + [PER_PAGE, offset],
        ).fetchall()

    return [dict(r) for r in rows], pages, page


def _fetch_seller_listings(*, seller_id: int, page: int) -> tuple[list[dict], int, int]:
    with _connect() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS cnt FROM listings WHERE seller_id = ? AND status = 'approved'",
            (int(seller_id),),
        ).fetchone()["cnt"]
        pages = max(1, ceil(total / PER_PAGE))
        page = max(1, min(page, pages))
        offset = (page - 1) * PER_PAGE

        rows = conn.execute(
            """
            SELECT listing_id, title, price
            FROM listings
            WHERE seller_id = ? AND status = 'approved'
            ORDER BY listing_id DESC
            LIMIT ? OFFSET ?
            """,
            (int(seller_id), PER_PAGE, offset),
        ).fetchall()
    return [dict(r) for r in rows], pages, page



def _is_seller(user_id: int, username: Optional[str]) -> bool:
    u = get_user(user_id, username)
    return bool(getattr(u, "is_seller", False) is True)


def _edit(bot: TeleBot, c: CallbackQuery, text: str, kb: InlineKeyboardMarkup, parse_mode: str | None = "Markdown") -> None:
    try:
        edit_message_any(bot, c.message, text, reply_markup=kb, parse_mode=parse_mode)
    except Exception as e:
        if "message is not modified" in str(e).lower():
            return
        raise



def _root_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.row(
        InlineKeyboardButton("🎮 Brawl Stars", callback_data=pack(Cb.CAT, "game", "bs")),
        InlineKeyboardButton("🧩 Roblox", callback_data=pack(Cb.CAT, "game", "rb")),
    )
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data=pack(Cb.NAV, "home")))
    return kb


def _brawlstars_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("Gems", callback_data=pack(Cb.CAT, "sub", "bs_gems")))
    kb.add(InlineKeyboardButton("Brawl Pass Plus", callback_data=pack(Cb.CAT, "sub", "bs_bpplus")))
    kb.add(InlineKeyboardButton("Brawl Pass", callback_data=pack(Cb.CAT, "sub", "bs_bp")))
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data=pack(Cb.CAT, "root")))
    return kb


def _roblox_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("Robux", callback_data=pack(Cb.CAT, "sub", "rb_robux")))
    kb.add(InlineKeyboardButton("Steal a Brainrots", callback_data=pack(Cb.CAT, "sub", "rb_brainrots")))
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data=pack(Cb.CAT, "root")))
    return kb


def _gems_amount_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=3)
    for amt in ALLOWED_GEM_AMOUNTS:
        kb.add(InlineKeyboardButton(str(amt), callback_data=pack(Cb.CAT, "list", "bs_gems", str(amt), "1")))
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data=pack(Cb.CAT, "game", "bs")))
    return kb


def _admin_review_kb(listing_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("👀 Взять в рассмотрение", callback_data=pack(Cb.CAT, "adm_take", str(listing_id))))
    return kb


def _admin_decision_kb(listing_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.row(
        InlineKeyboardButton("✅ Одобрить", callback_data=pack(Cb.CAT, "adm_yes", str(listing_id))),
        InlineKeyboardButton("❌ Отклонить", callback_data=pack(Cb.CAT, "adm_no", str(listing_id))),
    )
    return kb


def _list_kb(
    *,
    subcode: str,
    amount: Optional[int],
    page: int,
    pages: int,
    items: list[dict],
    can_add: bool,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)

    for it in items:
        title = (it.get("title") or "(\u0431\u0435\u0437 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u044f)").strip()
        if len(title) > 28:
            title = title[:25] + "..."
        kb.add(
            InlineKeyboardButton(
                f"{title} #{it['listing_id']}",
                callback_data=pack(Cb.CAT, "view", str(it["listing_id"]), subcode, str(amount or 0), str(page)),
            )
        )

    if can_add:
        kb.add(InlineKeyboardButton("➕ Выставить", callback_data=pack(Cb.CAT, "add", subcode, str(amount or 0))))

    prev_page = max(1, page - 1)
    next_page = min(pages, page + 1)
    kb.row(
        InlineKeyboardButton("⬅️ Пред.", callback_data=pack(Cb.CAT, "list", subcode, str(amount or 0), str(prev_page))),
        InlineKeyboardButton("След. ➡️", callback_data=pack(Cb.CAT, "list", subcode, str(amount or 0), str(next_page))),
    )

    if subcode == "bs_gems":
        kb.add(InlineKeyboardButton("⬅️ Назад", callback_data=pack(Cb.CAT, "sub", "bs_gems")))
    else:
        kb.add(InlineKeyboardButton("⬅️ Назад", callback_data=pack(Cb.CAT, "game", "bs" if subcode.startswith("bs_") else "rb")))
    return kb


def _view_kb(
    *,
    seller_id: int,
    listing_id: int,
    back_cb: str,
    seller_cb: str | None = None,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.row(
        InlineKeyboardButton("💬 Чат с продавцом", callback_data=pack(Cb.CAT, "chat", str(seller_id))),
        InlineKeyboardButton("🛒 Купить", callback_data=pack(Cb.CAT, "buy", str(listing_id))),
    )
    kb.add(
        InlineKeyboardButton(
            "ℹ️ О продавце",
            callback_data=seller_cb or pack(Cb.CAT, "seller", str(seller_id)),
        )
    )
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data=back_cb))
    kb.add(InlineKeyboardButton("🏠 Главное меню", callback_data=pack(Cb.NAV, "home")))
    return kb


def _seller_lots_kb(*, page: int, pages: int, items: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    for it in items:
        title = (it.get("title") or "(без названия)").strip()
        if len(title) > 28:
            title = title[:25] + "..."
        kb.add(
            InlineKeyboardButton(
                f"{title} #{it['listing_id']}",
                callback_data=pack(Cb.CAT, "seller_lot", str(it["listing_id"]), str(page)),
            )
        )

    kb.add(InlineKeyboardButton("➕ Новый лот", callback_data=pack(Cb.NAV, "catalog")))
    prev_page = max(1, page - 1)
    next_page = min(pages, page + 1)
    kb.row(
        InlineKeyboardButton("⬅️ Пред.", callback_data=pack(Cb.CAT, "seller_my", str(prev_page))),
        InlineKeyboardButton("След. ➡️", callback_data=pack(Cb.CAT, "seller_my", str(next_page))),
    )
    kb.add(InlineKeyboardButton("🏠 Главное меню", callback_data=pack(Cb.NAV, "home")))
    return kb


def _seller_lot_view_kb(*, listing_id: int, page: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🧹 Снять с продажи", callback_data=pack(Cb.CAT, "seller_off", str(listing_id), str(page))))
    kb.add(InlineKeyboardButton("⬅️ К моим лотам", callback_data=pack(Cb.CAT, "seller_my", str(page))))
    kb.add(InlineKeyboardButton("🏠 Главное меню", callback_data=pack(Cb.NAV, "home")))
    return kb


def _seller_info_kb(*, seller_id: int, back_cb: str, reviews_cb: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(
            "📝 Отзывы о продавце",
            callback_data=reviews_cb,
        )
    )
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data=back_cb))
    kb.add(InlineKeyboardButton("🏠 Главное меню", callback_data=pack(Cb.NAV, "home")))
    return kb


def _seller_reviews_kb(*, seller_id: int, page: int, pages: int, ctx_tail: list[str] | None = None) -> InlineKeyboardMarkup:
    tail = list(ctx_tail or [])
    kb = InlineKeyboardMarkup(row_width=2)
    prev_page = max(1, page - 1)
    next_page = min(pages, page + 1)
    kb.row(
        InlineKeyboardButton(
            "⬅️ Пред.",
            callback_data=pack(Cb.CAT, "seller_reviews", str(seller_id), str(prev_page), *tail),
        ),
        InlineKeyboardButton(
            "След. ➡️",
            callback_data=pack(Cb.CAT, "seller_reviews", str(seller_id), str(next_page), *tail),
        ),
    )
    kb.add(
        InlineKeyboardButton(
            "⬅️ К продавцу",
            callback_data=pack(Cb.CAT, "seller", str(seller_id), *tail),
        )
    )
    kb.add(InlineKeyboardButton("🏠 Главное меню", callback_data=pack(Cb.NAV, "home")))
    return kb


def render_catalog_root(bot: TeleBot, message: Message) -> None:
    edit_message_any(
        bot,
        message,
        "📦 *Каталог*\nВыбери игру:",
        reply_markup=_root_kb(),
        parse_mode="Markdown",
    )


def _render_game(bot: TeleBot, c: CallbackQuery, game: str) -> None:
    if game == "bs":
        _edit(bot, c, "🎮 *Brawl Stars*\nВыбери раздел:", _brawlstars_kb())
        return
    if game == "rb":
        _edit(bot, c, "🧩 *Roblox*\nВыбери раздел:", _roblox_kb())
        return
    _edit(bot, c, "Игра не найдена.", _root_kb(), parse_mode=None)


def _render_sub(bot: TeleBot, c: CallbackQuery, subcode: str) -> None:
    if subcode == "bs_gems":
        _edit(bot, c, "💎 *Гемы*\nВыбери количество:", _gems_amount_kb())
        return
    if subcode not in SUBCATS:
        render_catalog_root(bot, c.message)
        return
    _render_list(bot, c, subcode=subcode, amount=None, page=1)


def _render_list(bot: TeleBot, c: CallbackQuery, *, subcode: str, amount: Optional[int], page: int) -> None:
    meta = SUBCATS.get(subcode)
    if not meta:
        render_catalog_root(bot, c.message)
        return

    items, pages, page = _fetch_approved_listings(
        game=meta["game"],
        subcategory=meta["subcategory"],
        amount=amount,
        page=page,
    )

    header = f"📦 *{meta['title']}*"
    if subcode == "bs_gems" and amount:
        header += f" - *{amount}*"

    can_add = _is_seller(c.from_user.id, c.from_user.username)

    if not items:
        text = header + "\n\nПока нет предложений."
        if can_add:
            text += "\n\nНажми «Выставить» - лот уйдет на модерацию."
        _edit(
            bot,
            c,
            text,
            _list_kb(subcode=subcode, amount=amount, page=page, pages=pages, items=[], can_add=can_add),
        )
        return
    text = "\n".join([header, "", f"\u0421\u0442\u0440\u0430\u043d\u0438\u0446\u0430 {page}/{pages}"])

    _edit(
        bot,
        c,
        text,
        _list_kb(subcode=subcode, amount=amount, page=page, pages=pages, items=items, can_add=can_add),
    )


def _render_view(bot: TeleBot, c: CallbackQuery, *, listing_id: int, subcode: str, amount_raw: str, page_raw: str) -> None:
    it = _get_listing(listing_id)
    if not it or it.get("status") != "approved":
        _edit(bot, c, "Лот не найден.", _root_kb(), parse_mode=None)
        return

    title = (it.get("title") or "(без названия)").strip()
    desc = (it.get("full_desc") or "").strip()
    price = int(it.get("price") or 0)

    text = f"📄 *{title}*\n\n{desc}\n\nЦена: *{price}*"

    back_cb = pack(Cb.CAT, "list", subcode, amount_raw, page_raw)
    seller_cb = pack(Cb.CAT, "seller", str(int(it["seller_id"])), "from_view", str(listing_id), subcode, amount_raw, page_raw)
    _edit(
        bot,
        c,
        text,
        _view_kb(
            seller_id=int(it["seller_id"]),
            listing_id=int(it["listing_id"]),
            back_cb=back_cb,
            seller_cb=seller_cb,
        ),
    )


def _format_registered_for_humans(created_at) -> str:
    if not created_at:
        return "нет данных"
    try:
        delta = datetime.now(created_at.tzinfo) - created_at if getattr(created_at, "tzinfo", None) else datetime.now() - created_at
        days = max(0, int(delta.days))
    except Exception:
        return "нет данных"
    if days < 1:
        return "меньше дня"
    if days < 30:
        return f"{days} дн."
    months = days // 30
    if months < 12:
        return f"{months} мес."
    years = months // 12
    rem_months = months % 12
    if rem_months:
        return f"{years} г. {rem_months} мес."
    return f"{years} г."


def _render_seller_info(
    bot: TeleBot,
    c: CallbackQuery,
    *,
    seller_id: int,
    back_cb: str | None = None,
    reviews_tail: list[str] | None = None,
) -> None:
    seller = find_user(seller_id)
    if not seller:
        _edit(bot, c, "Продавец не найден.", _root_kb(), parse_mode=None)
        return

    completed = count_completed_orders_as_seller(seller_id)
    avg, cnt = get_user_rating(seller_id, "seller")
    rating_text = f"{avg:.2f}/5 ({cnt})" if cnt > 0 else "нет оценок"
    username = f"@{seller.username}" if seller.username else "нет"
    reg_for = _format_registered_for_humans(seller.created_at)

    text = (
        "ℹ️ Информация о продавце\n"
        f"ID: {seller.user_id}\n"
        f"Username: {username}\n"
        f"На площадке: {reg_for}\n"
        f"Выполнено заказов: {completed}\n"
        f"Рейтинг: {rating_text}"
    )
    _edit(
        bot,
        c,
        text,
        _seller_info_kb(
            seller_id=seller_id,
            back_cb=back_cb or pack(Cb.CAT, "root"),
            reviews_cb=pack(Cb.CAT, "seller_reviews", str(seller_id), "1", *(reviews_tail or [])),
        ),
        parse_mode=None,
    )


def _render_seller_reviews(
    bot: TeleBot,
    c: CallbackQuery,
    *,
    seller_id: int,
    page: int,
    ctx_tail: list[str] | None = None,
) -> None:
    rows, pages = list_user_reviews(seller_id, "seller", page=page, per_page=5)
    page = max(1, min(page, pages))
    title = f"📝 Отзывы о продавце {seller_id}"

    if not rows:
        text = f"{title}\n\nОтзывов пока нет.\n\nСтраница {page}/{pages}"
    else:
        lines: list[str] = [title, "", f"Страница {page}/{pages}", ""]
        for r in rows:
            stars_count = int(r.get("rating") or 0)
            stars = "в…" * stars_count + "в†" * (5 - stars_count)
            author_id = int(r.get("author_id") or 0)
            body = (r.get("review_text") or "").strip()
            created = format_display_datetime(r.get("created_at"), fallback="")
            preview = body if body else "без текста"
            lines.append(f"• {stars} от {author_id}: {preview}")
            if created:
                lines.append(f"  {created}")
        text = "\n".join(lines)

    _edit(
        bot,
        c,
        text,
        _seller_reviews_kb(
            seller_id=seller_id,
            page=page,
            pages=pages,
            ctx_tail=ctx_tail,
        ),
        parse_mode=None,
    )


def render_seller_lots(bot: TeleBot, message: Message, *, seller_id: int, page: int = 1) -> None:
    items, pages, page = _fetch_seller_listings(seller_id=seller_id, page=page)
    header = f"💼 Мои лоты в продаже\n\nСтраница {page}/{pages}"
    if not items:
        text = header + "\n\nУ вас пока нет активных лотов."
    else:
        text = header + "\n\nВыберите лот из кнопок ниже:"
    edit_message_any(
        bot,
        message,
        text,
        reply_markup=_seller_lots_kb(page=page, pages=pages, items=items),
        parse_mode=None,
    )


def _render_seller_lot_view(bot: TeleBot, c: CallbackQuery, *, seller_id: int, listing_id: int, page: int) -> None:
    it = _get_listing(listing_id)
    if not it or int(it.get("seller_id") or 0) != int(seller_id):
        _edit(bot, c, "Лот не найден.", _seller_lots_kb(page=page, pages=1, items=[]), parse_mode=None)
        return

    title = (it.get("title") or "(без названия)").strip()
    desc = (it.get("full_desc") or "").strip()
    price = int(it.get("price") or 0)
    status = str(it.get("status") or "")
    text = (
        f"📄 {title}\n\n"
        f"{desc}\n\n"
        f"Цена: {price}\n"
        f"Статус: {status}\n"
        f"ID: #{listing_id}"
    )
    _edit(bot, c, text, _seller_lot_view_kb(listing_id=listing_id, page=page), parse_mode=None)



def _ask_title(bot: TeleBot, chat_id: int) -> None:
    msg = bot.send_message(chat_id, "📝 Напиши название лота:")
    bot.register_next_step_handler(msg, _on_title, bot)


def _on_title(m: Message, bot: TeleBot) -> None:
    if is_home_text(m.text):
        bot.delete_state(m.from_user.id, m.chat.id)
        _go_home(bot, m)
        return

    title = (m.text or "").strip()
    if len(title) < 2:
        msg = bot.send_message(m.chat.id, "Название слишком короткое. Напиши еще раз:")
        bot.register_next_step_handler(msg, _on_title, bot)
        return

    if m.from_user.id not in _NEW_OFFER:
        bot.send_message(m.chat.id, "Сессия создания лота потерялась. Нажми «Выставить» еще раз.")
        _go_home(bot, m)
        return

    _NEW_OFFER[m.from_user.id]["title"] = title
    msg = bot.send_message(m.chat.id, "📄 Теперь напиши подробное описание лота:")
    bot.register_next_step_handler(msg, _on_full_desc, bot)


def _on_full_desc(m: Message, bot: TeleBot) -> None:
    if is_home_text(m.text):
        bot.delete_state(m.from_user.id, m.chat.id)
        _go_home(bot, m)
        return

    full_desc = (m.text or "").strip()
    if len(full_desc) < 5:
        msg = bot.send_message(m.chat.id, "Описание слишком короткое. Напиши еще раз:")
        bot.register_next_step_handler(msg, _on_full_desc, bot)
        return

    info = _NEW_OFFER.get(m.from_user.id)
    if not info:
        bot.send_message(m.chat.id, "Сессия создания лота потерялась. Нажми «Выставить» еще раз.")
        _go_home(bot, m)
        return

    info["full_desc"] = full_desc
    msg = bot.send_message(m.chat.id, "💳 Теперь введи цену за шт. (только число):")
    bot.register_next_step_handler(msg, _on_price, bot)


def _on_price(m: Message, bot: TeleBot) -> None:
    if is_home_text(m.text):
        bot.delete_state(m.from_user.id, m.chat.id)
        _go_home(bot, m)
        return

    raw = (m.text or "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        msg = bot.send_message(m.chat.id, "Цена должна быть положительным числом. Введи цену еще раз:")
        bot.register_next_step_handler(msg, _on_price, bot)
        return

    price = int(raw)

    info = _NEW_OFFER.get(m.from_user.id)
    if not info:
        bot.send_message(m.chat.id, "Сессия создания лота потерялась. Нажми «Выставить» еще раз.")
        _go_home(bot, m)
        return

    meta = SUBCATS.get(info.get("subcode", ""))
    if not meta:
        _NEW_OFFER.pop(m.from_user.id, None)
        bot.send_message(m.chat.id, "Категория не найдена. Открой каталог заново.")
        _go_home(bot, m)
        return

    title = (str(info.get("title") or "") or "(без названия)").strip()
    full_desc = (str(info.get("full_desc") or "")).strip()
    amount = info.get("amount")

    try:
        listing_id = _create_pending_listing(
            seller_id=m.from_user.id,
            game=meta["game"],
            subcategory=meta["subcategory"],
            amount=amount,
            title=title,
            full_desc=full_desc,
            price=price,
        )
    except Exception as e:
        bot.send_message(m.chat.id, f"Не удалось отправить лот на модерацию. Ошибка: {e}")
        _go_home(bot, m)
        return
    finally:
        _NEW_OFFER.pop(m.from_user.id, None)

    # Работягам
    bot.send_message(
        m.chat.id,
        f"⏳ Твой лот на модерации. ID: #{listing_id}",
        reply_markup=_home_menu_kb(),
    )

    # Админам
    cfg: Optional[Config] = getattr(bot, "_cfg", None)
    if not cfg or not getattr(cfg, "admin_ids", None):
        bot.send_message(m.chat.id, "Админы не настроены (admin_ids пустой) - лот сохранен как pending, но не отправлен на проверку.")
        return

    seller = get_user(m.from_user.id, m.from_user.username)
    username = f"@{seller.username}" if seller.username else "нет"
    amt_line = f"\nКоличество: {amount}" if amount else ""

    admin_text = (
        "🆕 Новый лот на модерации\n"
        f"ID лота: {listing_id}\n"
        f"Продавец: {m.from_user.id} ({username})\n"
        f"Категория: {meta['game']} / {meta['subcategory']}{amt_line}\n"
        f"Цена: {price}\n\n"
        f"Название: {title}\n\n"
        f"Описание:\n{full_desc}"
    )

    delivered = 0
    for admin_id in cfg.admin_ids:
        try:
            bot.send_message(int(admin_id), admin_text, reply_markup=_admin_review_kb(listing_id))
            delivered += 1
        except Exception:
            # Admin may not have started the bot yet (e.g. chat not found).
            # Do not show technical API details to the seller.
            pass

    if delivered == 0:
        bot.send_message(
            m.chat.id,
            "Лот сохранен и ждет модерации, но уведомление администрации пока не доставлено.",
        )




def register(bot: TeleBot, cfg: Config):
    setattr(bot, "_cfg", cfg)

    init_catalog_storage()

    @bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith(Cb.CAT + ":"))
    def cat_router(c: CallbackQuery):
        bot.answer_callback_query(c.id)

        try:
            parts = unpack(c.data)
            action = parts[1] if len(parts) > 1 else "root"

            if action == "root":
                render_catalog_root(bot, c.message)
                return

            if action == "seller_my":
                page_raw = parts[2] if len(parts) > 2 else "1"
                page = int(page_raw) if page_raw.isdigit() else 1
                render_seller_lots(bot, c.message, seller_id=c.from_user.id, page=page)
                return

            if action == "seller_lot":
                listing_id_raw = parts[2] if len(parts) > 2 else "0"
                page_raw = parts[3] if len(parts) > 3 else "1"
                page = int(page_raw) if page_raw.isdigit() else 1
                if not listing_id_raw.isdigit():
                    bot.send_message(c.message.chat.id, "Не смог прочитать ID лота.")
                    return
                _render_seller_lot_view(
                    bot,
                    c,
                    seller_id=c.from_user.id,
                    listing_id=int(listing_id_raw),
                    page=page,
                )
                return

            if action == "seller_off":
                listing_id_raw = parts[2] if len(parts) > 2 else "0"
                page_raw = parts[3] if len(parts) > 3 else "1"
                page = int(page_raw) if page_raw.isdigit() else 1
                if not listing_id_raw.isdigit():
                    bot.send_message(c.message.chat.id, "Не смог прочитать ID лота.")
                    return
                listing_id = int(listing_id_raw)
                it = _get_listing(listing_id)
                if not it:
                    bot.send_message(c.message.chat.id, "Лот не найден.")
                    return
                if int(it.get("seller_id") or 0) != int(c.from_user.id):
                    bot.send_message(c.message.chat.id, "Нет прав для этого действия.")
                    return

                _set_status(listing_id, "rejected")
                bot.send_message(c.message.chat.id, f"✅ Лот #{listing_id} снят с продажи.")
                render_seller_lots(bot, c.message, seller_id=c.from_user.id, page=page)
                return

            if action == "game":
                game = parts[2] if len(parts) > 2 else "?"
                _render_game(bot, c, game)
                return

            if action == "sub":
                subcode = parts[2] if len(parts) > 2 else "?"
                _render_sub(bot, c, subcode)
                return

            if action == "list":
                subcode = parts[2] if len(parts) > 2 else "?"
                amount_raw = parts[3] if len(parts) > 3 else "0"
                page_raw = parts[4] if len(parts) > 4 else "1"

                amount = int(amount_raw) if amount_raw.isdigit() and int(amount_raw) > 0 else None
                page = int(page_raw) if page_raw.isdigit() else 1

                if subcode == "bs_gems":
                    if amount is None or amount not in ALLOWED_GEM_AMOUNTS:
                        _edit(bot, c, "💎 *Гемы*\nВыбери количество:", _gems_amount_kb())
                        return

                _render_list(bot, c, subcode=subcode, amount=amount, page=page)
                return

            if action == "view":
                listing_id_raw = parts[2] if len(parts) > 2 else "0"
                subcode = parts[3] if len(parts) > 3 else "bs_gems"
                amount_raw = parts[4] if len(parts) > 4 else "0"
                page_raw = parts[5] if len(parts) > 5 else "1"

                if not listing_id_raw.isdigit():
                    render_catalog_root(bot, c.message)
                    return

                _render_view(
                    bot,
                    c,
                    listing_id=int(listing_id_raw),
                    subcode=subcode,
                    amount_raw=amount_raw,
                    page_raw=page_raw,
                )
                return

            if action == "add":
                subcode = parts[2] if len(parts) > 2 else "?"
                amount_raw = parts[3] if len(parts) > 3 else "0"
                amount = int(amount_raw) if amount_raw.isdigit() and int(amount_raw) > 0 else None

                if not _is_seller(c.from_user.id, c.from_user.username):
                    bot.send_message(c.message.chat.id, "Эта функция доступна только подтвержденным продавцам.")
                    return

                if subcode == "bs_gems" and (amount is None or amount not in ALLOWED_GEM_AMOUNTS):
                    bot.send_message(c.message.chat.id, "Для гемов сначала выбери количество в каталоге.")
                    return

                if subcode not in SUBCATS:
                    bot.send_message(c.message.chat.id, "Категория не найдена.")
                    return

                _NEW_OFFER[c.from_user.id] = {"subcode": subcode, "amount": amount}
                _ask_title(bot, c.message.chat.id)
                return

            if action in ("adm_take", "adm_yes", "adm_no"):
                if c.from_user.id not in cfg.admin_ids:
                    bot.send_message(c.message.chat.id, "Нет прав.")
                    return

                listing_id_raw = parts[2] if len(parts) > 2 else "0"
                if not listing_id_raw.isdigit():
                    bot.send_message(c.message.chat.id, "Не смог прочитать ID лота.")
                    return

                listing_id = int(listing_id_raw)
                it = _get_listing(listing_id)
                if not it:
                    bot.send_message(c.message.chat.id, "Лот не найден.")
                    return

                status = str(it.get("status") or "")
                review_admin_id = int(it.get("review_admin_id") or 0)

                if action == "adm_take":
                    if status == "pending":
                        taken = _take_listing_for_review(listing_id=listing_id, admin_id=int(c.from_user.id))
                        if not taken:
                            bot.send_message(c.message.chat.id, "Не удалось взять лот в рассмотрение. Попробуйте еще раз.")
                            return
                        bot.send_message(c.message.chat.id, f"Лот #{listing_id} взят в рассмотрение.")
                        notice = f"👀 Лот #{listing_id} взят в рассмотрение админом {c.from_user.id}"
                        for admin_id in cfg.admin_ids:
                            try:
                                bot.send_message(int(admin_id), notice)
                            except Exception:
                                pass
                        try:
                            bot.edit_message_reply_markup(
                                c.message.chat.id,
                                c.message.message_id,
                                reply_markup=_admin_decision_kb(listing_id),
                            )
                        except Exception:
                            pass
                        return

                    if status == "in_review":
                        if review_admin_id == int(c.from_user.id):
                            bot.send_message(c.message.chat.id, f"Лот #{listing_id} уже у вас в рассмотрении.")
                        else:
                            bot.send_message(c.message.chat.id, f"Лот #{listing_id} уже взят другим администратором.")
                        return

                    bot.send_message(c.message.chat.id, "Этот лот уже обработан.")
                    try:
                        bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)
                    except Exception:
                        pass
                    return

                # Decision actions (approve/reject) require explicit "take" step first.
                if status != "in_review":
                    bot.send_message(c.message.chat.id, "Сначала возьмите лот в рассмотрение.")
                    return

                if review_admin_id != int(c.from_user.id):
                    bot.send_message(c.message.chat.id, "Этот лот рассматривает другой администратор.")
                    return

                if action == "adm_yes":
                    _set_status(listing_id, "approved")
                    bot.send_message(c.message.chat.id, f"✅ Лот принят и опубликован. ID: #{listing_id}")
                    bot.send_message(
                        int(it["seller_id"]),
                        f"✅ Ваш лот выставлен. ID: #{listing_id}",
                        reply_markup=_home_menu_kb(),
                    )
                else:
                    _set_status(listing_id, "rejected")
                    bot.send_message(c.message.chat.id, f"❌ Лот отклонен. ID: #{listing_id}")
                    bot.send_message(
                        int(it["seller_id"]),
                        f"❌ Ваш лот отклонен. ID: #{listing_id}",
                        reply_markup=_home_menu_kb(),
                    )

                try:
                    bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)
                except Exception:
                    pass
                return

            if action == "chat":
                seller_id_raw = parts[2] if len(parts) > 2 else "0"
                if not seller_id_raw.isdigit():
                    bot.send_message(c.message.chat.id, "Не смог прочитать ID продавца.")
                    return

                ok, text = open_chat(
                    bot,
                    from_user_id=c.from_user.id,
                    from_username=c.from_user.username,
                    peer_user_id=int(seller_id_raw),
                    chat_id=c.message.chat.id,
                )
                if ok:
                    kb = InlineKeyboardMarkup(row_width=1)
                    kb.add(InlineKeyboardButton("🏠 Главное меню", callback_data=pack(Cb.NAV, "home")))
                    bot.send_message(c.message.chat.id, text, reply_markup=kb)
                else:
                    bot.send_message(c.message.chat.id, text)
                return

            if action == "seller":
                seller_id_raw = parts[2] if len(parts) > 2 else "0"
                if not seller_id_raw.isdigit():
                    bot.send_message(c.message.chat.id, "Не смог прочитать продавца.")
                    return

                back_cb: str | None = None
                reviews_tail: list[str] | None = None
                if len(parts) > 7 and parts[3] == "from_view":
                    listing_id_raw = parts[4]
                    subcode = parts[5]
                    amount_raw = parts[6]
                    page_raw = parts[7]
                    if listing_id_raw.isdigit():
                        back_cb = pack(Cb.CAT, "view", listing_id_raw, subcode, amount_raw, page_raw)
                        reviews_tail = ["from_view", listing_id_raw, subcode, amount_raw, page_raw]

                _render_seller_info(
                    bot,
                    c,
                    seller_id=int(seller_id_raw),
                    back_cb=back_cb,
                    reviews_tail=reviews_tail,
                )
                return

            if action == "seller_reviews":
                seller_id_raw = parts[2] if len(parts) > 2 else "0"
                page_raw_reviews = parts[3] if len(parts) > 3 else "1"

                if not seller_id_raw.isdigit():
                    bot.send_message(c.message.chat.id, "Не смог прочитать продавца.")
                    return

                page_reviews = int(page_raw_reviews) if page_raw_reviews.isdigit() else 1
                ctx_tail = parts[4:] if len(parts) > 4 else None
                _render_seller_reviews(
                    bot,
                    c,
                    seller_id=int(seller_id_raw),
                    page=page_reviews,
                    ctx_tail=ctx_tail,
                )
                return

            if action == "buy":
                listing_id_raw = parts[2] if len(parts) > 2 else "0"
                if not listing_id_raw.isdigit():
                    bot.send_message(c.message.chat.id, "\u041d\u0435 \u0441\u043c\u043e\u0433 \u043f\u0440\u043e\u0447\u0438\u0442\u0430\u0442\u044c ID \u043b\u043e\u0442\u0430.")
                    return

                listing_id = int(listing_id_raw)
                it = _get_listing(listing_id)
                if not it or it.get("status") != "approved":
                    bot.send_message(c.message.chat.id, "\u041b\u043e\u0442 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d \u0434\u043b\u044f \u043f\u043e\u043a\u0443\u043f\u043a\u0438.")
                    return

                seller_id = int(it.get("seller_id") or 0)
                buyer_id = int(c.from_user.id)
                if seller_id <= 0:
                    bot.send_message(c.message.chat.id, "\u0423 \u043b\u043e\u0442\u0430 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u043f\u0440\u043e\u0434\u0430\u0432\u0435\u0446.")
                    return
                if seller_id == buyer_id:
                    bot.send_message(c.message.chat.id, "\u041d\u0435\u043b\u044c\u0437\u044f \u043a\u0443\u043f\u0438\u0442\u044c \u0441\u0432\u043e\u0439 \u0441\u043e\u0431\u0441\u0442\u0432\u0435\u043d\u043d\u044b\u0439 \u043b\u043e\u0442.")
                    return

                open_order = get_open_order_by_listing(listing_id)
                if open_order:
                    bot.send_message(c.message.chat.id, "\u041f\u043e \u044d\u0442\u043e\u043c\u0443 \u043b\u043e\u0442\u0443 \u0443\u0436\u0435 \u0435\u0441\u0442\u044c \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0439 \u0437\u0430\u043a\u0430\u0437.")
                    return

                price = int(it.get("price") or 0)
                buyer = get_user(buyer_id, c.from_user.username)
                if int(buyer.balance) < price:
                    bot.send_message(c.message.chat.id, f"\u041d\u0435\u0434\u043e\u0441\u0442\u0430\u0442\u043e\u0447\u043d\u043e \u0441\u0440\u0435\u0434\u0441\u0442\u0432. \u041d\u0443\u0436\u043d\u043e: {price}, \u0443 \u0432\u0430\u0441: {buyer.balance}.")
                    return

                try:
                    order_id = create_order_with_escrow(
                        listing_id=listing_id,
                        buyer_id=buyer_id,
                        seller_id=seller_id,
                        price=price,
                    )
                except ValueError:
                    bot.send_message(c.message.chat.id, "\u041d\u0435\u0434\u043e\u0441\u0442\u0430\u0442\u043e\u0447\u043d\u043e \u0441\u0440\u0435\u0434\u0441\u0442\u0432 \u0434\u043b\u044f \u043f\u043e\u043a\u0443\u043f\u043a\u0438.")
                    return
                except Exception as e:
                    bot.send_message(c.message.chat.id, f"\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0437\u0434\u0430\u0442\u044c \u0437\u0430\u043a\u0430\u0437: {e}")
                    return

                _set_status(listing_id, "sold")

                buyer_kb = InlineKeyboardMarkup(row_width=1)
                buyer_kb.add(InlineKeyboardButton("\U0001f4ac \u0427\u0430\u0442 \u0441 \u043f\u0440\u043e\u0434\u0430\u0432\u0446\u043e\u043c", callback_data=pack(Cb.CAT, "chat", str(seller_id))))
                buyer_kb.add(InlineKeyboardButton("🏠 Главное меню", callback_data=pack(Cb.NAV, "home")))
                bot.send_message(
                    c.message.chat.id,
                    (
                        f"\u2705 \u0417\u0430\u043a\u0430\u0437 #{order_id} \u0441\u043e\u0437\u0434\u0430\u043d.\n"
                        "\u0414\u0435\u043d\u044c\u0433\u0438 \u0441\u043f\u0438\u0441\u0430\u043d\u044b \u0438 \u0437\u0430\u043c\u043e\u0440\u043e\u0436\u0435\u043d\u044b \u0434\u043e \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0438\u044f \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u0438\u044f \u0442\u043e\u0432\u0430\u0440\u0430."
                    ),
                    reply_markup=buyer_kb,
                )

                seller_kb = InlineKeyboardMarkup(row_width=1)
                seller_kb.add(InlineKeyboardButton("\U0001f4e6 \u041e\u0442\u043f\u0440\u0430\u0432\u0438\u043b \u0442\u043e\u0432\u0430\u0440", callback_data=pack(Cb.ORD, "delivered", str(order_id))))
                seller_kb.add(InlineKeyboardButton("↩️ Отменить заказ (до 5 мин)", callback_data=pack(Cb.ORD, "cancel_seller", str(order_id))))
                seller_kb.add(InlineKeyboardButton("💬 Чат с покупателем", callback_data=pack(Cb.CAT, "chat", str(buyer_id))))
                seller_kb.add(InlineKeyboardButton("🏠 Главное меню", callback_data=pack(Cb.NAV, "home")))
                try:
                    bot.send_message(
                        seller_id,
                        (
                            f"\U0001f6d2 \u0423 \u0432\u0430\u0441 \u043d\u043e\u0432\u0430\u044f \u043f\u043e\u043a\u0443\u043f\u043a\u0430. \u0417\u0430\u043a\u0430\u0437 #{order_id}\n"
                            f"\u041b\u043e\u0442: #{listing_id}\n"
                            f"\u0421\u0443\u043c\u043c\u0430: {price}\n\n"
                            "\u041f\u043e\u0441\u043b\u0435 \u0444\u0430\u043a\u0442\u0438\u0447\u0435\u0441\u043a\u043e\u0439 \u043e\u0442\u043f\u0440\u0430\u0432\u043a\u0438 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 \u043a\u043d\u043e\u043f\u043a\u0443 \u00ab\u041e\u0442\u043f\u0440\u0430\u0432\u0438\u043b \u0442\u043e\u0432\u0430\u0440\u00bb."
                        ),
                        reply_markup=seller_kb,
                    )
                except Exception:
                    pass
                return

            render_catalog_root(bot, c.message)

        except Exception as e:
            if "message is not modified" in str(e).lower():
                return
            bot.send_message(c.message.chat.id, "Ошибка в каталоге. Попробуйте ещё раз.")
