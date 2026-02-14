from telebot import TeleBot
from telebot.types import CallbackQuery

from ..callbacks import Cb, unpack
from ..keyboards import main_menu_kb
from .start import WELCOME_TEXT


def register(bot: TeleBot):
    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.NAV + ":"))
    def nav_router(c: CallbackQuery):
        parts = unpack(c.data)
        action = parts[1] if len(parts) > 1 else "home"

        if action == "home":
            bot.edit_message_caption(
                chat_id=c.message.chat.id,
                message_id=c.message.message_id,
                caption=WELCOME_TEXT,
                reply_markup=main_menu_kb(page=1),
            )
            bot.answer_callback_query(c.id)
            return

        if action == "catalog":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "📦 Каталог открыт. Выбери нужную категорию/товар.")
            return

        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, f"🔘 Нажато: {action}. (Заглушка) Тут будет функционал.")
