from __future__ import annotations

from telebot import TeleBot
from telebot.apihelper import ApiTelegramException
from telebot.types import CallbackQuery, Message

from ..callbacks import Cb, unpack, pack
from ..config import Config
from ..keyboards import (
    admin_panel_kb,
    admin_ban_choice_kb,
    admin_broadcast_targets_kb,
    super_admin_panel_kb,
    super_admin_admins_kb,
    super_admin_ban_choice_kb,
    super_admin_broadcast_targets_kb,
)
from ..states import AdminPanelStates, SuperAdminPanelStates
from ..storage import (
    get_user,
    find_user,
    set_balance,
    set_banned,
    set_admin,
    set_seller,
    list_user_ids,
    is_admin as storage_is_admin,
    is_banned as storage_is_banned,
)
from ..utils import is_super_admin, is_admin, format_user_profile
from .start import show_home


def _parse_tg_id(text: str | None) -> int | None:
    t = (text or "").strip()
    return int(t) if t.isdigit() else None

_CTX: dict[tuple[int, int], dict] = {}


def _ck(user_id: int, chat_id: int) -> tuple[int, int]:
    return (int(user_id), int(chat_id))


def ctx_set(user_id: int, chat_id: int, **kwargs) -> None:
    k = _ck(user_id, chat_id)
    d = _CTX.get(k) or {}
    d.update(kwargs)
    _CTX[k] = d


def ctx_get(user_id: int, chat_id: int) -> dict:
    return _CTX.get(_ck(user_id, chat_id), {})


def ctx_clear(user_id: int, chat_id: int) -> None:
    _CTX.pop(_ck(user_id, chat_id), None)


def _go_home(bot: TeleBot, m: Message) -> None:
    cfg = getattr(bot, "_cfg", None)
    if cfg is not None:
        show_home(bot, cfg, chat_id=m.chat.id, user_id=m.from_user.id, username=m.from_user.username)
    else:
        bot.send_message(m.chat.id, "Введите /start для перехода в главное меню.")


