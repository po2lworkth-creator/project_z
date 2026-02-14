from telebot import TeleBot
from telebot.types import CallbackQuery
from ..callbacks import unpack, Cb

def register(bot: TeleBot):

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.CAT + ":"))
    def open_category(c: CallbackQuery):
        parts = unpack(c.data)
        code = parts[1] if len(parts) > 1 else "??"
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, f"📦 Категория {code}. (Заглушка) Тут будет список товаров/фильтры.")
