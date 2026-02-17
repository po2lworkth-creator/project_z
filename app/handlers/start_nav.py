from telebot import TeleBot
from telebot.types import CallbackQuery

from ..callbacks import Cb, unpack
from ..keyboards import main_menu_kb
from .start import WELCOME_TEXT
from ..utils import edit_message_any
from ..storage import is_admin as storage_is_admin
from ..utils import is_admin, is_super_admin
from ..config import Config


def register(bot: TeleBot, cfg: Config):
    @bot.callback_query_handler(
        func=lambda c: c.data in (f"{Cb.NAV}:home", f"{Cb.NAV}:catalog")
    )
    def nav_router(c: CallbackQuery):
        parts = unpack(c.data)
        action = parts[1] if len(parts) > 1 else "home"

        if action == "home":
            try:
                show_admin_panel = is_admin(c.from_user.id, cfg.super_admin_id, storage_is_admin)
                show_super_panel = is_super_admin(c.from_user.id, cfg.super_admin_id)
                edit_message_any(
                    bot,
                    c.message,
                    WELCOME_TEXT,
                    reply_markup=main_menu_kb(page=1, show_admin_panel=show_admin_panel, show_super_admin_panel=show_super_panel),
                )
            finally:
                bot.answer_callback_query(c.id)
            return

        if action == "catalog":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "📦 Каталог открыт. Выбери нужную категорию/товар.")
            return


        bot.answer_callback_query(c.id)
