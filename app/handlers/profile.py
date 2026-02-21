from datetime import datetime
from html import escape

from telebot import TeleBot
from telebot.types import CallbackQuery

from ..callbacks import Cb, unpack
from ..keyboards import profile_kb
from ..models import SELLER_STATUS_SELLER
from ..storage import get_user, list_reviews_authored, list_reviews_received
from ..utils import edit_message_any, format_display_datetime, now_with_display_time_offset, with_display_time_offset


def _seller_yes_no(u) -> str:
    is_seller = bool(getattr(u, "is_seller", False)) or getattr(u, "seller_status", None) == SELLER_STATUS_SELLER
    return "да" if is_seller else "нет"


def _registration_bucket(created_at) -> str:
    if not created_at:
        return "нет данных"

    created_at = with_display_time_offset(created_at)
    now = now_with_display_time_offset()
    try:
        if getattr(created_at, "tzinfo", None) is not None and getattr(now, "tzinfo", None) is None:
            now = datetime.now(created_at.tzinfo)
    except Exception:
        pass

    delta_days = (now.date() - created_at.date()).days

    if delta_days <= 0:
        return "сегодня"
    if delta_days == 1:
        return "вчера"
    if delta_days == 2:
        return "позавчера"

    if now.year == created_at.year and now.month == created_at.month:
        return "в этом месяце"

    def half_year(dt: datetime) -> int:
        return 1 if dt.month <= 6 else 2

    if now.year == created_at.year and half_year(now) == half_year(created_at):
        return "в этом полугодии"

    if now.year == created_at.year:
        return "в этом году"

    if delta_days <= 548:
        return "полтора года"
    if delta_days <= 730:
        return "два года"
    return "больше двух лет"


def register(bot: TeleBot):
    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.NAV + ":profile"))
    def open_profile(c: CallbackQuery):
        parts = unpack(c.data or "")
        action = parts[1] if len(parts) > 1 else ""
        if action == "profile_reviews":
            try:
                authored = list_reviews_authored(c.from_user.id, limit=10)
                received = list_reviews_received(c.from_user.id, limit=10)

                lines: list[str] = ["📝 <b>Мои отзывы</b>", ""]
                lines.append("<b>Которые вы оставили:</b>")
                if authored:
                    for row in authored:
                        created = format_display_datetime(row.get("created_at"), fmt="%d.%m.%Y %H:%M", fallback="-")
                        target_id = int(row.get("target_id") or 0)
                        target_role = "продавцу" if str(row.get("target_role") or "") == "seller" else "покупателю"
                        rating = int(row.get("rating") or 0)
                        body = (row.get("review_text") or "").strip() or "без текста"
                        lines.append(
                            f"• Заказ #{int(row.get('order_id') or 0)} | {rating}/5 | {target_role} {target_id}\n"
                            f"{body}\n{created}"
                        )
                else:
                    lines.append("• Пока нет")

                lines.append("")
                lines.append("<b>Которые вы получили:</b>")
                if received:
                    for row in received:
                        created = format_display_datetime(row.get("created_at"), fmt="%d.%m.%Y %H:%M", fallback="-")
                        author_id = int(row.get("author_id") or 0)
                        target_role = "как продавец" if str(row.get("target_role") or "") == "seller" else "как покупатель"
                        rating = int(row.get("rating") or 0)
                        body = (row.get("review_text") or "").strip() or "без текста"
                        lines.append(
                            f"• Заказ #{int(row.get('order_id') or 0)} | {rating}/5 | от {author_id} ({target_role})\n"
                            f"{body}\n{created}"
                        )
                else:
                    lines.append("• Пока нет")

                kb = profile_kb(phone_linked=bool(getattr(get_user(c.from_user.id), "phone", None)))
                edit_message_any(
                    bot,
                    c.message,
                    "\n".join(lines),
                    reply_markup=kb,
                    parse_mode="HTML",
                )
            finally:
                bot.answer_callback_query(c.id)
            return

        try:
            u = get_user(c.from_user.id, c.from_user.username)

            username = f"@{u.username}" if u.username else "нет"
            phone_linked = bool(getattr(u, "phone", None))
            phone_text = u.phone if u.phone else "не привязан"

            created_exact = format_display_datetime(u.created_at)
            created_bucket = _registration_bucket(u.created_at)
            seller_status = _seller_yes_no(u)

            text = (
                "👤 <b>Профиль</b>\n"
                f"ID: <code>{u.user_id}</code>\n"
                f"Username: {escape(str(username))}\n"
                f"Баланс: <b>{escape(str(u.balance))}</b>\n"
                f"Статус продавца: <b>{escape(str(seller_status))}</b>\n\n"
                f"Телефон: <b>{escape(str(phone_text))}</b>\n"
                f"Регистрация: <b>{escape(str(created_bucket))}</b>\n"
                f"Дата регистрации: <b>{escape(str(created_exact))}</b>\n"
            )

            edit_message_any(
                bot,
                c.message,
                text,
                reply_markup=profile_kb(phone_linked=phone_linked),
                parse_mode="HTML",
            )
        finally:
            bot.answer_callback_query(c.id)
