from __future__ import annotations

from datetime import datetime, timedelta, timezone

from telebot import TeleBot
from telebot.types import Message


def edit_message_any(
    bot: TeleBot,
    message: Message,
    text: str,
    reply_markup=None,
    parse_mode: str | None = None,
):
    """Edit a message regardless of whether it's a media caption or a plain text message.

    In this project the start screen is usually a photo with a caption. If the asset
    is missing/broken, the bot sends a plain text message instead. Telegram uses
    different edit methods for these two cases.
    """

    has_caption = getattr(message, "caption", None) is not None
    if has_caption and message.content_type != "text":
        return bot.edit_message_caption(
            chat_id=message.chat.id,
            message_id=message.message_id,
            caption=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )

    return bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=message.message_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )


DISPLAY_TIME_OFFSET_HOURS = 3


def with_display_time_offset(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt + timedelta(hours=DISPLAY_TIME_OFFSET_HOURS)


def now_with_display_time_offset() -> datetime:
    # Use UTC as base so displayed time is stable regardless of host timezone.
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=DISPLAY_TIME_OFFSET_HOURS)


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def format_display_datetime(value, fmt: str = "%d.%m.%Y %H:%M", fallback: str = "нет") -> str:
    dt: datetime | None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = parse_iso_datetime(str(value) if value is not None else None)
    if dt is None:
        return fallback
    dt = with_display_time_offset(dt)
    if dt is None:
        return fallback
    return dt.strftime(fmt)


from .models import User


def is_super_admin(user_id: int, super_admin_ids: int | list[int]) -> bool:
    uid = int(user_id)
    if isinstance(super_admin_ids, int):
        return uid == int(super_admin_ids)
    return uid in {int(x) for x in super_admin_ids}


def is_admin(user_id: int, super_admin_ids: int | list[int], storage_is_admin) -> bool:
    # storage_is_admin - функция storage.is_admin
    if is_super_admin(user_id, super_admin_ids):
        return True
    return bool(storage_is_admin(user_id))


def format_user_profile(u: User) -> str:
    uname = f"@{u.username}" if u.username else "(без username)"
    admin_txt = "да" if u.is_admin else "нет"
    ban_txt = "да" if u.is_banned else "нет"
    seller_txt = "да" if u.is_seller else "нет"
    phone_txt = "да" if u.seller_verified_phone else "нет"

    return (
        "Профиль пользователя\n"
        f"TG ID: {u.user_id}\n"
        f"Username: {uname}\n"
        f"Баланс: {u.balance}\n"
        f"Админ: {admin_txt}\n"
        f"Бан: {ban_txt}\n"
        f"Продавец: {seller_txt}\n"
        f"Телефон подтвержден: {phone_txt}"
    )

