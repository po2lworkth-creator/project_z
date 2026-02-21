from typing import Optional

from telebot import TeleBot
from telebot.types import (
    CallbackQuery,
    Message,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from ..callbacks import Cb, pack
from ..config import Config
from ..models import (
    SELLER_STATUS_NONE,
    SELLER_STATUS_APPLIED,
    SELLER_STATUS_SELLER,
    SELLER_STATUS_REJECTED,
)
from ..storage import (
    get_user,
    verify_user_phone,
    apply_seller,
    approve_seller,
    reject_seller,
    take_seller_application_review,
    can_review_seller_application,
)
from ..keyboards import profile_kb
from ..utils import format_display_datetime
from .start import is_home_text, show_home


def _go_home(bot: TeleBot, m: Message) -> None:
    cfg = getattr(bot, "_cfg", None)
    if cfg is not None:
        show_home(bot, cfg, chat_id=m.chat.id, user_id=m.from_user.id, username=m.from_user.username)
    else:
        bot.send_message(m.chat.id, "Введите /start для перехода в главное меню.")


def _apply_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📝 Подать заявку на продавца", callback_data=pack(Cb.SELL, "apply")))
    return kb


def _verify_phone_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("📱 Отправить номер", request_contact=True))
    return kb


def _admin_review_kb(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("👀 Взять в рассмотрение", callback_data=pack(Cb.SELL, f"adm_take:{user_id}")))
    return kb


def _admin_decision_kb(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton("✅ Подтвердить", callback_data=pack(Cb.SELL, f"adm_approve:{user_id}")),
        InlineKeyboardButton("❌ Отклонить", callback_data=pack(Cb.SELL, f"adm_reject:{user_id}")),
    )
    return kb


def _parse_user_id(action: str, prefix: str) -> Optional[int]:
    if not action.startswith(prefix + ":"):
        return None
    tail = action.split(":", 1)[1].strip()
    return int(tail) if tail.isdigit() else None


def _is_phone_verified(u) -> bool:
    return getattr(u, "seller_verified_phone", False) is True


def _has_phone(u) -> bool:
    phone = getattr(u, "phone", None)
    return bool(phone and str(phone).strip())


def _send_profile(bot: TeleBot, chat_id: int, user_id: int, username: Optional[str]):
    u = get_user(user_id, username)
    username_text = f"@{u.username}" if u.username else "нет"
    phone_linked = bool(u.phone)
    phone_text = u.phone if u.phone else "не привязан"
    created_at = format_display_datetime(u.created_at)

    text = (
        "👤 Профиль\n"
        f"ID: {u.user_id}\n"
        f"Username: {username_text}\n"
        f"Баланс: {u.balance}\n\n"
        f"Телефон: {phone_text}\n"
        f"Регистрация: {created_at}\n"
    )

    bot.send_message(
        chat_id,
        text,
        reply_markup=profile_kb(phone_linked=phone_linked),
    )


def _send_seller_next_step(bot: TeleBot, chat_id: int, u):
    if u.seller_status == SELLER_STATUS_SELLER or u.is_seller:
        bot.send_message(chat_id, "✅ У тебя уже есть возможности продавца.")
        return

    if u.seller_status == SELLER_STATUS_APPLIED:
        bot.send_message(chat_id, "⏳ Заявка уже подана и ожидает рассмотрения.")
        return

    if u.seller_status in (SELLER_STATUS_NONE, SELLER_STATUS_REJECTED):
        bot.send_message(
            chat_id,
            "✅ Телефон подтвержден.\nТеперь можешь подать заявку на роль продавца.",
            reply_markup=_apply_kb(),
        )
        return

    bot.send_message(chat_id, "Статус продавца не распознан. Напиши в поддержку.")


def _submit_seller_application(bot: TeleBot, cfg: Config, chat_id: int, u, reason: str) -> None:
    ok = apply_seller(u.user_id)
    if not ok:
        bot.send_message(chat_id, "Не получилось подать заявку. Напиши в поддержку.")
        return

    bot.send_message(chat_id, "✅ Заявка подана.\nОжидайте подтверждения от модератора.")

    username = f"@{u.username}" if u.username else "нет"
    reason = reason.strip()

    for admin_id in cfg.admin_ids:
        bot.send_message(
            admin_id,
            (
                "📝 Новая заявка на продавца\n"
                f"User ID: {u.user_id}\n"
                f"Username: {username}\n"
                f"Телефон: {u.phone}\n"
                f"Причина: {reason}"
            ),
            reply_markup=_admin_review_kb(u.user_id),
        )


