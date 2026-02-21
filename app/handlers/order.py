from telebot import TeleBot
from telebot.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..callbacks import unpack, Cb, pack
from ..storage import (
    get_order,
    set_order_status,
    complete_order_and_release_escrow,
    cancel_paid_order_by_seller,
    has_review_for_order,
    create_review,
    list_orders_for_user,
)
from ..utils import edit_message_any
from .start import is_home_text, show_home

_REVIEW_CTX: dict[int, dict] = {}
ORDERS_PER_PAGE = 10


def _go_home(bot: TeleBot, m: Message) -> None:
    cfg = getattr(bot, "_cfg", None)
    if cfg is not None:
        show_home(bot, cfg, chat_id=m.chat.id, user_id=m.from_user.id, username=m.from_user.username)
    else:
        bot.send_message(m.chat.id, "Введите /start для перехода в главное меню.")


def _home_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🏠 Главное меню", callback_data=pack(Cb.NAV, "home")))
    return kb


def _status_ru(status: str) -> str:
    return {
        "paid": "Оплачен",
        "delivered": "Отправлен",
        "completed": "Завершен",
        "canceled_by_seller": "Отменен продавцом",
    }.get(status, status)



def _is_unfinished(status: str) -> bool:
    return status in ("created", "paid", "delivered")


def _unfinished_label(status: str) -> str:
    if _is_unfinished(status):
        return f"В процессе ({_status_ru(status)})"
    if status == "completed":
        return "Выполнен"
    return _status_ru(status)

def _buyer_after_paid_kb(seller_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("💬 Чат с продавцом", callback_data=pack(Cb.CAT, "chat", str(seller_id))))
    kb.add(InlineKeyboardButton("📦 Все заказы", callback_data=pack(Cb.NAV, "active")))
    kb.add(InlineKeyboardButton("🏠 Главное меню", callback_data=pack(Cb.NAV, "home")))
    return kb


def _buyer_confirm_kb(order_id: int, seller_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("✅ Подтвердить получение", callback_data=pack(Cb.ORD, "confirm", str(order_id))))
    kb.add(InlineKeyboardButton("💬 Чат с продавцом", callback_data=pack(Cb.CAT, "chat", str(seller_id))))
    kb.add(InlineKeyboardButton("📦 Все заказы", callback_data=pack(Cb.NAV, "active")))
    kb.add(InlineKeyboardButton("🏠 Главное меню", callback_data=pack(Cb.NAV, "home")))
    return kb


def _review_kb(order_id: int, target_id: int, target_role: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(
            "📝 Оставить отзыв",
            callback_data=pack(Cb.ORD, "review", str(order_id), str(target_id), target_role),
        )
    )
    kb.add(InlineKeyboardButton("📦 Все заказы", callback_data=pack(Cb.NAV, "active")))
    kb.add(InlineKeyboardButton("🏠 Главное меню", callback_data=pack(Cb.NAV, "home")))
    return kb


