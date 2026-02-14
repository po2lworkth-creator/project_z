from telebot import TeleBot
from telebot.types import CallbackQuery
from ..callbacks import Cb
from ..storage import get_user
from ..keyboards import profile_kb

def register(bot: TeleBot):

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.NAV + ":profile"))
    def open_profile(c: CallbackQuery):
        u = get_user(c.from_user.id, c.from_user.username)
        text = (
            "👤 *Профиль*\n"
            f"ID: `{u.user_id}`\n"
            f"Username: @{u.username}\n"
            f"Баланс: *{u.balance}*\n"
            f"Продавец: *{'да' if u.is_seller else 'нет'}*\n"
            f"Верификация телефона: *{'да' if u.seller_verified_phone else 'нет'}*\n"
        )
        bot.edit_message_caption(
            caption=text,
            chat_id=c.message.chat.id,
            message_id=c.message.message_id,
            reply_markup=profile_kb(),
            parse_mode="Markdown",
        )
        bot.answer_callback_query(c.id)
