from telebot import TeleBot
from telebot.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup

from ..callbacks import Cb, pack, unpack
from ..config import Config
from ..keyboards import support_kb
from ..states import SupportStates
from .start import show_home
from ..storage import (
    get_user,
    create_withdraw_request,
    get_withdraw_request,
    review_withdraw_request,
    take_withdraw_request,
)


_SUPPORT_CTX: dict[tuple[int, int], dict] = {}
_SUPPORT_TAKEN: dict[int, int] = {}


def _ctx_key(user_id: int, chat_id: int) -> tuple[int, int]:
    return int(user_id), int(chat_id)


def _ctx_set(user_id: int, chat_id: int, **kwargs) -> None:
    k = _ctx_key(user_id, chat_id)
    d = _SUPPORT_CTX.get(k) or {}
    d.update(kwargs)
    _SUPPORT_CTX[k] = d


def _ctx_get(user_id: int, chat_id: int) -> dict:
    return _SUPPORT_CTX.get(_ctx_key(user_id, chat_id), {})


def _ctx_clear(user_id: int, chat_id: int) -> None:
    _SUPPORT_CTX.pop(_ctx_key(user_id, chat_id), None)


def _is_support(user_id: int, cfg: Config) -> bool:
    return int(user_id) in set(cfg.support_ids)


def _take_support_request(*, target_id: int, support_id: int) -> tuple[bool, str]:
    tid = int(target_id)
    sid = int(support_id)
    owner = _SUPPORT_TAKEN.get(tid)
    if owner is None:
        _SUPPORT_TAKEN[tid] = sid
        return True, "ok"
    if int(owner) == sid:
        return False, "already_taken_by_you"
    return False, f"taken_by_other:{int(owner)}"


def _withdraw_admin_kb(request_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("👀 Взять в рассмотрение", callback_data=pack(Cb.SUP, "wd", "take", str(request_id))))
    return kb


def _support_take_kb(target_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("👀 Взять в рассмотрение", callback_data=pack(Cb.SUP, "take", str(target_id))))
    return kb


def _support_reply_kb(target_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("Ответить", callback_data=pack(Cb.SUP, "answer", str(target_id))))
    return kb