def _active_list_kb(user_id: int, orders: list[dict], *, page: int, pages: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    uid = int(user_id)
    for o in orders:
        order_id = int(o["order_id"])
        role = "Покупка" if int(o["buyer_id"]) == uid else "Продажа"
        status = _unfinished_label(str(o["status"]))
        kb.add(
            InlineKeyboardButton(
                f"↩ Заказ #{order_id} · {role} · {status}",
                callback_data=pack(Cb.ORD, "view", str(order_id)),
            )
        )
    if pages > 1:
        prev_page = max(1, page - 1)
        next_page = min(pages, page + 1)
        kb.row(
            InlineKeyboardButton("⬅️ Пред.", callback_data=pack(Cb.ORD, "list", str(prev_page))),
            InlineKeyboardButton("След. ➡️", callback_data=pack(Cb.ORD, "list", str(next_page))),
        )
    kb.add(InlineKeyboardButton("🏠 Главное меню", callback_data=pack(Cb.NAV, "home")))
    return kb


def _active_detail_kb(order: dict, viewer_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    viewer_id = int(viewer_id)
    buyer_id = int(order["buyer_id"])
    seller_id = int(order["seller_id"])
    status = str(order["status"])

    if viewer_id == seller_id and status == "paid":
        kb.add(InlineKeyboardButton("📦 Отправил товар", callback_data=pack(Cb.ORD, "delivered", str(order["order_id"]))))
        kb.add(InlineKeyboardButton("↩️ Отменить заказ (до 5 мин)", callback_data=pack(Cb.ORD, "cancel_seller", str(order["order_id"]))))
    if viewer_id == buyer_id and status == "delivered":
        kb.add(InlineKeyboardButton("✅ Подтвердить получение", callback_data=pack(Cb.ORD, "confirm", str(order["order_id"]))))

    peer_id = seller_id if viewer_id == buyer_id else buyer_id
    kb.add(InlineKeyboardButton("💬 Чат", callback_data=pack(Cb.CAT, "chat", str(peer_id))))
    kb.add(InlineKeyboardButton("📦 К заказам", callback_data=pack(Cb.NAV, "active")))
    kb.add(InlineKeyboardButton("🏠 Главное меню", callback_data=pack(Cb.NAV, "home")))
    return kb


def render_active_orders(bot: TeleBot, message: Message, user_id: int, page: int = 1) -> None:
    rows = list_orders_for_user(user_id)
    if not rows:
        text = "📦 Все заказы\n\nСейчас заказов нет."
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton("🏠 Главное меню", callback_data=pack(Cb.NAV, "home")))
        edit_message_any(bot, message, text, reply_markup=kb, parse_mode=None)
        return

    total = len(rows)
    pages = max(1, (total + ORDERS_PER_PAGE - 1) // ORDERS_PER_PAGE)
    page = max(1, min(int(page), pages))
    start = (page - 1) * ORDERS_PER_PAGE
    end = start + ORDERS_PER_PAGE
    page_rows = rows[start:end]

    lines = ["📦 Все заказы", f"Страница {page}/{pages}", ""]
    uid = int(user_id)
    in_progress: list[dict] = []
    history: list[dict] = []
    for o in page_rows:
        if _is_unfinished(str(o["status"])):
            in_progress.append(o)
        else:
            history.append(o)

    if in_progress:
        lines.append("В процессе:")
        for o in in_progress:
            role = "Покупка" if int(o["buyer_id"]) == uid else "Продажа"
            lines.append(
                f"• #{int(o['order_id'])} | {role} | {_unfinished_label(str(o['status']))} | {int(o['price'])}"
            )
    else:
        lines.append("В процессе: нет")

    lines.append("")
    lines.append("История заказов:")
    if history:
        for o in history:
            role = "Покупка" if int(o["buyer_id"]) == uid else "Продажа"
            lines.append(
                f"• #{int(o['order_id'])} | {role} | {_unfinished_label(str(o['status']))} | {int(o['price'])}"
            )
    else:
        lines.append("• пока пусто")

    edit_message_any(
        bot,
        message,
        "\n".join(lines),
        reply_markup=_active_list_kb(uid, page_rows, page=page, pages=pages),
        parse_mode=None,
    )


def _ask_review_rating(bot: TeleBot, *, user_id: int, chat_id: int, ctx: dict):
    msg = bot.send_message(
        chat_id,
        "Оцените пользователя по 5-балльной шкале (число от 1 до 5).",
        reply_markup=_home_kb(),
    )
    _REVIEW_CTX[int(user_id)] = ctx
    bot.register_next_step_handler(msg, _on_review_rating, bot)


def _on_review_rating(m: Message, bot: TeleBot):
    if is_home_text(m.text):
        bot.delete_state(m.from_user.id, m.chat.id)
        _REVIEW_CTX.pop(m.from_user.id, None)
        _go_home(bot, m)
        return

    ctx = _REVIEW_CTX.get(m.from_user.id)
    if not ctx:
        bot.send_message(m.chat.id, "Сессия отзыва потеряна. Нажмите «Оставить отзыв» снова.")
        _go_home(bot, m)
        return

    raw = (m.text or "").strip()
    if not raw.isdigit() or not (1 <= int(raw) <= 5):
        msg = bot.send_message(
            m.chat.id,
            "Нужно число от 1 до 5. Попробуйте еще раз:",
            reply_markup=_home_kb(),
        )
        bot.register_next_step_handler(msg, _on_review_rating, bot)
        return

    ctx["rating"] = int(raw)
    msg = bot.send_message(
        m.chat.id,
        "Напишите текст отзыва (по желанию). Можно отправить «-», если без текста.",
        reply_markup=_home_kb(),
    )
    bot.register_next_step_handler(msg, _on_review_text, bot)


def _on_review_text(m: Message, bot: TeleBot):
    if is_home_text(m.text):
        bot.delete_state(m.from_user.id, m.chat.id)
        _REVIEW_CTX.pop(m.from_user.id, None)
        _go_home(bot, m)
        return

    ctx = _REVIEW_CTX.pop(m.from_user.id, None)
    if not ctx:
        bot.send_message(m.chat.id, "Сессия отзыва потеряна. Нажмите «Оставить отзыв» снова.")
        _go_home(bot, m)
        return

    text = (m.text or "").strip()
    if text == "-":
        text = ""

    ok = create_review(
        order_id=int(ctx["order_id"]),
        author_id=int(ctx["author_id"]),
        target_id=int(ctx["target_id"]),
        target_role=str(ctx["target_role"]),
        rating=int(ctx["rating"]),
        review_text=text,
    )
    if not ok:
        bot.send_message(m.chat.id, "Отзыв по этой сделке уже оставлен.")
        return
    bot.send_message(m.chat.id, "✅ Спасибо! Отзыв сохранен.")

    target_id = int(ctx["target_id"])
    rating = int(ctx["rating"])
    target_role = str(ctx["target_role"])
    role_title = "продавцу" if target_role == "seller" else "покупателю"
    author_name = f"@{m.from_user.username}" if m.from_user.username else str(int(ctx["author_id"]))
    body = text if text else "без текста"
    stars = "★" * max(0, min(5, rating)) + "☆" * max(0, 5 - max(0, min(5, rating)))
    notify_text = (
        f"📝 Вам оставили отзыв ({role_title})\n"
        f"Заказ: #{int(ctx['order_id'])}\n"
        f"Оценка: {rating}/5 ({stars})\n"
        f"От: {author_name}\n\n"
        f"Текст: {body}"
    )
    try:
        bot.send_message(target_id, notify_text, reply_markup=_home_kb())
    except Exception:
        pass

    _go_home(bot, m)


def register(bot: TeleBot):
    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.ORD + ":"))
    def order_actions(c: CallbackQuery):
        parts = unpack(c.data)
        action = parts[1] if len(parts) > 1 else "unknown"

        bot.answer_callback_query(c.id)

        if action == "list":
            page_raw = parts[2] if len(parts) > 2 else "1"
            page = int(page_raw) if page_raw.isdigit() else 1
            render_active_orders(bot, c.message, c.from_user.id, page=page)
            return

        order_id_raw = parts[2] if len(parts) > 2 else "0"
        if not order_id_raw.isdigit():
            bot.send_message(c.message.chat.id, "Не смог прочитать ID заказа.")
            return

        order_id = int(order_id_raw)
        order = get_order(order_id)
        if not order:
            bot.send_message(c.message.chat.id, "Заказ не найден.")
            return

        viewer_id = int(c.from_user.id)
        buyer_id = int(order["buyer_id"])
        seller_id = int(order["seller_id"])
        price = int(order["price"])
        status = str(order["status"])

        if viewer_id not in (buyer_id, seller_id):
            bot.send_message(c.message.chat.id, "Нет доступа к этому заказу.")
            return

        if action == "view":
            role = "Покупка" if viewer_id == buyer_id else "Продажа"
            title = str(order.get("listing_title") or "")
            text = (
                f"📦 Заказ #{order_id}\n"
                f"Роль: {role}\n"
                f"Статус: {_status_ru(status)}\n"
                f"Сумма: {price}\n"
                f"Лот: #{int(order['listing_id'])}"
            )
            if title:
                text += f"\nНазвание: {title}"
            bot.send_message(c.message.chat.id, text, reply_markup=_active_detail_kb(order, viewer_id))
            return

        if action == "delivered":
            if viewer_id != seller_id:
                bot.send_message(c.message.chat.id, "Нет прав для этого действия.")
                return
            if status != "paid":
                bot.send_message(c.message.chat.id, f"Нельзя отметить отправку. Текущий статус: {status}")
                return

            set_order_status(order_id, "delivered")
            bot.send_message(c.message.chat.id, f"✅ Заказ #{order_id} отмечен как отправленный.")
            bot.send_message(
                buyer_id,
                f"📦 Продавец отметил отправку заказа #{order_id}. Подтвердите получение после проверки.",
                reply_markup=_buyer_confirm_kb(order_id, seller_id),
            )
            return

        if action == "cancel_seller":
            if viewer_id != seller_id:
                bot.send_message(c.message.chat.id, "Отменить заказ может только продавец.")
                return
            if status != "paid":
                bot.send_message(c.message.chat.id, f"Отмена невозможна. Текущий статус: {status}")
                return

            ok, reason = cancel_paid_order_by_seller(
                order_id=order_id,
                seller_id=viewer_id,
                max_seconds=300,
            )
            if not ok:
                if reason == "too_late":
                    bot.send_message(c.message.chat.id, "Отмена доступна только в течение 5 минут после оплаты.")
                elif reason.startswith("invalid_status:"):
                    current = reason.split(":", 1)[1]
                    bot.send_message(c.message.chat.id, f"Отмена невозможна. Текущий статус: {current}")
                elif reason == "not_seller":
                    bot.send_message(c.message.chat.id, "Отменить заказ может только продавец.")
                elif reason in ("already_changed",):
                    bot.send_message(c.message.chat.id, "Заказ уже изменен. Обновите список заказов.")
                else:
                    bot.send_message(c.message.chat.id, "Не удалось отменить заказ.")
                return

            bot.send_message(
                c.message.chat.id,
                f"↩️ Заказ #{order_id} отменен. Деньги возвращены покупателю.",
                reply_markup=_home_kb(),
            )
            try:
                bot.send_message(
                    buyer_id,
                    f"↩️ Заказ #{order_id} отменен продавцом. {price} возвращено на ваш баланс.",
                    reply_markup=_home_kb(),
                )
            except Exception:
                pass
            return

        if action == "confirm":
            if viewer_id != buyer_id:
                bot.send_message(c.message.chat.id, "Подтвердить получение может только покупатель.")
                return
            if status != "delivered":
                bot.send_message(c.message.chat.id, f"Нельзя подтвердить. Текущий статус: {status}")
                return

            ok, reason = complete_order_and_release_escrow(order_id)
            if not ok:
                if reason.startswith("invalid_status:"):
                    current = reason.split(":", 1)[1]
                    bot.send_message(c.message.chat.id, f"Нельзя подтвердить. Текущий статус: {current}")
                else:
                    bot.send_message(c.message.chat.id, "Не удалось завершить заказ. Попробуйте еще раз.")
                return
            bot.send_message(
                c.message.chat.id,
                f"✅ Получение заказа #{order_id} подтверждено.",
                reply_markup=_review_kb(order_id, seller_id, "seller"),
            )
            bot.send_message(
                seller_id,
                f"💸 Заказ #{order_id} завершен. На ваш баланс зачислено: {price}.",
                reply_markup=_review_kb(order_id, buyer_id, "buyer"),
            )
            return

        if action == "review":
            # format: ORD:review:<order_id>:<target_id>:<target_role>
            target_id_raw = parts[3] if len(parts) > 3 else "0"
            target_role = parts[4] if len(parts) > 4 else ""

            if not target_id_raw.isdigit() or target_role not in ("seller", "buyer"):
                bot.send_message(c.message.chat.id, "Некорректные данные для отзыва.")
                return

            author_id = viewer_id
            target_id = int(target_id_raw)
            if status != "completed":
                bot.send_message(c.message.chat.id, "Оставить отзыв можно только после завершения заказа.")
                return
            if author_id == target_id:
                bot.send_message(c.message.chat.id, "Нельзя оставить отзыв самому себе.")
                return
            if has_review_for_order(order_id, author_id, target_role):
                bot.send_message(c.message.chat.id, "Вы уже оставляли отзыв по этой сделке.")
                return

            _ask_review_rating(
                bot,
                user_id=viewer_id,
                chat_id=int(c.message.chat.id),
                ctx={
                    "order_id": order_id,
                    "author_id": author_id,
                    "target_id": target_id,
                    "target_role": target_role,
                },
            )
            return

        if action == "dispute":
            bot.send_message(c.message.chat.id, "Споры пока не реализованы.")
            return

        if action == "paid":
            bot.send_message(
                c.message.chat.id,
                f"💳 Заказ #{order_id} оплачен. Ожидайте отправку продавцом.",
                reply_markup=_buyer_after_paid_kb(seller_id),
            )
            return

        bot.send_message(c.message.chat.id, f"Неизвестное действие заказа: {action}")

