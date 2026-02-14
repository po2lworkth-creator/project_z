from telebot import TeleBot
from telebot.types import CallbackQuery
from ..callbacks import unpack, Cb

def register(bot: TeleBot):

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.ORD + ":"))
    def order_actions(c: CallbackQuery):
        parts = unpack(c.data)
        action = parts[1] if len(parts) > 1 else "unknown"
        order_id = parts[2] if len(parts) > 2 else "?"
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, f"🧾 Заказ {order_id}, действие={action}. (Заглушка) Тут будет смена статуса/эскроу.")
