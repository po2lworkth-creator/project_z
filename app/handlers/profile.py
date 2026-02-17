from datetime import datetime
from telebot import TeleBot
from telebot.types import CallbackQuery

from ..callbacks import Cb
from ..storage import get_user
from ..keyboards import profile_kb
from ..utils import edit_message_any
from ..models import SELLER_STATUS_SELLER


def _seller_yes_no(u) -> str:
    is_seller = bool(getattr(u, "is_seller", False)) or getattr(u, "seller_status", None) == SELLER_STATUS_SELLER
    return "да" if is_seller else "нет"


def _registration_bucket(created_at) -> str:
    if not created_at:
        return "нет данных"

    now = datetime.now()
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

    # в этом месяце
    if now.year == created_at.year and now.month == created_at.month:
        return "в этом месяце"

    # в этом полугодии
    def half_year(dt: datetime) -> int:
        return 1 if dt.month <= 6 else 2

    if now.year == created_at.year and half_year(now) == half_year(created_at):
        return "в этом полугодии"

    # в этом году
    if now.year == created_at.year:
        return "в этом году"

    # дальше - по дням
    if delta_days <= 548:  # ~1.5 года
        return "полтора года"
    if delta_days <= 730:  # ~2 года
        return "два года"
    return "больше двух лет"


def register(bot: TeleBot):

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.NAV + ":profile"))
    def open_profile(c: CallbackQuery):
        try:
            u = get_user(c.from_user.id, c.from_user.username)

            username = f"@{u.username}" if u.username else "нет"
            phone_linked = bool(getattr(u, "phone", None))
            phone_text = u.phone if u.phone else "не привязан"

            created_exact = u.created_at.strftime("%d.%m.%Y %H:%M") if u.created_at else "нет"
            created_bucket = _registration_bucket(u.created_at)
            seller_status = _seller_yes_no(u)

            text = (
                "👤 *Профиль*\n"
                f"ID: `{u.user_id}`\n"
                f"Username: {username}\n"
                f"Баланс: *{u.balance}*\n"
                f"Статус продавца: *{seller_status}*\n\n"
                f"Телефон: *{phone_text}*\n"
                f"Регистрация: *{created_bucket}*\n"
                f"Дата регистрации: *{created_exact}*\n"
            )

            edit_message_any(
                bot,
                c.message,
                text,
                reply_markup=profile_kb(phone_linked=phone_linked),
                parse_mode="Markdown",
            )
        finally:
            bot.answer_callback_query(c.id)
