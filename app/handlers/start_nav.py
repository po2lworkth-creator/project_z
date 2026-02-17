from telebot import TeleBot
from telebot.types import CallbackQuery

from ..callbacks import Cb, unpack
from ..keyboards import main_menu_kb
from .start import WELCOME_TEXT
from ..utils import edit_message_any


def register(bot: TeleBot):
    @bot.callback_query_handler(
        func=lambda c: c.data in (f"{Cb.NAV}:home", f"{Cb.NAV}:catalog")
    )
    def nav_router(c: CallbackQuery):
        parts = unpack(c.data)
        action = parts[1] if len(parts) > 1 else "home"

        if action == "home":
            try:
                edit_message_any(
                    bot,
                    c.message,
                    WELCOME_TEXT,
                    reply_markup=main_menu_kb(page=1),
                )
            finally:
                bot.answer_callback_query(c.id)
            return

        if action == "catalog":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "📦 Каталог открыт. Выбери нужную категорию/товар.")
            return

        # Should not reach here because of the handler filter above.
        bot.answer_callback_query(c.id)
