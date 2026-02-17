from __future__ import annotations

from telebot import TeleBot
from telebot.types import Message

from .models import User


def edit_message_any(
    bot: TeleBot,
    message: Message,
    text: str,
    reply_markup=None,
    parse_mode: str | None = None,
):
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


def is_super_admin(user_id: int, super_admin_id: int) -> bool:
    return int(user_id) == int(super_admin_id)


def is_admin(user_id: int, super_admin_id: int, storage_is_admin_func) -> bool:
    if is_super_admin(user_id, super_admin_id):
        return True
    return bool(storage_is_admin_func(int(user_id)))


def format_user_profile(u: User) -> str:
    username_text = f"@{u.username}" if u.username else "нет"
    phone_text = u.phone if u.phone else "не привязан"
    admin_text = "да" if u.is_admin else "нет"
    banned_text = "да" if u.is_banned else "нет"

    return (
        "Профиль пользователя\n"
        f"ID: {u.user_id}\n"
        f"Username: {username_text}\n"
        f"Телефон: {phone_text}\n"
        f"Баланс: {u.balance}\n"
        f"Админ: {admin_text}\n"
        f"Бан: {banned_text}"
    )
