from __future__ import annotations

from telebot import TeleBot
from telebot.types import CallbackQuery, Message

from ..callbacks import Cb, unpack
from ..config import Config
from ..keyboards import (
    admin_panel_kb,
    superadmin_panel_kb,
    superadmin_admins_kb,
    ban_choice_kb,
    superadmin_ban_choice_kb,
)
from ..states import AdminStates, SuperAdminStates
from ..storage import find_user, get_user, set_balance, set_banned, set_admin
from ..utils import is_admin, is_super_admin, is_banned, format_user_profile


def _parse_tg_id(text: str | None) -> int | None:
    if not text:
        return None
    t = text.strip()
    if not t.isdigit():
        return None
    try:
        return int(t)
    except Exception:
        return None


def register(bot: TeleBot, cfg: Config):
    # ---------- открытие панелей ----------
    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.ADM + ":"))
    def admin_panel_router(c: CallbackQuery):
        parts = unpack(c.data)
        action = parts[1] if len(parts) > 1 else "open"

        if not is_admin(c.from_user.id, cfg):
            bot.answer_callback_query(c.id, "Нет доступа.")
            return
        if is_banned(c.from_user.id):
            bot.answer_callback_query(c.id, "Ты забанен.")
            return

        if action == "open":
            bot.edit_message_caption(
                chat_id=c.message.chat.id,
                message_id=c.message.message_id,
                caption="🛠 *Админ-панель*\n\nВыбери действие:",
                reply_markup=admin_panel_kb(),
                parse_mode="Markdown",
            )
            bot.answer_callback_query(c.id)
            return

        if action == "find_user":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "🔎 Введи Telegram ID пользователя (числом).")
            bot.set_state(c.from_user.id, AdminStates.waiting_find_user_id, c.message.chat.id)
            return

        if action == "set_balance":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "💰 Введи Telegram ID пользователя (числом).")
            bot.set_state(c.from_user.id, AdminStates.waiting_balance_user_id, c.message.chat.id)
            return

        if action == "ban":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "⛔️ Введи Telegram ID пользователя (числом).")
            bot.set_state(c.from_user.id, AdminStates.waiting_ban_user_id, c.message.chat.id)
            return

        if action in ("ban_do", "unban") and len(parts) >= 3 and parts[2].isdigit():
            target_id = int(parts[2])
            banned = (action == "ban_do")
            set_banned(target_id, banned)
            bot.answer_callback_query(c.id, "Готово.")
            bot.send_message(c.message.chat.id, f"✅ Статус бана обновлён для id: {target_id}")
            return

        bot.answer_callback_query(c.id)

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.SADM + ":"))
    def superadmin_panel_router(c: CallbackQuery):
        parts = unpack(c.data)
        action = parts[1] if len(parts) > 1 else "open"

        if not is_super_admin(c.from_user.id, cfg):
            bot.answer_callback_query(c.id, "Нет доступа.")
            return
        if is_banned(c.from_user.id):
            bot.answer_callback_query(c.id, "Ты забанен.")
            return

        if action == "open":
            bot.edit_message_caption(
                chat_id=c.message.chat.id,
                message_id=c.message.message_id,
                caption="👑 *Панель суперадмина*\n\nВыбери действие:",
                reply_markup=superadmin_panel_kb(),
                parse_mode="Markdown",
            )
            bot.answer_callback_query(c.id)
            return

        if action == "admins":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "👮 *Управление админами*\nВыбери действие:", reply_markup=superadmin_admins_kb(), parse_mode="Markdown")
            return

        if action == "find_user":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "🔎 Введи Telegram ID пользователя (числом).")
            bot.set_state(c.from_user.id, AdminStates.waiting_find_user_id, c.message.chat.id)
            return

        if action == "set_balance":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "💰 Введи Telegram ID пользователя (числом).")
            bot.set_state(c.from_user.id, AdminStates.waiting_balance_user_id, c.message.chat.id)
            return

        if action == "ban":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "⛔️ Введи Telegram ID пользователя (числом).")
            bot.set_state(c.from_user.id, AdminStates.waiting_ban_user_id, c.message.chat.id)
            return

        if action == "make_admin":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "✅ Введи Telegram ID пользователя - кому выдать админку.")
            bot.set_state(c.from_user.id, SuperAdminStates.waiting_make_admin_user_id, c.message.chat.id)
            return

        if action == "revoke_admin":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "🧹 Введи Telegram ID пользователя - у кого снять админку.")
            bot.set_state(c.from_user.id, SuperAdminStates.waiting_revoke_admin_user_id, c.message.chat.id)
            return

        if action in ("ban_do", "unban") and len(parts) >= 3 and parts[2].isdigit():
            target_id = int(parts[2])
            banned = (action == "ban_do")
            set_banned(target_id, banned)
            bot.answer_callback_query(c.id, "Готово.")
            bot.send_message(c.message.chat.id, f"✅ Статус бана обновлён для id: {target_id}")
            return

        bot.answer_callback_query(c.id)

    # ---------- обработчики состояний (общие) ----------
    @bot.message_handler(state=AdminStates.waiting_find_user_id, content_types=["text"])
    def admin_find_user_id(m: Message):
        bot.delete_state(m.from_user.id, m.chat.id)

        if not is_admin(m.from_user.id, cfg):
            return

        target_id = _parse_tg_id(m.text)
        if not target_id:
            bot.send_message(m.chat.id, "❌ Нужно отправить Telegram ID числом.")
            return

        # поиск без создания
        u = find_user(target_id)
        if not u:
            bot.send_message(m.chat.id, "Пользователь не найден в базе (скорее всего, он ещё не запускал бота).")
            return

        bot.send_message(m.chat.id, format_user_profile(target_id), parse_mode="Markdown")

    @bot.message_handler(state=AdminStates.waiting_balance_user_id, content_types=["text"])
    def admin_balance_user_id(m: Message):
        if not is_admin(m.from_user.id, cfg):
            bot.delete_state(m.from_user.id, m.chat.id)
            return

        target_id = _parse_tg_id(m.text)
        if not target_id:
            bot.send_message(m.chat.id, "❌ Нужно отправить Telegram ID числом. Попробуй ещё раз.")
            return

        # создаём если нет - чтобы можно было выставить баланс
        u = get_user(target_id)
        bot.set_state(m.from_user.id, AdminStates.waiting_balance_new_value, m.chat.id)
        with bot.retrieve_data(m.from_user.id, m.chat.id) as data:
            data["target_id"] = target_id

        bot.send_message(
            m.chat.id,
            f"Сейчас у пользователя id: *{target_id}* баланс: *{u.balance}*\n"
            "Введи значение, которым заменится его баланс (числом).",
            parse_mode="Markdown",
        )

    @bot.message_handler(state=AdminStates.waiting_balance_new_value, content_types=["text"])
    def admin_balance_new_value(m: Message):
        if not is_admin(m.from_user.id, cfg):
            bot.delete_state(m.from_user.id, m.chat.id)
            return

        new_val = _parse_tg_id(m.text)
        if new_val is None:
            bot.send_message(m.chat.id, "❌ Нужно отправить новое значение баланса числом. Попробуй ещё раз.")
            return

        with bot.retrieve_data(m.from_user.id, m.chat.id) as data:
            target_id = int(data.get("target_id") or 0)

        if not target_id:
            bot.delete_state(m.from_user.id, m.chat.id)
            bot.send_message(m.chat.id, "❌ Не удалось определить пользователя. Повтори через панель.")
            return

        set_balance(target_id, int(new_val))
        bot.delete_state(m.from_user.id, m.chat.id)
        bot.send_message(m.chat.id, f"✅ Баланс обновлён. Теперь у пользователя id: {target_id} баланс: {int(new_val)}")

    @bot.message_handler(state=AdminStates.waiting_ban_user_id, content_types=["text"])
    def admin_ban_user_id(m: Message):
        bot.delete_state(m.from_user.id, m.chat.id)

        # если суперадмин - тоже админ, пропускаем
        if not is_admin(m.from_user.id, cfg):
            return

        target_id = _parse_tg_id(m.text)
        if not target_id:
            bot.send_message(m.chat.id, "❌ Нужно отправить Telegram ID числом.")
            return

        u = get_user(target_id)  # создадим, чтобы был флаг бана
        currently_banned = bool(getattr(u, "is_banned", False))

        if is_super_admin(m.from_user.id, cfg):
            kb = superadmin_ban_choice_kb(target_id, currently_banned)
        else:
            kb = ban_choice_kb(target_id, currently_banned)

        status = "✅ забанен" if currently_banned else "❌ не в бане"
        bot.send_message(
            m.chat.id,
            f"Пользователь id: *{target_id}* сейчас: *{status}*\nВыбери действие:",
            reply_markup=kb,
            parse_mode="Markdown",
        )

    # ---------- суперадмин: выдача/снятие админки ----------
    @bot.message_handler(state=SuperAdminStates.waiting_make_admin_user_id, content_types=["text"])
    def superadmin_make_admin(m: Message):
        if not is_super_admin(m.from_user.id, cfg):
            bot.delete_state(m.from_user.id, m.chat.id)
            return

        target_id = _parse_tg_id(m.text)
        if not target_id:
            bot.send_message(m.chat.id, "❌ Нужно отправить Telegram ID числом.")
            return

        set_admin(target_id, True)
        bot.delete_state(m.from_user.id, m.chat.id)
        bot.send_message(m.chat.id, f"✅ Админка выдана пользователю id: {target_id}")
        try:
            bot.send_message(target_id, "✅ Тебе выдали доступ администратора.")
        except Exception:
            pass

    @bot.message_handler(state=SuperAdminStates.waiting_revoke_admin_user_id, content_types=["text"])
    def superadmin_revoke_admin(m: Message):
        if not is_super_admin(m.from_user.id, cfg):
            bot.delete_state(m.from_user.id, m.chat.id)
            return

        target_id = _parse_tg_id(m.text)
        if not target_id:
            bot.send_message(m.chat.id, "❌ Нужно отправить Telegram ID числом.")
            return

        set_admin(target_id, False)
        bot.delete_state(m.from_user.id, m.chat.id)
        bot.send_message(m.chat.id, f"🧹 Админка снята у пользователя id: {target_id}")
        try:
            bot.send_message(target_id, "ℹ️ Твой доступ администратора был отозван.")
        except Exception:
            pass
