from telebot import TeleBot
from telebot.types import CallbackQuery, Message, KeyboardButton, ReplyKeyboardMarkup
from ..callbacks import Cb
from ..states import SellerStates
from ..storage import set_seller, set_seller_phone_verified

def register(bot: TeleBot):

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.SELL + ":verify_phone"))
    def verify_phone(c: CallbackQuery):
        bot.answer_callback_query(c.id)

        # Заглушка: включаем режим продавца. В реале это заявка/модерация.
        set_seller(c.from_user.id, True)

        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(KeyboardButton("📱 Отправить номер", request_contact=True))

        bot.send_message(
            c.message.chat.id,
            "✅ Для доступа к функциям продавца нужно подтвердить номер.\n"
            "Нажми кнопку ниже и отправь контакт (заглушка).",
            reply_markup=kb
        )
        bot.set_state(c.from_user.id, SellerStates.waiting_phone_contact, c.message.chat.id)

    @bot.message_handler(state=SellerStates.waiting_phone_contact, content_types=["contact"])
    def got_contact(m: Message):
        set_seller_phone_verified(m.from_user.id, True)
        bot.delete_state(m.from_user.id, m.chat.id)
        bot.send_message(m.chat.id, "✅ Номер подтверждён. (Заглушка) Теперь доступны функции продавца.", reply_markup=None)

    @bot.message_handler(state=SellerStates.waiting_phone_contact, content_types=["text"])
    def got_text_instead_contact(m: Message):
        bot.send_message(m.chat.id, "Нужно отправить контакт кнопкой «📱 Отправить номер».")