def register(bot: TeleBot, cfg: Config):

    def _safe_notify(user_id: int, text: str) -> None:
        """Try to notify a user. Ignore errors (user may block bot / never started)."""
        try:
            bot.send_message(int(user_id), text)
        except ApiTelegramException:
            pass
        except Exception:
            pass

    def _broadcast_target_ids(scope: str, *, super_mode: bool) -> list[int]:
        if scope == "all":
            return list_user_ids()
        if scope == "sellers":
            return list_user_ids(only_sellers=True)
        if scope == "admins" and super_mode:
            return list_user_ids(only_admins=True)
        if scope == "support":
            return sorted({int(x) for x in cfg.support_ids})
        return []

    def _broadcast_scope_title(scope: str) -> str:
        titles = {
            "all": "всем пользователям",
            "sellers": "продавцам",
            "admins": "администраторам",
            "support": "поддержке",
        }
        return titles.get(scope, "получателям")

    def _send_broadcast(target_ids: list[int], text: str) -> tuple[int, int]:
        ok = 0
        fail = 0
        for uid in sorted(set(int(x) for x in target_ids if int(x) > 0)):
            try:
                bot.send_message(uid, f"📣 Сообщение от администрации:\n{text}")
                ok += 1
            except Exception:
                fail += 1
        return ok, fail

    # Routers (callbacks)
    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.ADM + ":"))
    def admin_panel_router(c: CallbackQuery):
        parts = unpack(c.data)
        action = parts[1] if len(parts) > 1 else "open"

        if storage_is_banned(c.from_user.id):
            bot.answer_callback_query(c.id, "Вы заблокированы", show_alert=True)
            return

        if not is_admin(c.from_user.id, cfg.super_admin_ids, storage_is_admin):
            bot.answer_callback_query(c.id, "Нет доступа", show_alert=True)
            return

        if action == "open":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "🛠 Админ-панель", reply_markup=admin_panel_kb())
            return

        if action == "profile":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "Отправь TG ID пользователя для просмотра профиля:")
            bot.set_state(c.from_user.id, AdminPanelStates.profile_wait_tg_id, c.message.chat.id)
            return

        if action == "balance":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "Отправь TG ID пользователя, которому нужно изменить баланс:")
            bot.set_state(c.from_user.id, AdminPanelStates.balance_wait_tg_id, c.message.chat.id)
            return

        if action == "message":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "Отправь TG ID пользователя, которому нужно написать:")
            bot.set_state(c.from_user.id, AdminPanelStates.message_wait_tg_id, c.message.chat.id)
            return
        if action == "broadcast":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "Выбери аудиторию для рассылки:", reply_markup=admin_broadcast_targets_kb())
            return

        if action == "broadcast_scope":
            scope = parts[2] if len(parts) > 2 else ""
            if scope not in ("all", "sellers", "support"):
                bot.answer_callback_query(c.id, "Некорректная аудитория", show_alert=True)
                return
            bot.answer_callback_query(c.id)
            ctx_set(c.from_user.id, c.message.chat.id, broadcast_scope=scope)
            bot.set_state(c.from_user.id, AdminPanelStates.broadcast_wait_text, c.message.chat.id)
            bot.send_message(c.message.chat.id, f"Введите текст рассылки {_broadcast_scope_title(scope)}:")
            return

        if action == "ban":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "Выбери действие:", reply_markup=admin_ban_choice_kb())
            return

        if action == "ban_set":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "Отправь TG ID пользователя, которого нужно забанить:")
            ctx_set(c.from_user.id, c.message.chat.id, ban_mode="set")
            bot.set_state(c.from_user.id, AdminPanelStates.ban_wait_tg_id, c.message.chat.id)
            return

        if action == "ban_unset":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "Отправь TG ID пользователя для разбана:")
            ctx_set(c.from_user.id, c.message.chat.id, ban_mode="unset")
            bot.set_state(c.from_user.id, AdminPanelStates.ban_wait_tg_id, c.message.chat.id)
            return

        if action == "seller_revoke":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "Отправь TG ID пользователя, у которого нужно забрать роль продавца:")
            bot.set_state(c.from_user.id, AdminPanelStates.seller_revoke_wait_tg_id, c.message.chat.id)
            return

        bot.answer_callback_query(c.id)

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.SAD + ":"))
    def super_admin_panel_router(c: CallbackQuery):
        parts = unpack(c.data)
        action = parts[1] if len(parts) > 1 else "open"

        if storage_is_banned(c.from_user.id):
            bot.answer_callback_query(c.id, "Вы заблокированы", show_alert=True)
            return

        if not is_super_admin(c.from_user.id, cfg.super_admin_ids):
            bot.answer_callback_query(c.id, "Нет доступа", show_alert=True)
            return

        if action == "open":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "👑 Панель суперадмина", reply_markup=super_admin_panel_kb())
            return

        if action == "profile":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "Отправь TG ID пользователя для просмотра профиля:")
            bot.set_state(c.from_user.id, SuperAdminPanelStates.profile_wait_tg_id, c.message.chat.id)
            return

        if action == "balance":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "Отправь TG ID пользователя, которому нужно изменить баланс:")
            bot.set_state(c.from_user.id, SuperAdminPanelStates.balance_wait_tg_id, c.message.chat.id)
            return

        if action == "message":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "Отправь TG ID пользователя, которому нужно написать:")
            bot.set_state(c.from_user.id, SuperAdminPanelStates.message_wait_tg_id, c.message.chat.id)
            return
        if action == "broadcast":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "Выбери аудиторию для рассылки:", reply_markup=super_admin_broadcast_targets_kb())
            return

        if action == "broadcast_scope":
            scope = parts[2] if len(parts) > 2 else ""
            if scope not in ("all", "sellers", "admins", "support"):
                bot.answer_callback_query(c.id, "Некорректная аудитория", show_alert=True)
                return
            bot.answer_callback_query(c.id)
            ctx_set(c.from_user.id, c.message.chat.id, broadcast_scope=scope)
            bot.set_state(c.from_user.id, SuperAdminPanelStates.broadcast_wait_text, c.message.chat.id)
            bot.send_message(c.message.chat.id, f"Введите текст рассылки {_broadcast_scope_title(scope)}:")
            return

        if action == "ban":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "Выбери действие:", reply_markup=super_admin_ban_choice_kb())
            return

        if action == "ban_set":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "Отправь TG ID пользователя, которого нужно забанить:")
            ctx_set(c.from_user.id, c.message.chat.id, ban_mode="set")
            bot.set_state(c.from_user.id, SuperAdminPanelStates.ban_wait_tg_id, c.message.chat.id)
            return

        if action == "ban_unset":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "Отправь TG ID пользователя для разбана:")
            ctx_set(c.from_user.id, c.message.chat.id, ban_mode="unset")
            bot.set_state(c.from_user.id, SuperAdminPanelStates.ban_wait_tg_id, c.message.chat.id)
            return

        if action == "seller_revoke":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "Отправь TG ID пользователя, у которого нужно забрать роль продавца:")
            bot.set_state(c.from_user.id, SuperAdminPanelStates.seller_revoke_wait_tg_id, c.message.chat.id)
            return

        if action == "admins":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "👮 Управление админами", reply_markup=super_admin_admins_kb())
            return

        if action == "admin_grant":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "Отправь TG ID пользователя, которому выдать админку:")
            bot.set_state(c.from_user.id, SuperAdminPanelStates.admin_grant_wait_tg_id, c.message.chat.id)
            return

        if action == "admin_revoke":
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "Отправь TG ID пользователя, у которого снять админку:")
            bot.set_state(c.from_user.id, SuperAdminPanelStates.admin_revoke_wait_tg_id, c.message.chat.id)
            return

        bot.answer_callback_query(c.id)

    # Admin states
    @bot.message_handler(state=AdminPanelStates.profile_wait_tg_id, content_types=["text"])
    def admin_profile_get_id(m: Message):
        if not is_admin(m.from_user.id, cfg.super_admin_ids, storage_is_admin):
            bot.send_message(m.chat.id, "Нет доступа")
            bot.delete_state(m.from_user.id, m.chat.id)
            return

        tg_id = _parse_tg_id(m.text)
        if tg_id is None:
            bot.send_message(m.chat.id, "Нужно отправить число - TG ID")
            return

        u = find_user(tg_id)
        if not u:
            bot.send_message(m.chat.id, "Пользователь не найден (еще не писал боту)")
            bot.delete_state(m.from_user.id, m.chat.id)
            return

        bot.send_message(m.chat.id, format_user_profile(u))
        bot.delete_state(m.from_user.id, m.chat.id)
        _go_home(bot, m)

    @bot.message_handler(state=AdminPanelStates.balance_wait_tg_id, content_types=["text"])
    def admin_balance_get_id(m: Message):
        if not is_admin(m.from_user.id, cfg.super_admin_ids, storage_is_admin):
            bot.send_message(m.chat.id, "Нет доступа")
            bot.delete_state(m.from_user.id, m.chat.id)
            return

        tg_id = _parse_tg_id(m.text)
        if tg_id is None:
            bot.send_message(m.chat.id, "Нужно отправить число - TG ID")
            return

        u = find_user(tg_id)
        if not u:
            bot.send_message(m.chat.id, "Пользователь не найден (еще не писал боту)")
            bot.delete_state(m.from_user.id, m.chat.id)
            return

        ctx_set(m.from_user.id, m.chat.id, target_tg_id=tg_id)
        bot.set_state(m.from_user.id, AdminPanelStates.balance_wait_new_value, m.chat.id)

        bot.send_message(
            m.chat.id,
            f"Сейчас у этого пользователя {u.balance} на балансе.\n"
            "Введи значение, которым заменится его баланс:",
        )

    @bot.message_handler(state=AdminPanelStates.balance_wait_new_value, content_types=["text"])
    def admin_balance_set(m: Message):
        if not is_admin(m.from_user.id, cfg.super_admin_ids, storage_is_admin):
            bot.send_message(m.chat.id, "Нет доступа")
            bot.delete_state(m.from_user.id, m.chat.id)
            ctx_clear(m.from_user.id, m.chat.id)
            return

        new_val = (m.text or "").strip()
        if not new_val.isdigit():
            bot.send_message(m.chat.id, "Нужно отправить число (например 0, 100, 250)")
            return

        data = ctx_get(m.from_user.id, m.chat.id)
        tg_id = int(data.get("target_tg_id", 0) or 0)
        if tg_id <= 0:
            bot.send_message(m.chat.id, "Ошибка состояния - попробуй заново")
            bot.delete_state(m.from_user.id, m.chat.id)
            ctx_clear(m.from_user.id, m.chat.id)
            return

        set_balance(
            tg_id,
            int(new_val),
            actor_id=int(m.from_user.id),
            reason=f"Изменение баланса админом {int(m.from_user.id)} через админ-панель",
        )
        u = get_user(tg_id)
        bot.send_message(m.chat.id, f"Готово. Новый баланс пользователя {tg_id}: {u.balance}")
        _safe_notify(tg_id, f"Ваш новый баланс: {u.balance}")
        bot.delete_state(m.from_user.id, m.chat.id)
        ctx_clear(m.from_user.id, m.chat.id)

    @bot.message_handler(state=AdminPanelStates.seller_revoke_wait_tg_id, content_types=["text"])
    def admin_revoke_seller(m: Message):
        if not is_admin(m.from_user.id, cfg.super_admin_ids, storage_is_admin):
            bot.send_message(m.chat.id, "Нет доступа")
            bot.delete_state(m.from_user.id, m.chat.id)
            return

        tg_id = _parse_tg_id(m.text)
        if tg_id is None:
            bot.send_message(m.chat.id, "Нужно отправить число - TG ID")
            return

        u = find_user(tg_id)
        if not u:
            bot.send_message(m.chat.id, "Пользователь не найден (еще не писал боту)")
            bot.delete_state(m.from_user.id, m.chat.id)
            return

        if not u.is_seller:
            bot.send_message(m.chat.id, f"У пользователя {tg_id} уже нет роли продавца")
            bot.delete_state(m.from_user.id, m.chat.id)
            return

        set_seller(tg_id, False)
        bot.send_message(m.chat.id, f"Готово. У пользователя {tg_id} снята роль продавца")
        _safe_notify(tg_id, "Ваша роль продавца отозвана администратором")
        bot.delete_state(m.from_user.id, m.chat.id)
        _go_home(bot, m)

    @bot.message_handler(state=AdminPanelStates.ban_wait_tg_id, content_types=["text"])
    def admin_ban_apply(m: Message):
        if not is_admin(m.from_user.id, cfg.super_admin_ids, storage_is_admin):
            bot.send_message(m.chat.id, "Нет доступа")
            bot.delete_state(m.from_user.id, m.chat.id)
            ctx_clear(m.from_user.id, m.chat.id)
            return

        tg_id = _parse_tg_id(m.text)
        if tg_id is None:
            bot.send_message(m.chat.id, "Нужно отправить число - TG ID")
            return

        data = ctx_get(m.from_user.id, m.chat.id)
        mode = data.get("ban_mode")

        if mode == "set":
            if is_super_admin(tg_id, cfg.super_admin_ids):
                bot.send_message(m.chat.id, "Нельзя забанить суперадмина")
                bot.delete_state(m.from_user.id, m.chat.id)
                ctx_clear(m.from_user.id, m.chat.id)
                return
            set_banned(tg_id, True)
            bot.send_message(m.chat.id, f"Пользователь {tg_id} забанен")
            _safe_notify(tg_id, "Ваш аккаунт заблокирован")
        else:
            set_banned(tg_id, False)
            bot.send_message(m.chat.id, f"Пользователь {tg_id} разбанен")
            _safe_notify(tg_id, "Ваш аккаунт разблокирован")

        bot.delete_state(m.from_user.id, m.chat.id)
        ctx_clear(m.from_user.id, m.chat.id)

    # Super admin states
    @bot.message_handler(state=SuperAdminPanelStates.profile_wait_tg_id, content_types=["text"])
    def super_profile_get_id(m: Message):
        if not is_super_admin(m.from_user.id, cfg.super_admin_ids):
            bot.send_message(m.chat.id, "Нет доступа")
            bot.delete_state(m.from_user.id, m.chat.id)
            return

        tg_id = _parse_tg_id(m.text)
        if tg_id is None:
            bot.send_message(m.chat.id, "Нужно отправить число - TG ID")
            return

        u = find_user(tg_id)
        if not u:
            bot.send_message(m.chat.id, "Пользователь не найден (еще не писал боту)")
            bot.delete_state(m.from_user.id, m.chat.id)
            return

        bot.send_message(m.chat.id, format_user_profile(u))
        bot.delete_state(m.from_user.id, m.chat.id)
        _go_home(bot, m)

    @bot.message_handler(state=SuperAdminPanelStates.balance_wait_tg_id, content_types=["text"])
    def super_balance_get_id(m: Message):
        if not is_super_admin(m.from_user.id, cfg.super_admin_ids):
            bot.send_message(m.chat.id, "Нет доступа")
            bot.delete_state(m.from_user.id, m.chat.id)
            ctx_clear(m.from_user.id, m.chat.id)
            return

        tg_id = _parse_tg_id(m.text)
        if tg_id is None:
            bot.send_message(m.chat.id, "Нужно отправить число - TG ID")
            return

        u = find_user(tg_id)
        if not u:
            bot.send_message(m.chat.id, "Пользователь не найден (еще не писал боту)")
            bot.delete_state(m.from_user.id, m.chat.id)
            return

        ctx_set(m.from_user.id, m.chat.id, target_tg_id=tg_id)
        bot.set_state(m.from_user.id, SuperAdminPanelStates.balance_wait_new_value, m.chat.id)

        bot.send_message(
            m.chat.id,
            f"Сейчас у этого пользователя {u.balance} на балансе.\n"
            "Введи значение, которым заменится его баланс:",
        )

    @bot.message_handler(state=SuperAdminPanelStates.balance_wait_new_value, content_types=["text"])
    def super_balance_set(m: Message):
        if not is_super_admin(m.from_user.id, cfg.super_admin_ids):
            bot.send_message(m.chat.id, "Нет доступа")
            bot.delete_state(m.from_user.id, m.chat.id)
            ctx_clear(m.from_user.id, m.chat.id)
            return

        new_val = (m.text or "").strip()
        if not new_val.isdigit():
            bot.send_message(m.chat.id, "Нужно отправить число (например 0, 100, 250)")
            return

        data = ctx_get(m.from_user.id, m.chat.id)
        tg_id = int(data.get("target_tg_id", 0) or 0)
        if tg_id <= 0:
            bot.send_message(m.chat.id, "Ошибка состояния - попробуй заново")
            bot.delete_state(m.from_user.id, m.chat.id)
            ctx_clear(m.from_user.id, m.chat.id)
            return

        set_balance(
            tg_id,
            int(new_val),
            actor_id=int(m.from_user.id),
            reason=f"Изменение баланса суперадмином {int(m.from_user.id)}",
        )
        u = get_user(tg_id)
        bot.send_message(m.chat.id, f"Готово. Новый баланс пользователя {tg_id}: {u.balance}")
        _safe_notify(tg_id, f"Ваш новый баланс: {u.balance}")
        bot.delete_state(m.from_user.id, m.chat.id)
        ctx_clear(m.from_user.id, m.chat.id)

    @bot.message_handler(state=SuperAdminPanelStates.ban_wait_tg_id, content_types=["text"])
    def super_ban_apply(m: Message):
        if not is_super_admin(m.from_user.id, cfg.super_admin_ids):
            bot.send_message(m.chat.id, "Нет доступа")
            bot.delete_state(m.from_user.id, m.chat.id)
            ctx_clear(m.from_user.id, m.chat.id)
            return

        tg_id = _parse_tg_id(m.text)
        if tg_id is None:
            bot.send_message(m.chat.id, "Нужно отправить число - TG ID")
            return

        data = ctx_get(m.from_user.id, m.chat.id)
        mode = data.get("ban_mode")

        if mode == "set":
            if is_super_admin(tg_id, cfg.super_admin_ids):
                bot.send_message(m.chat.id, "Нельзя забанить суперадмина")
                bot.delete_state(m.from_user.id, m.chat.id)
                ctx_clear(m.from_user.id, m.chat.id)
                return
            set_banned(tg_id, True)
            bot.send_message(m.chat.id, f"Пользователь {tg_id} забанен")
            _safe_notify(tg_id, "Ваш аккаунт заблокирован")
        else:
            set_banned(tg_id, False)
            bot.send_message(m.chat.id, f"Пользователь {tg_id} разбанен")
            _safe_notify(tg_id, "Ваш аккаунт разблокирован")

        bot.delete_state(m.from_user.id, m.chat.id)
        ctx_clear(m.from_user.id, m.chat.id)

    @bot.message_handler(state=SuperAdminPanelStates.seller_revoke_wait_tg_id, content_types=["text"])
    def super_revoke_seller(m: Message):
        if not is_super_admin(m.from_user.id, cfg.super_admin_ids):
            bot.send_message(m.chat.id, "Нет доступа")
            bot.delete_state(m.from_user.id, m.chat.id)
            return

        tg_id = _parse_tg_id(m.text)
        if tg_id is None:
            bot.send_message(m.chat.id, "Нужно отправить число - TG ID")
            return

        u = find_user(tg_id)
        if not u:
            bot.send_message(m.chat.id, "Пользователь не найден (еще не писал боту)")
            bot.delete_state(m.from_user.id, m.chat.id)
            return

        if not u.is_seller:
            bot.send_message(m.chat.id, f"У пользователя {tg_id} уже нет роли продавца")
            bot.delete_state(m.from_user.id, m.chat.id)
            return

        set_seller(tg_id, False)
        bot.send_message(m.chat.id, f"Готово. У пользователя {tg_id} снята роль продавца")
        _safe_notify(tg_id, "Ваша роль продавца отозвана администратором")
        bot.delete_state(m.from_user.id, m.chat.id)
        _go_home(bot, m)

    @bot.message_handler(state=SuperAdminPanelStates.admin_grant_wait_tg_id, content_types=["text"])
    def super_admin_grant(m: Message):
        if not is_super_admin(m.from_user.id, cfg.super_admin_ids):
            bot.send_message(m.chat.id, "Нет доступа")
            bot.delete_state(m.from_user.id, m.chat.id)
            return

        tg_id = _parse_tg_id(m.text)
        if tg_id is None:
            bot.send_message(m.chat.id, "Нужно отправить число - TG ID")
            return

        set_admin(tg_id, True)
        bot.send_message(m.chat.id, f"Готово. Пользователь {tg_id} теперь админ")
        bot.delete_state(m.from_user.id, m.chat.id)
        _go_home(bot, m)

    @bot.message_handler(state=SuperAdminPanelStates.admin_revoke_wait_tg_id, content_types=["text"])
    def super_admin_revoke(m: Message):
        if not is_super_admin(m.from_user.id, cfg.super_admin_ids):
            bot.send_message(m.chat.id, "Нет доступа")
            bot.delete_state(m.from_user.id, m.chat.id)
            return

        tg_id = _parse_tg_id(m.text)
        if tg_id is None:
            bot.send_message(m.chat.id, "Нужно отправить число - TG ID")
            return

        if is_super_admin(tg_id, cfg.super_admin_ids):
            bot.send_message(m.chat.id, "Нельзя снять админку у суперадмина")
            bot.delete_state(m.from_user.id, m.chat.id)
            return

        set_admin(tg_id, False)
        bot.send_message(m.chat.id, f"Готово. У пользователя {tg_id} снята админка")
        bot.delete_state(m.from_user.id, m.chat.id)
        _go_home(bot, m)


    @bot.callback_query_handler(func=lambda c: c.data in (pack(Cb.ADM, "message"), pack(Cb.SAD, "message")))
    def admin_message_entry(c: CallbackQuery):
        parts = unpack(c.data or "")
        scope = parts[0] if parts else ""

        if scope == Cb.ADM:
            if not is_admin(c.from_user.id, cfg.super_admin_ids, storage_is_admin):
                bot.answer_callback_query(c.id, "Нет доступа", show_alert=True)
                return
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "Отправь TG ID пользователя, которому нужно написать:")
            bot.set_state(c.from_user.id, AdminPanelStates.message_wait_tg_id, c.message.chat.id)
            return

        if scope == Cb.SAD:
            if not is_super_admin(c.from_user.id, cfg.super_admin_ids):
                bot.answer_callback_query(c.id, "Нет доступа", show_alert=True)
                return
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "Отправь TG ID пользователя, которому нужно написать:")
            bot.set_state(c.from_user.id, SuperAdminPanelStates.message_wait_tg_id, c.message.chat.id)
            return

        bot.answer_callback_query(c.id)

    @bot.message_handler(state=AdminPanelStates.message_wait_tg_id, content_types=["text"])
    def admin_message_get_id(m: Message):
        if not is_admin(m.from_user.id, cfg.super_admin_ids, storage_is_admin):
            bot.send_message(m.chat.id, "Нет доступа")
            bot.delete_state(m.from_user.id, m.chat.id)
            ctx_clear(m.from_user.id, m.chat.id)
            return

        tg_id = _parse_tg_id(m.text)
        if tg_id is None:
            bot.send_message(m.chat.id, "Нужно отправить число - TG ID")
            return

        u = find_user(tg_id)
        if not u:
            bot.send_message(m.chat.id, "Пользователь не найден (еще не писал боту)")
            bot.delete_state(m.from_user.id, m.chat.id)
            ctx_clear(m.from_user.id, m.chat.id)
            return

        ctx_set(m.from_user.id, m.chat.id, msg_target_tg_id=tg_id)
        bot.set_state(m.from_user.id, AdminPanelStates.message_wait_text, m.chat.id)
        bot.send_message(m.chat.id, "Введите текст сообщения для пользователя:")

    @bot.message_handler(state=AdminPanelStates.message_wait_text, content_types=["text"])
    def admin_message_send(m: Message):
        if not is_admin(m.from_user.id, cfg.super_admin_ids, storage_is_admin):
            bot.send_message(m.chat.id, "Нет доступа")
            bot.delete_state(m.from_user.id, m.chat.id)
            ctx_clear(m.from_user.id, m.chat.id)
            return

        text = (m.text or "").strip()
        if not text:
            bot.send_message(m.chat.id, "Сообщение не может быть пустым.")
            return

        data = ctx_get(m.from_user.id, m.chat.id)
        tg_id = int(data.get("msg_target_tg_id", 0) or 0)
        if tg_id <= 0:
            bot.send_message(m.chat.id, "Ошибка состояния. Начните заново.")
            bot.delete_state(m.from_user.id, m.chat.id)
            ctx_clear(m.from_user.id, m.chat.id)
            return

        try:
            bot.send_message(tg_id, f"📩 Сообщение от администрации:\n{text}")
            bot.send_message(m.chat.id, f"✅ Сообщение отправлено пользователю {tg_id}")
        except Exception:
            bot.send_message(m.chat.id, "Не удалось отправить сообщение пользователю.")
        finally:
            bot.delete_state(m.from_user.id, m.chat.id)
            ctx_clear(m.from_user.id, m.chat.id)
            _go_home(bot, m)

    @bot.message_handler(state=AdminPanelStates.broadcast_wait_text, content_types=["text"])
    def admin_broadcast_send(m: Message):
        if not is_admin(m.from_user.id, cfg.super_admin_ids, storage_is_admin):
            bot.send_message(m.chat.id, "Нет доступа")
            bot.delete_state(m.from_user.id, m.chat.id)
            ctx_clear(m.from_user.id, m.chat.id)
            return

        text = (m.text or "").strip()
        if not text:
            bot.send_message(m.chat.id, "Сообщение не может быть пустым.")
            return

        data = ctx_get(m.from_user.id, m.chat.id)
        scope = str(data.get("broadcast_scope") or "")
        if scope not in ("all", "sellers", "support"):
            bot.send_message(m.chat.id, "Ошибка состояния. Начните заново.")
            bot.delete_state(m.from_user.id, m.chat.id)
            ctx_clear(m.from_user.id, m.chat.id)
            return

        target_ids = _broadcast_target_ids(scope, super_mode=False)
        if not target_ids:
            bot.send_message(m.chat.id, f"Для рассылки {_broadcast_scope_title(scope)} получатели не найдены.")
        else:
            sent, failed = _send_broadcast(target_ids, text)
            bot.send_message(
                m.chat.id,
                f"Рассылка {_broadcast_scope_title(scope)} завершена.\n"
                f"Отправлено: {sent}\n"
                f"Не отправлено: {failed}",
            )

        bot.delete_state(m.from_user.id, m.chat.id)
        ctx_clear(m.from_user.id, m.chat.id)
        _go_home(bot, m)

    @bot.message_handler(state=SuperAdminPanelStates.message_wait_tg_id, content_types=["text"])
    def super_message_get_id(m: Message):
        if not is_super_admin(m.from_user.id, cfg.super_admin_ids):
            bot.send_message(m.chat.id, "Нет доступа")
            bot.delete_state(m.from_user.id, m.chat.id)
            ctx_clear(m.from_user.id, m.chat.id)
            return

        tg_id = _parse_tg_id(m.text)
        if tg_id is None:
            bot.send_message(m.chat.id, "Нужно отправить число - TG ID")
            return

        u = find_user(tg_id)
        if not u:
            bot.send_message(m.chat.id, "Пользователь не найден (еще не писал боту)")
            bot.delete_state(m.from_user.id, m.chat.id)
            ctx_clear(m.from_user.id, m.chat.id)
            return

        ctx_set(m.from_user.id, m.chat.id, msg_target_tg_id=tg_id)
        bot.set_state(m.from_user.id, SuperAdminPanelStates.message_wait_text, m.chat.id)
        bot.send_message(m.chat.id, "Введите текст сообщения для пользователя:")

    @bot.message_handler(state=SuperAdminPanelStates.message_wait_text, content_types=["text"])
    def super_message_send(m: Message):
        if not is_super_admin(m.from_user.id, cfg.super_admin_ids):
            bot.send_message(m.chat.id, "Нет доступа")
            bot.delete_state(m.from_user.id, m.chat.id)
            ctx_clear(m.from_user.id, m.chat.id)
            return

        text = (m.text or "").strip()
        if not text:
            bot.send_message(m.chat.id, "Сообщение не может быть пустым.")
            return

        data = ctx_get(m.from_user.id, m.chat.id)
        tg_id = int(data.get("msg_target_tg_id", 0) or 0)
        if tg_id <= 0:
            bot.send_message(m.chat.id, "Ошибка состояния. Начните заново.")
            bot.delete_state(m.from_user.id, m.chat.id)
            ctx_clear(m.from_user.id, m.chat.id)
            return

        try:
            bot.send_message(tg_id, f"📩 Сообщение от администрации:\n{text}")
            bot.send_message(m.chat.id, f"✅ Сообщение отправлено пользователю {tg_id}")
        except Exception:
            bot.send_message(m.chat.id, "Не удалось отправить сообщение пользователю.")
        finally:
            bot.delete_state(m.from_user.id, m.chat.id)
            ctx_clear(m.from_user.id, m.chat.id)
            _go_home(bot, m)

    @bot.message_handler(state=SuperAdminPanelStates.broadcast_wait_text, content_types=["text"])
    def super_broadcast_send(m: Message):
        if not is_super_admin(m.from_user.id, cfg.super_admin_ids):
            bot.send_message(m.chat.id, "Нет доступа")
            bot.delete_state(m.from_user.id, m.chat.id)
            ctx_clear(m.from_user.id, m.chat.id)
            return

        text = (m.text or "").strip()
        if not text:
            bot.send_message(m.chat.id, "Сообщение не может быть пустым.")
            return

        data = ctx_get(m.from_user.id, m.chat.id)
        scope = str(data.get("broadcast_scope") or "")
        if scope not in ("all", "sellers", "admins", "support"):
            bot.send_message(m.chat.id, "Ошибка состояния. Начните заново.")
            bot.delete_state(m.from_user.id, m.chat.id)
            ctx_clear(m.from_user.id, m.chat.id)
            return

        target_ids = _broadcast_target_ids(scope, super_mode=True)
        if not target_ids:
            bot.send_message(m.chat.id, f"Для рассылки {_broadcast_scope_title(scope)} получатели не найдены.")
        else:
            sent, failed = _send_broadcast(target_ids, text)
            bot.send_message(
                m.chat.id,
                f"Рассылка {_broadcast_scope_title(scope)} завершена.\n"
                f"Отправлено: {sent}\n"
                f"Не отправлено: {failed}",
            )

        bot.delete_state(m.from_user.id, m.chat.id)
        ctx_clear(m.from_user.id, m.chat.id)
        _go_home(bot, m)


