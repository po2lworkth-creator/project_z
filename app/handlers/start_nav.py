from __future__ import annotations

from telebot import TeleBot
from telebot.types import CallbackQuery

from ..callbacks import Cb, unpack
from ..keyboards import main_menu_kb
from ..storage import get_user, is_banned, is_admin as storage_is_admin
from ..utils import edit_message_any, is_super_admin, is_admin
from .start import WELCOME_TEXT
from . import catalog
from . import order


def register(bot: TeleBot, cfg):
    @bot.callback_query_handler(func=lambda c: c.data in (f"{Cb.NAV}:home", f"{Cb.NAV}:catalog", f"{Cb.NAV}:sell", f"{Cb.NAV}:active"))
    def nav_router(c: CallbackQuery):
        parts = unpack(c.data)
        action = parts[1] if len(parts) > 1 else "home"
        try:
            bot.delete_state(c.from_user.id, c.message.chat.id)
        except Exception:
            pass

        if action == "home":
            u = get_user(c.from_user.id, c.from_user.username)

            if is_banned(u.user_id):
                bot.answer_callback_query(c.id, "Вы заблокированы", show_alert=True)
                return

            show_admin_panel = is_admin(u.user_id, cfg.super_admin_ids, storage_is_admin)
            show_super_panel = is_super_admin(u.user_id, cfg.super_admin_ids)

            edit_message_any(
                bot,
                c.message,
                WELCOME_TEXT,
                reply_markup=main_menu_kb(
                    page=1,
                    is_seller=bool(u.is_seller),
                    show_admin_panel=show_admin_panel,
                    show_super_admin_panel=show_super_panel,
                ),
            )
            bot.answer_callback_query(c.id)
            return

        if action == "catalog":
            catalog.render_catalog_root(bot, c.message)
            bot.answer_callback_query(c.id)
            return

        if action == "sell":
            u = get_user(c.from_user.id, c.from_user.username)

            if not bool(u.is_seller):
                bot.answer_callback_query(c.id, "Доступно только подтвержденным продавцам", show_alert=True)
                return

            catalog.render_seller_lots(bot, c.message, seller_id=c.from_user.id, page=1)
            bot.answer_callback_query(c.id)
            return

        if action == "active":
            order.render_active_orders(bot, c.message, c.from_user.id)
            bot.answer_callback_query(c.id)
            return

        bot.answer_callback_query(c.id)

