from telebot import TeleBot
from telebot.types import CallbackQuery, Message

from ..callbacks import Cb
from ..keyboards import support_kb
from ..states import SupportStates


def register(bot: TeleBot):
    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.SUP + ":open"))
    def support_open(c: CallbackQuery):
        bot.answer_callback_query(c.id)
        bot.send_message(
            c.message.chat.id,
            "🛟 Поддержка\nВыберите действие:",
            reply_markup=support_kb(),
        )

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.SUP + ":contact"))
    def support_contact(c: CallbackQuery):
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, "📝 Напиши сообщение в поддержку.")
        bot.set_state(c.from_user.id, SupportStates.waiting_message, c.message.chat.id)

    @bot.message_handler(state=SupportStates.waiting_message, content_types=["text"])
    def support_message(m: Message):
        bot.delete_state(m.from_user.id, m.chat.id)
        bot.send_message(m.chat.id, "✅ Сообщение принято. Оператор ответит позже.")
