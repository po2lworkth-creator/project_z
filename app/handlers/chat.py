from telebot import TeleBot
from telebot.types import CallbackQuery, Message
from ..callbacks import Cb
from ..states import ChatStates

# Каркас "прямого чата" внутри бота.
# Реальная логика: комнаты, маршрутизация buyer<->seller, хранение сообщений/контекстов, антиспам.

def register(bot: TeleBot):

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.CHAT + ":start"))
    def chat_start(c: CallbackQuery):
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, "💬 Введи ID продавца (заглушка).")
        bot.set_state(c.from_user.id, ChatStates.waiting_seller_id, c.message.chat.id)

    @bot.message_handler(state=ChatStates.waiting_seller_id, content_types=["text"])
    def chat_get_seller(m: Message):
        seller_id = m.text.strip()
        bot.set_state(m.from_user.id, ChatStates.chatting, m.chat.id)
        bot.send_message(m.chat.id, f"✅ Чат с продавцом {seller_id} открыт. (Заглушка) Пиши сообщение.")

    @bot.message_handler(state=ChatStates.chatting, content_types=["text"])
    def chat_forward(m: Message):
        bot.send_message(m.chat.id, "📨 (Заглушка) Сообщение было бы отправлено продавцу/в чат-комнату.")
