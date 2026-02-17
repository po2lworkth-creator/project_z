from telebot import TeleBot
from telebot.types import Message

from ..config import Config
from ..keyboards import main_menu_kb
from ..storage import get_user

WELCOME_TEXT = "РАБОТАЕМ НАХУЙ"


def register(bot: TeleBot, cfg: Config):
    @bot.message_handler(commands=["start", "home"])
    def cmd_start(m: Message):
        get_user(m.from_user.id, m.from_user.username)

        try:
            with open(cfg.assets_main_image_path, "rb") as f:
                bot.send_photo(
                    m.chat.id,
                    photo=f,
                    caption=WELCOME_TEXT,
                    reply_markup=main_menu_kb(page=1),
                )
        except FileNotFoundError:
            bot.send_message(
                m.chat.id,
                WELCOME_TEXT + "\n\n(assets/main.jpg не найден - добавь картинку)",
                reply_markup=main_menu_kb(page=1),
            )
        except Exception:
            bot.send_message(
                m.chat.id,
                WELCOME_TEXT
                + "\n\n(Не удалось отправить изображение. Замени assets/main.jpg на валидный JPG.)",
                reply_markup=main_menu_kb(page=1),
            )