def _withdraw_decision_kb(request_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.row(
        InlineKeyboardButton("✅ Принять", callback_data=pack(Cb.SUP, "wd", "approve", str(request_id))),
        InlineKeyboardButton("❌ Отклонить", callback_data=pack(Cb.SUP, "wd", "reject", str(request_id))),
    )
    return kb


def _home_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🏠 Главное меню", callback_data=pack(Cb.NAV, "home")))
    return kb


def _go_home(bot: TeleBot, m: Message) -> None:
    cfg = getattr(bot, "_cfg", None)
    if cfg is not None:
        show_home(bot, cfg, chat_id=m.chat.id, user_id=m.from_user.id, username=m.from_user.username)
    else:
        bot.send_message(m.chat.id, "Введите /start для перехода в главное меню.")


def register(bot: TeleBot, cfg: Config):
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
        if not cfg.support_ids:
            bot.send_message(c.message.chat.id, "Поддержка сейчас недоступна. Попробуйте позже.")
            return
        bot.send_message(c.message.chat.id, "📝 Напишите сообщение в поддержку.")
        bot.set_state(c.from_user.id, SupportStates.waiting_message, c.message.chat.id)

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.SUP + ":withdraw"))
    def support_withdraw_entry(c: CallbackQuery):
        bot.answer_callback_query(c.id)
        u = get_user(c.from_user.id, c.from_user.username)
        if not bool(getattr(u, "is_seller", False)):
            bot.send_message(c.message.chat.id, "Запрос на вывод доступен только продавцам.")
            return

        if int(u.balance) <= 0:
            bot.send_message(c.message.chat.id, "Недостаточно средств для вывода.")
            return

        bot.send_message(c.message.chat.id, "Укажите причину вывода средств:")
        bot.set_state(c.from_user.id, SupportStates.waiting_withdraw_reason, c.message.chat.id)

    @bot.message_handler(state=SupportStates.waiting_withdraw_reason, content_types=["text"])
    def support_withdraw_reason(m: Message):
        u = get_user(m.from_user.id, m.from_user.username)
        if not bool(getattr(u, "is_seller", False)):
            bot.delete_state(m.from_user.id, m.chat.id)
            _ctx_clear(m.from_user.id, m.chat.id)
            bot.send_message(m.chat.id, "Запрос на вывод доступен только продавцам.")
            return

        reason = (m.text or "").strip()
        if len(reason) < 5:
            bot.send_message(m.chat.id, "Причина слишком короткая. Напишите подробнее (минимум 5 символов).")
            return

        _ctx_set(m.from_user.id, m.chat.id, wd_reason=reason)
        bot.set_state(m.from_user.id, SupportStates.waiting_withdraw_amount, m.chat.id)
        bot.send_message(m.chat.id, f"Укажите сумму вывода (числом). Доступно: {u.balance}")

    @bot.message_handler(state=SupportStates.waiting_withdraw_amount, content_types=["text"])
    def support_withdraw_amount(m: Message):
        u = get_user(m.from_user.id, m.from_user.username)
        if not bool(getattr(u, "is_seller", False)):
            bot.delete_state(m.from_user.id, m.chat.id)
            _ctx_clear(m.from_user.id, m.chat.id)
            bot.send_message(m.chat.id, "Запрос на вывод доступен только продавцам.")
            return

        raw = (m.text or "").strip()
        if not raw.isdigit() or int(raw) <= 0:
            bot.send_message(m.chat.id, "Сумма должна быть положительным числом.")
            return

        amount = int(raw)
        if amount > int(u.balance):
            bot.send_message(m.chat.id, f"Сумма больше доступного баланса ({u.balance}).")
            return

        _ctx_set(m.from_user.id, m.chat.id, wd_amount=amount)
        bot.set_state(m.from_user.id, SupportStates.waiting_withdraw_phone, m.chat.id)
        bot.send_message(m.chat.id, "Укажите номер телефона для вывода:")

    @bot.message_handler(state=SupportStates.waiting_withdraw_phone, content_types=["text"])
    def support_withdraw_phone(m: Message):
        u = get_user(m.from_user.id, m.from_user.username)
        if not bool(getattr(u, "is_seller", False)):
            bot.delete_state(m.from_user.id, m.chat.id)
            _ctx_clear(m.from_user.id, m.chat.id)
            bot.send_message(m.chat.id, "Запрос на вывод доступен только продавцам.")
            return

        payout_phone = (m.text or "").strip()
        if len(payout_phone) < 6:
            bot.send_message(m.chat.id, "Укажите корректный номер телефона.")
            return

        _ctx_set(m.from_user.id, m.chat.id, wd_phone=payout_phone)
        bot.set_state(m.from_user.id, SupportStates.waiting_withdraw_bank, m.chat.id)
        bot.send_message(m.chat.id, "Укажите банк для вывода:")

    @bot.message_handler(state=SupportStates.waiting_withdraw_bank, content_types=["text"])
    def support_withdraw_bank(m: Message):
        u = get_user(m.from_user.id, m.from_user.username)
        if not bool(getattr(u, "is_seller", False)):
            bot.delete_state(m.from_user.id, m.chat.id)
            _ctx_clear(m.from_user.id, m.chat.id)
            bot.send_message(m.chat.id, "Запрос на вывод доступен только продавцам.")
            return

        payout_bank = (m.text or "").strip()
        if len(payout_bank) < 2:
            bot.send_message(m.chat.id, "Укажите корректное название банка.")
            return

        data = _ctx_get(m.from_user.id, m.chat.id)
        reason = str(data.get("wd_reason") or "").strip()
        amount = int(data.get("wd_amount") or 0)
        payout_phone = str(data.get("wd_phone") or "").strip()
        if not reason or amount <= 0 or not payout_phone:
            bot.delete_state(m.from_user.id, m.chat.id)
            _ctx_clear(m.from_user.id, m.chat.id)
            bot.send_message(m.chat.id, "Сессия вывода потеряна. Начните заново через «Запрос на вывод».")
            _go_home(bot, m)
            return
        if amount > int(u.balance):
            bot.delete_state(m.from_user.id, m.chat.id)
            _ctx_clear(m.from_user.id, m.chat.id)
            bot.send_message(
                m.chat.id,
                f"Сумма вывода больше вашего текущего баланса ({u.balance}). Создайте заявку заново.",
            )
            _go_home(bot, m)
            return

        try:
            request_id = create_withdraw_request(
                user_id=m.from_user.id,
                amount=amount,
                reason=reason,
                payout_phone=payout_phone,
                payout_bank=payout_bank,
            )
        except Exception:
            bot.send_message(m.chat.id, "Не удалось создать заявку на вывод. Попробуйте позже.")
            bot.delete_state(m.from_user.id, m.chat.id)
            _ctx_clear(m.from_user.id, m.chat.id)
            return

        uname = f"@{m.from_user.username}" if m.from_user.username else "нет"
        payload = (
            "💸 Новая заявка на вывод\n"
            f"Заявка: #{request_id}\n"
            f"Продавец ID: {m.from_user.id}\n"
            f"Username: {uname}\n"
            f"Телефон: {payout_phone}\n"
            f"Банк: {payout_bank}\n"
            f"Сумма: {amount}\n"
            f"Причина: {reason}"
        )

        sent = 0
        for admin_id in cfg.admin_ids:
            try:
                bot.send_message(int(admin_id), payload, reply_markup=_withdraw_admin_kb(request_id))
                sent += 1
            except Exception:
                pass

        bot.delete_state(m.from_user.id, m.chat.id)
        _ctx_clear(m.from_user.id, m.chat.id)

        if sent == 0:
            bot.send_message(m.chat.id, "Заявка создана, но не удалось уведомить администрацию.")
            _go_home(bot, m)
            return

        bot.send_message(m.chat.id, f"✅ Заявка на вывод #{request_id} отправлена администрации.")
        _go_home(bot, m)

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.SUP + ":wd:"))
    def support_withdraw_review(c: CallbackQuery):
        parts = unpack(c.data)
        action = parts[2] if len(parts) > 2 else ""
        req_raw = parts[3] if len(parts) > 3 else "0"

        if int(c.from_user.id) not in set(cfg.admin_ids):
            bot.answer_callback_query(c.id, "Нет доступа", show_alert=True)
            return
        if action not in ("take", "approve", "reject") or not req_raw.isdigit():
            bot.answer_callback_query(c.id, "Некорректные данные", show_alert=True)
            return

        request_id = int(req_raw)
        if action == "take":
            ok, reason = take_withdraw_request(
                request_id=request_id,
                admin_id=c.from_user.id,
            )
            if not ok:
                if reason.startswith("already_processed:"):
                    st = reason.split(":", 1)[1]
                    bot.answer_callback_query(c.id, f"Уже обработано: {st}", show_alert=True)
                elif reason == "already_taken_by_you":
                    bot.answer_callback_query(c.id, "Заявка уже у вас в рассмотрении", show_alert=True)
                elif reason.startswith("taken_by_other:"):
                    owner = reason.split(":", 1)[1]
                    bot.answer_callback_query(c.id, f"Заявка уже взята админом {owner}", show_alert=True)
                else:
                    bot.answer_callback_query(c.id, "Не удалось взять заявку", show_alert=True)
                return

            try:
                bot.edit_message_reply_markup(
                    chat_id=c.message.chat.id,
                    message_id=c.message.message_id,
                    reply_markup=_withdraw_decision_kb(request_id),
                )
            except Exception:
                pass
            notice = f"👀 Заявка на вывод #{request_id} взята в рассмотрение админом {c.from_user.id}"
            for admin_id in cfg.admin_ids:
                try:
                    bot.send_message(int(admin_id), notice)
                except Exception:
                    pass
            bot.answer_callback_query(c.id, "Взято в рассмотрение")
            return

        approve = action == "approve"
        ok, reason = review_withdraw_request(
            request_id=request_id,
            admin_id=c.from_user.id,
            approve=approve,
        )

        if not ok:
            if reason.startswith("already_processed:"):
                st = reason.split(":", 1)[1]
                bot.answer_callback_query(c.id, f"Уже обработано: {st}", show_alert=True)
            elif reason == "not_taken":
                bot.answer_callback_query(c.id, "Сначала возьмите заявку в рассмотрение", show_alert=True)
            elif reason.startswith("taken_by_other:"):
                owner = reason.split(":", 1)[1]
                bot.answer_callback_query(c.id, f"Заявку рассматривает админ {owner}", show_alert=True)
            elif reason == "insufficient_balance":
                bot.answer_callback_query(c.id, "Недостаточно баланса у продавца", show_alert=True)
            else:
                bot.answer_callback_query(c.id, "Не удалось обработать заявку", show_alert=True)
            return

        req = get_withdraw_request(request_id)
        if not req:
            bot.answer_callback_query(c.id, "Заявка не найдена", show_alert=True)
            return

        status_text = "✅ ПРИНЯТО" if approve else "❌ ОТКЛОНЕНО"
        reviewed_payload = (
            "💸 Заявка на вывод обработана\n"
            f"Заявка: #{request_id}\n"
            f"Продавец ID: {int(req['user_id'])}\n"
            f"Сумма: {int(req['amount'])}\n"
            f"Статус: {status_text}\n"
            f"Админ: {c.from_user.id}"
        )
        try:
            bot.edit_message_text(
                chat_id=c.message.chat.id,
                message_id=c.message.message_id,
                text=reviewed_payload,
            )
        except Exception:
            pass

        try:
            if approve:
                bot.send_message(
                    int(req["user_id"]),
                    f"✅ Ваша заявка на вывод #{request_id} одобрена. Сумма: {int(req['amount'])}.\nОжидайте ответ администрации.",
                    reply_markup=_home_kb(),
                )
            else:
                bot.send_message(
                    int(req["user_id"]),
                    f"❌ Ваша заявка на вывод #{request_id} отклонена администратором.",
                    reply_markup=_home_kb(),
                )
            show_home(
                bot,
                cfg,
                chat_id=int(req["user_id"]),
                user_id=int(req["user_id"]),
                username=None,
            )
        except Exception:
            pass

        bot.answer_callback_query(c.id, "Готово")

    @bot.message_handler(state=SupportStates.waiting_message, content_types=["text"])
    def support_message(m: Message):
        bot.delete_state(m.from_user.id, m.chat.id)

        text = (m.text or "").strip()
        if not text:
            bot.send_message(m.chat.id, "Сообщение пустое. Попробуйте еще раз через меню поддержки.")
            return

        uname = f"@{m.from_user.username}" if m.from_user.username else "нет"
        display_name = (m.from_user.first_name or "").strip() or "Без имени"
        _SUPPORT_TAKEN.pop(int(m.from_user.id), None)

        payload = (
            "📩 Новое сообщение в поддержку\n"
            f"Пользователь: {display_name}\n"
            f"Username: {uname}\n"
            f"ID: {m.from_user.id}\n\n"
            f"Сообщение:\n{text}"
        )

        delivered = 0
        for support_id in cfg.support_ids:
            try:
                bot.send_message(int(support_id), payload, reply_markup=_support_take_kb(int(m.from_user.id)))
                delivered += 1
            except Exception:
                pass

        if delivered == 0:
            bot.send_message(m.chat.id, "Не удалось отправить сообщение в поддержку. Попробуйте позже.")
            _go_home(bot, m)
            return

        bot.send_message(m.chat.id, "✅ Ваше сообщение отправлено в поддержку.")
        _go_home(bot, m)

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.SUP + ":take:"))
    def support_take_entry(c: CallbackQuery):
        parts = unpack(c.data)
        target_raw = parts[2] if len(parts) > 2 else "0"

        if not _is_support(c.from_user.id, cfg):
            bot.answer_callback_query(c.id, "Нет доступа", show_alert=True)
            return
        if not target_raw.isdigit():
            bot.answer_callback_query(c.id, "Некорректный ID", show_alert=True)
            return

        target_id = int(target_raw)
        ok, reason = _take_support_request(target_id=target_id, support_id=c.from_user.id)
        if not ok:
            if reason == "already_taken_by_you":
                bot.answer_callback_query(c.id, "Уже у вас в рассмотрении", show_alert=True)
            elif reason.startswith("taken_by_other:"):
                owner = reason.split(":", 1)[1]
                bot.answer_callback_query(c.id, f"Уже взято поддержкой {owner}", show_alert=True)
            else:
                bot.answer_callback_query(c.id, "Не удалось взять в рассмотрение", show_alert=True)
            return

        try:
            bot.edit_message_reply_markup(
                chat_id=c.message.chat.id,
                message_id=c.message.message_id,
                reply_markup=_support_reply_kb(target_id),
            )
        except Exception:
            pass
        notice = f"👀 Обращение пользователя {target_id} взято в рассмотрение поддержкой {c.from_user.id}"
        for support_id in cfg.support_ids:
            try:
                bot.send_message(int(support_id), notice)
            except Exception:
                pass
        bot.answer_callback_query(c.id, "Взято в рассмотрение")

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.SUP + ":answer:"))
    def support_answer_entry(c: CallbackQuery):
        parts = unpack(c.data)
        target_raw = parts[2] if len(parts) > 2 else "0"

        if not _is_support(c.from_user.id, cfg):
            bot.answer_callback_query(c.id, "Нет доступа", show_alert=True)
            return
        if not target_raw.isdigit():
            bot.answer_callback_query(c.id, "Некорректный ID", show_alert=True)
            return

        target_id = int(target_raw)
        owner = _SUPPORT_TAKEN.get(target_id)
        if owner is None:
            bot.answer_callback_query(c.id, "Сначала возьмите в рассмотрение", show_alert=True)
            return
        if int(owner) != int(c.from_user.id):
            bot.answer_callback_query(c.id, f"Эту заявку ведет поддержка {owner}", show_alert=True)
            return

        _ctx_set(c.from_user.id, c.message.chat.id, reply_target_id=target_id)
        bot.set_state(c.from_user.id, SupportStates.waiting_reply, c.message.chat.id)
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, f"Напишите ответ пользователю {target_id}:")

    @bot.message_handler(state=SupportStates.waiting_reply, content_types=["text"])
    def support_send_reply(m: Message):
        if not _is_support(m.from_user.id, cfg):
            bot.delete_state(m.from_user.id, m.chat.id)
            _ctx_clear(m.from_user.id, m.chat.id)
            bot.send_message(m.chat.id, "Нет доступа")
            return

        data = _ctx_get(m.from_user.id, m.chat.id)
        target_id = int(data.get("reply_target_id", 0) or 0)
        if target_id <= 0:
            bot.delete_state(m.from_user.id, m.chat.id)
            _ctx_clear(m.from_user.id, m.chat.id)
            bot.send_message(m.chat.id, "Ошибка состояния. Нажмите «Ответить» еще раз.")
            return

        reply_text = (m.text or "").strip()
        if not reply_text:
            bot.send_message(m.chat.id, "Ответ не может быть пустым.")
            return

        try:
            bot.send_message(target_id, f"Ответ от поддержки:\n{reply_text}")
            bot.send_message(m.chat.id, "✅ Ответ отправлен")
            _SUPPORT_TAKEN.pop(target_id, None)
        except Exception:
            bot.send_message(m.chat.id, "Не удалось отправить ответ пользователю.")
        finally:
            bot.delete_state(m.from_user.id, m.chat.id)
            _ctx_clear(m.from_user.id, m.chat.id)
            _go_home(bot, m)
