from __future__ import annotations

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

    # If message has a caption (photo/video/etc.) and is not a plain text message - edit caption.
    has_caption = getattr(message, "caption", None) is not None
    if has_caption and message.content_type != "text":
        return bot.edit_message_caption(
            chat_id=message.chat.id,
            message_id=message.message_id,
            caption=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )

    # Fallback - edit message text.
    return bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=message.message_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )
