from __future__ import annotations

from telebot import TeleBot
from telebot.types import Message

from ..config import Config
from ..keyboards import main_menu_kb
from ..storage import get_user, is_banned, ensure_bootstrap_admins, is_admin as storage_is_admin
from ..utils import is_super_admin, is_admin

WELCOME_TEXT = "Добро пожаловать в каталог"
HOME_TEXTS = {"главное меню", "🏠 главное меню", "/menu", "menu", "home", "/home", "/start"}


def is_home_text(text: str | None) -> bool:
    return (text or "").strip().lower() in HOME_TEXTS


def show_home(bot: TeleBot, cfg: Config, *, chat_id: int, user_id: int, username: str | None) -> None:
    u = get_user(user_id, username)

    if is_banned(u.user_id):
        bot.send_message(chat_id, "Ваш аккаунт заблокирован.")
        return

    show_admin_panel = is_admin(u.user_id, cfg.super_admin_ids, storage_is_admin)
    show_super_panel = is_super_admin(u.user_id, cfg.super_admin_ids)

    try:
        with open(cfg.assets_main_image_path, "rb") as f:
            bot.send_photo(
                chat_id,
                photo=f,
                caption=WELCOME_TEXT,
                reply_markup=main_menu_kb(
                    page=1,
                    is_seller=bool(u.is_seller),
                    show_admin_panel=show_admin_panel,
                    show_super_admin_panel=show_super_panel,
                ),
            )
    except FileNotFoundError:
        bot.send_message(
            chat_id,
            WELCOME_TEXT + "\n\n(assets/main.jpg не найден - добавьте картинку)",
            reply_markup=main_menu_kb(
                page=1,
                is_seller=bool(u.is_seller),
                show_admin_panel=show_admin_panel,
                show_super_admin_panel=show_super_panel,
            ),
        )
    except Exception:
        bot.send_message(
            chat_id,
            WELCOME_TEXT + "\n\n(Не удалось отправить изображение. Замените assets/main.jpg на валидный JPG.)",
            reply_markup=main_menu_kb(
                page=1,
                is_seller=bool(u.is_seller),
                show_admin_panel=show_admin_panel,
                show_super_admin_panel=show_super_panel,
            ),
        )


def register(bot: TeleBot, cfg: Config):
    ensure_bootstrap_admins(cfg.super_admin_ids, cfg.admin_ids)
    setattr(bot, "_cfg", cfg)

    @bot.message_handler(commands=["start", "home", "menu"])
    def cmd_start(m: Message):
        try:
            bot.delete_state(m.from_user.id, m.chat.id)
        except Exception:
            pass
        show_home(bot, cfg, chat_id=m.chat.id, user_id=m.from_user.id, username=m.from_user.username)

    @bot.message_handler(state="*", content_types=["text"], func=lambda m: is_home_text(m.text))
    def text_home(m: Message):
        try:
            bot.delete_state(m.from_user.id, m.chat.id)
        except Exception:
            pass
        show_home(bot, cfg, chat_id=m.chat.id, user_id=m.from_user.id, username=m.from_user.username)
