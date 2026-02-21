from telebot import TeleBot
from telebot.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup

from ..callbacks import Cb, pack
from ..states import ChatStates
from ..storage import find_user
from .start import is_home_text, show_home

# Active direct dialogs: user_id -> peer_user_id.
_DIALOGS: dict[int, int] = {}


def _go_home(bot: TeleBot, m: Message) -> None:
    cfg = getattr(bot, "_cfg", None)
    if cfg is not None:
        show_home(bot, cfg, chat_id=m.chat.id, user_id=m.from_user.id, username=m.from_user.username)
    else:
        bot.send_message(m.chat.id, "Введите /start для перехода в главное меню.")


def _home_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🏠 Главное меню", callback_data=pack(Cb.NAV, "home")))
    return kb


def open_chat(
    bot: TeleBot,
    *,
    from_user_id: int,
    from_username: str | None,
    peer_user_id: int,
    chat_id: int,
) -> tuple[bool, str]:
    from_user_id = int(from_user_id)
    peer_user_id = int(peer_user_id)

    if peer_user_id <= 0:
        return False, "Некорректный ID собеседника."
    if peer_user_id == from_user_id:
        return False, "Нельзя открыть чат с самим собой."

    peer = find_user(peer_user_id)
    if not peer:
        return False, "Пользователь не найден в базе (он еще не запускал бота)."

    # Open bidirectional dialog: both sides can write immediately.
    _DIALOGS[from_user_id] = peer_user_id
    _DIALOGS[peer_user_id] = from_user_id

    bot.set_state(from_user_id, ChatStates.chatting, chat_id)
    # In private chats chat_id usually equals user_id.
    bot.set_state(peer_user_id, ChatStates.chatting, peer_user_id)

    uname = f"@{from_username}" if from_username else "без username"
    try:
        bot.send_message(
            peer_user_id,
            f"💬 С вами открыт чат.\nСобеседник: {uname} (ID: {from_user_id})",
            reply_markup=_home_kb(),
        )
    except Exception:
        # If peer blocked bot / cannot receive messages, initiator still gets a clear status.
        return False, "Не удалось доставить сообщение собеседнику. Проверьте, что он запускал бота."

    return True, f"💬 Чат открыт с пользователем {peer_user_id}.\nНапишите сообщение."


def register(bot: TeleBot):
    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.CHAT + ":start"))
    def chat_start(c: CallbackQuery):
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, "💬 Введи TG ID пользователя:")
        bot.set_state(c.from_user.id, ChatStates.waiting_seller_id, c.message.chat.id)

    @bot.message_handler(state=ChatStates.waiting_seller_id, content_types=["text"])
    def chat_get_seller(m: Message):
        if is_home_text(m.text):
            bot.delete_state(m.from_user.id, m.chat.id)
            _go_home(bot, m)
            return

        raw = (m.text or "").strip()
        if not raw.isdigit():
            bot.send_message(m.chat.id, "Нужно отправить числовой TG ID.")
            return

        ok, text = open_chat(
            bot,
            from_user_id=m.from_user.id,
            from_username=m.from_user.username,
            peer_user_id=int(raw),
            chat_id=m.chat.id,
        )
        if ok:
            bot.send_message(m.chat.id, text, reply_markup=_home_kb())
        else:
            bot.send_message(m.chat.id, text)
        if not ok:
            bot.delete_state(m.from_user.id, m.chat.id)

    @bot.message_handler(state=ChatStates.chatting, content_types=["text"])
    def chat_forward(m: Message):
        if is_home_text(m.text):
            peer_id = _DIALOGS.pop(int(m.from_user.id), None)
            bot.delete_state(m.from_user.id, m.chat.id)
            _go_home(bot, m)
            if peer_id is not None and _DIALOGS.get(peer_id) == int(m.from_user.id):
                _DIALOGS.pop(peer_id, None)
                bot.delete_state(peer_id, peer_id)
                try:
                    bot.send_message(peer_id, "Собеседник завершил чат.")
                except Exception:
                    pass
            return

        text = (m.text or "").strip()
        if text.lower() in ("/chat_end", "/chat_stop", "/stopchat"):
            peer_id = _DIALOGS.pop(int(m.from_user.id), None)
            bot.delete_state(m.from_user.id, m.chat.id)
            bot.send_message(m.chat.id, "Чат завершен.")
            _go_home(bot, m)
            if peer_id is not None and _DIALOGS.get(peer_id) == int(m.from_user.id):
                _DIALOGS.pop(peer_id, None)
                bot.delete_state(peer_id, peer_id)
                try:
                    bot.send_message(peer_id, "Собеседник завершил чат.")
                except Exception:
                    pass
            return

        peer_id = _DIALOGS.get(int(m.from_user.id))
        if not peer_id:
            bot.send_message(m.chat.id, "Чат не активен. Откройте его снова через кнопку чата.")
            bot.delete_state(m.from_user.id, m.chat.id)
            _go_home(bot, m)
            return

        sender = f"@{m.from_user.username}" if m.from_user.username else str(m.from_user.id)
        try:
            bot.send_message(peer_id, f"💬 {sender}:\n{text}")
        except Exception:
            bot.send_message(m.chat.id, "Не удалось отправить сообщение собеседнику.")
