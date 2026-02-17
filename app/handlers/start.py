from telebot import TeleBot
from telebot.types import Message

from ..config import Config
from ..keyboards import main_menu_kb
from ..storage import get_user, is_admin as storage_is_admin
from ..utils import is_super_admin, is_admin

WELCOME_TEXT = "РАБОТАЕМ НАХУЙ"


def register(bot: TeleBot, cfg: Config):
    @bot.message_handler(commands=["start", "home"])
    def cmd_start(m: Message):
        get_user(m.from_user.id, m.from_user.username)

        show_admin_panel = is_admin(m.from_user.id, cfg.super_admin_id, storage_is_admin)
        show_super_panel = is_super_admin(m.from_user.id, cfg.super_admin_id)

        try:
            with open(cfg.assets_main_image_path, "rb") as f:
                bot.send_photo(
                    m.chat.id,
                    photo=f,
                    caption=WELCOME_TEXT,
                    reply_markup=main_menu_kb(page=1, show_admin_panel=show_admin_panel, show_super_admin_panel=show_super_panel),
                )
        except FileNotFoundError:
            bot.send_message(
                m.chat.id,
                WELCOME_TEXT + "\n\n(assets/main.jpg не найден - добавь картинку)",
                reply_markup=main_menu_kb(page=1, show_admin_panel=show_admin_panel, show_super_admin_panel=show_super_panel),
            )
        except Exception:
            bot.send_message(
                m.chat.id,
                WELCOME_TEXT
                + "\n\n(Не удалось отправить изображение. Замени assets/main.jpg на валидный JPG.)",
                reply_markup=main_menu_kb(page=1, show_admin_panel=show_admin_panel, show_super_admin_panel=show_super_panel),
            )