def _on_seller_reason(m: Message, bot: TeleBot, cfg: Config):
    if is_home_text(m.text):
        bot.delete_state(m.from_user.id, m.chat.id)
        _go_home(bot, m)
        return

    reason = (m.text or "").strip()
    if len(reason) < 5:
        msg = bot.send_message(m.chat.id, "Напиши, зачем тебе роль продавца (минимум 5 символов).")
        bot.register_next_step_handler(msg, _on_seller_reason, bot, cfg)
        return

    u = get_user(m.from_user.id, m.from_user.username)

    if not _is_phone_verified(u) or not _has_phone(u):
        bot.send_message(
            m.chat.id,
            "Сначала подтвердите номер телефона - нажмите «Получить возможности продавца» и отправьте контакт.",
        )
        return

    if u.seller_status == SELLER_STATUS_SELLER or u.is_seller:
        bot.send_message(m.chat.id, "Ты уже продавец.")
        return

    if u.seller_status == SELLER_STATUS_APPLIED:
        bot.send_message(m.chat.id, "Заявка уже подана и ожидает рассмотрения.")
        return

    _submit_seller_application(bot, cfg, m.chat.id, u, reason)


def register(bot: TeleBot, cfg: Config):
    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.SELL + ":verify_phone"))
    def verify_phone_entry(c: CallbackQuery):
        bot.answer_callback_query(c.id)
        u = get_user(c.from_user.id, c.from_user.username)

        if not _has_phone(u):
            bot.send_message(
                c.message.chat.id,
                "✅ Чтобы получить возможности продавца, сначала привяжи номер - нажми кнопку ниже и отправь свой контакт.",
                reply_markup=_verify_phone_kb(),
            )
            return

        if not _is_phone_verified(u):
            verify_user_phone(u.user_id, u.phone)

        u = get_user(c.from_user.id, c.from_user.username)
        _send_seller_next_step(bot, c.message.chat.id, u)

    @bot.callback_query_handler(func=lambda c: c.data and c.data == pack(Cb.SELL, "apply"))
    def apply_seller_role(c: CallbackQuery):
        bot.answer_callback_query(c.id)
        u = get_user(c.from_user.id, c.from_user.username)

        if not _is_phone_verified(u) or not _has_phone(u):
            bot.send_message(
                c.message.chat.id,
                "Сначала подтвердите номер телефона - нажмите «Получить возможности продавца» и отправьте контакт.",
            )
            return

        if u.seller_status == SELLER_STATUS_SELLER or u.is_seller:
            bot.send_message(c.message.chat.id, "Ты уже продавец.")
            return

        if u.seller_status == SELLER_STATUS_APPLIED:
            bot.send_message(c.message.chat.id, "Заявка уже подана и ожидает рассмотрения.")
            return

        msg = bot.send_message(
            c.message.chat.id,
            "Напиши, зачем тебе роль продавца. Без этого заявка не отправится на модерацию.",
        )
        bot.register_next_step_handler(msg, _on_seller_reason, bot, cfg)

    @bot.message_handler(content_types=["contact"])
    def got_contact_anytime(m: Message):
        get_user(m.from_user.id, m.from_user.username)

        if not m.contact:
            bot.send_message(m.chat.id, "Нужно отправить контакт кнопкой «📱 Отправить номер».")
            return

        if m.contact.user_id is not None and m.contact.user_id != m.from_user.id:
            bot.send_message(m.chat.id, "Нужно отправить СВОЙ контакт кнопкой «📱 Отправить номер».")
            return

        phone = (m.contact.phone_number or "").strip()
        if not phone:
            bot.send_message(m.chat.id, "Не смог прочитать номер из контакта. Попробуй еще раз.")
            return

        verify_user_phone(m.from_user.id, phone)

        bot.send_message(
            m.chat.id,
            "✅ Телефон привязан.",
            reply_markup=ReplyKeyboardRemove(),
        )

        _send_profile(bot, m.chat.id, m.from_user.id, m.from_user.username)

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.SELL + ":adm_take:"))
    def admin_take(c: CallbackQuery):
        bot.answer_callback_query(c.id)

        if c.from_user.id not in cfg.admin_ids:
            bot.send_message(c.message.chat.id, "Нет прав.")
            return

        action = c.data.split(":", 1)[1]
        user_id = _parse_user_id(action, "adm_take")
        if user_id is None:
            bot.send_message(c.message.chat.id, "Не смог прочитать user_id.")
            return

        ok, reason = take_seller_application_review(user_id=user_id, admin_id=c.from_user.id)
        if not ok:
            if reason == "already_taken_by_you":
                bot.send_message(c.message.chat.id, "Эта заявка уже у вас в рассмотрении.")
            elif reason.startswith("taken_by_other:"):
                owner = reason.split(":", 1)[1]
                bot.send_message(c.message.chat.id, f"Заявка уже взята другим админом ({owner}).")
            elif reason.startswith("invalid_status:"):
                st = reason.split(":", 1)[1]
                bot.send_message(c.message.chat.id, f"Заявка уже обработана (статус: {st}).")
                try:
                    bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)
                except Exception:
                    pass
            else:
                bot.send_message(c.message.chat.id, "Не удалось взять заявку в рассмотрение.")
            return

        bot.send_message(c.message.chat.id, f"Заявка пользователя {user_id} взята в рассмотрение.")
        notice = f"👀 Заявка на продавца пользователя {user_id} взята в рассмотрение админом {c.from_user.id}"
        for admin_id in cfg.admin_ids:
            try:
                bot.send_message(int(admin_id), notice)
            except Exception:
                pass
        try:
            bot.edit_message_reply_markup(
                c.message.chat.id,
                c.message.message_id,
                reply_markup=_admin_decision_kb(user_id),
            )
        except Exception:
            pass

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.SELL + ":adm_approve:"))
    def admin_approve(c: CallbackQuery):
        bot.answer_callback_query(c.id)

        if c.from_user.id not in cfg.admin_ids:
            bot.send_message(c.message.chat.id, "Нет прав.")
            return

        action = c.data.split(":", 1)[1]
        user_id = _parse_user_id(action, "adm_approve")
        if user_id is None:
            bot.send_message(c.message.chat.id, "Не смог прочитать user_id.")
            return

        can_review, reason = can_review_seller_application(user_id=user_id, admin_id=c.from_user.id)
        if not can_review:
            if reason == "not_taken":
                bot.send_message(c.message.chat.id, "Сначала возьмите заявку в рассмотрение.")
            elif reason.startswith("taken_by_other:"):
                owner = reason.split(":", 1)[1]
                bot.send_message(c.message.chat.id, f"Заявку рассматривает другой админ ({owner}).")
            elif reason.startswith("invalid_status:"):
                st = reason.split(":", 1)[1]
                bot.send_message(c.message.chat.id, f"Заявка уже обработана (статус: {st}).")
                try:
                    bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)
                except Exception:
                    pass
            else:
                bot.send_message(c.message.chat.id, "Не удалось обработать заявку.")
            return

        u = get_user(user_id, None)

        if not _is_phone_verified(u) or not _has_phone(u):
            bot.send_message(
                c.message.chat.id,
                f"Нельзя подтвердить - у пользователя нет подтвержденного телефона: {user_id}",
            )
            return

        approve_seller(user_id)

        bot.send_message(c.message.chat.id, f"✅ Пользователь подтвержден: {user_id}")
        bot.send_message(user_id, "✅ Ваша заявка принята - теперь вы продавец.")

        try:
            bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)
        except Exception:
            pass
        show_home(
            bot,
            cfg,
            chat_id=c.message.chat.id,
            user_id=c.from_user.id,
            username=c.from_user.username,
        )

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.SELL + ":adm_reject:"))
    def admin_reject(c: CallbackQuery):
        bot.answer_callback_query(c.id)

        if c.from_user.id not in cfg.admin_ids:
            bot.send_message(c.message.chat.id, "Нет прав.")
            return

        action = c.data.split(":", 1)[1]
        user_id = _parse_user_id(action, "adm_reject")
        if user_id is None:
            bot.send_message(c.message.chat.id, "Не смог прочитать user_id.")
            return

        can_review, reason = can_review_seller_application(user_id=user_id, admin_id=c.from_user.id)
        if not can_review:
            if reason == "not_taken":
                bot.send_message(c.message.chat.id, "Сначала возьмите заявку в рассмотрение.")
            elif reason.startswith("taken_by_other:"):
                owner = reason.split(":", 1)[1]
                bot.send_message(c.message.chat.id, f"Заявку рассматривает другой админ ({owner}).")
            elif reason.startswith("invalid_status:"):
                st = reason.split(":", 1)[1]
                bot.send_message(c.message.chat.id, f"Заявка уже обработана (статус: {st}).")
                try:
                    bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)
                except Exception:
                    pass
            else:
                bot.send_message(c.message.chat.id, "Не удалось обработать заявку.")
            return

        reject_seller(user_id)

        bot.send_message(c.message.chat.id, f"❌ Пользователь отклонен: {user_id}")
        bot.send_message(user_id, "❌ Ваша заявка отклонена. Можно подать повторно после уточнения в поддержке.")

        try:
            bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)
        except Exception:
            pass
        show_home(
            bot,
            cfg,
            chat_id=c.message.chat.id,
            user_id=c.from_user.id,
            username=c.from_user.username,
        )

