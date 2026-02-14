from telebot import TeleBot
from telebot.types import CallbackQuery, Message

from ..callbacks import Cb
from ..storage import get_user
from ..keyboards import wallet_kb
from ..states import WalletStates

def register(bot: TeleBot):

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.NAV + ":wallet"))
    def open_wallet(c: CallbackQuery):
        u = get_user(c.from_user.id, c.from_user.username)
        text = (
            "💰 *Кошелёк*\n"
            f"Текущий баланс: *{u.balance}*\n\n"
            "Выбери действие:"
        )
        bot.edit_message_caption(
            caption=text,
            chat_id=c.message.chat.id,
            message_id=c.message.message_id,
            reply_markup=wallet_kb(),
            parse_mode="Markdown",
        )
        bot.answer_callback_query(c.id)

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.WAL + ":topup"))
    def wallet_topup(c: CallbackQuery):
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, "➕ Введи сумму пополнения (заглушка).")
        bot.set_state(c.from_user.id, WalletStates.topup_amount, c.message.chat.id)

    @bot.message_handler(state=WalletStates.topup_amount, content_types=["text"])
    def wallet_topup_amount(m: Message):
        bot.delete_state(m.from_user.id, m.chat.id)
        bot.send_message(m.chat.id, "✅ Принято. (Заглушка) Тут будет создание инвойса/платежа.")

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.WAL + ":withdraw"))
    def wallet_withdraw(c: CallbackQuery):
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, "➖ Введи сумму вывода (заглушка).")
        bot.set_state(c.from_user.id, WalletStates.withdraw_amount, c.message.chat.id)

    @bot.message_handler(state=WalletStates.withdraw_amount, content_types=["text"])
    def wallet_withdraw_amount(m: Message):
        bot.set_state(m.from_user.id, WalletStates.withdraw_details, m.chat.id)
        bot.send_message(m.chat.id, "✍️ Введи реквизиты/комментарий для вывода (заглушка).")

    @bot.message_handler(state=WalletStates.withdraw_details, content_types=["text"])
    def wallet_withdraw_details(m: Message):
        bot.delete_state(m.from_user.id, m.chat.id)
        bot.send_message(m.chat.id, "📨 Заявка на вывод создана. (Заглушка) Тут будет запись в БД и уведомление админам.")
