from __future__ import annotations

from telebot import TeleBot
from telebot.apihelper import ApiTelegramException
from telebot.types import CallbackQuery, Message

from ..storage import is_banned


def register(bot: TeleBot):
    """Block any interaction for banned users."""

    @bot.callback_query_handler(func=lambda c: is_banned(c.from_user.id))
    def _blocked_callback(c: CallbackQuery):
        try:
            bot.delete_state(c.from_user.id, c.message.chat.id)
        except Exception:
            pass

        try:
            bot.edit_message_reply_markup(
                chat_id=c.message.chat.id,
                message_id=c.message.message_id,
                reply_markup=None,
            )
        except ApiTelegramException:
            pass
        except Exception:
            pass

        bot.answer_callback_query(c.id, "Ваш аккаунт заблокирован", show_alert=True)

    @bot.message_handler(
        func=lambda m: is_banned(m.from_user.id),
        content_types=[
            "text",
            "photo",
            "video",
            "document",
            "audio",
            "voice",
            "sticker",
            "contact",
            "location",
            "animation",
        ],
    )
    def _blocked_message(m: Message):
        try:
            bot.delete_state(m.from_user.id, m.chat.id)
        except Exception:
            pass
        bot.send_message(m.chat.id, "Ваш аккаунт заблокирован")
