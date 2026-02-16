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
)


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
    kb.row(
        InlineKeyboardButton("✅ Подтвердить", callback_data=pack(Cb.SELL, f"adm_approve:{user_id}")),
        InlineKeyboardButton("❌ Отклонить", callback_data=pack(Cb.SELL, f"adm_reject:{user_id}")),
    )
    return kb


def _parse_user_id(action: str, prefix: str) -> int | None:
    if not action.startswith(prefix + ":"):
        return None
    tail = action.split(":", 1)[1].strip()
    return int(tail) if tail.isdigit() else None


def _is_phone_verified(u) -> bool:
    return getattr(u, "seller_verified_phone", False) is True


def _has_phone(u) -> bool:
    phone = getattr(u, "phone", None)
    return bool(phone and str(phone).strip())


def register(bot: TeleBot, cfg: Config):

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(Cb.SELL + ":verify_phone"))
    def verify_phone_entry(c: CallbackQuery):
        bot.answer_callback_query(c.id)
        u = get_user(c.from_user.id, c.from_user.username)

        if not _is_phone_verified(u) or not _has_phone(u):
            bot.send_message(
                c.message.chat.id,
                "✅ Чтобы подать заявку на продавца, нужно подтвердить номер телефона.\n"
                "Нажми кнопку ниже и отправь свой контакт.",
                reply_markup=_verify_phone_kb(),
            )
            return

        if u.seller_status in (SELLER_STATUS_NONE, SELLER_STATUS_REJECTED):
            bot.send_message(
                c.message.chat.id,
                "✅ Телефон подтвержден.\nТеперь можешь подать заявку на роль продавца.",
                reply_markup=_apply_kb(),
            )
            return

        if u.seller_status == SELLER_STATUS_APPLIED:
            bot.send_message(c.message.chat.id, "⏳ Заявка уже подана и ожидает рассмотрения.")
            return

        if u.seller_status == SELLER_STATUS_SELLER:
            bot.send_message(c.message.chat.id, "✅ Ты уже продавец - доп функции доступны.")
            return

        bot.send_message(c.message.chat.id, "Статус продавца не распознан. Напиши в поддержку.")

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

        if u.seller_status == SELLER_STATUS_SELLER:
            bot.send_message(c.message.chat.id, "Ты уже продавец.")
            return

        if u.seller_status == SELLER_STATUS_APPLIED:
            bot.send_message(c.message.chat.id, "Заявка уже подана и ожидает рассмотрения.")
            return

        ok = apply_seller(c.from_user.id)
        if not ok:
            bot.send_message(c.message.chat.id, "Не получилось подать заявку. Напиши в поддержку.")
            return

        bot.send_message(c.message.chat.id, "✅ Заявка подана.\nОжидайте подтверждения от модератора.")

        for admin_id in cfg.admin_ids:
            bot.send_message(
                admin_id,
                (
                    "📝 Новая заявка на продавца\n"
                    f"User ID: {u.user_id}\n"
                    f"Username: @{u.username}\n"
                    f"Телефон: {u.phone}"
                ),
                reply_markup=_admin_review_kb(u.user_id),
            )

    @bot.message_handler(content_types=["contact"])
    def got_contact_anytime(m: Message):
        u = get_user(m.from_user.id, m.from_user.username)

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
            "✅ Номер подтвержден.\nТеперь можно подать заявку на роль продавца.",
            reply_markup=ReplyKeyboardRemove(),
        )
        bot.send_message(m.chat.id, "Нажми кнопку ниже, чтобы подать заявку.", reply_markup=_apply_kb())

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

        u = get_user(user_id, None)

        if not _is_phone_verified(u) or not _has_phone(u):
            bot.send_message(c.message.chat.id, f"Нельзя подтвердить - у пользователя нет подтвержденного телефона: {user_id}")
            return

        approve_seller(user_id)

        bot.send_message(c.message.chat.id, f"✅ Пользователь подтвержден: {user_id}")
        bot.send_message(user_id, "✅ Ваша заявка принята - теперь вы продавец.")

        try:
            bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)
        except Exception:
            pass

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

        reject_seller(user_id)

        bot.send_message(c.message.chat.id, f"❌ Пользователь отклонен: {user_id}")
        bot.send_message(user_id, "❌ Ваша заявка отклонена. Можно подать повторно после уточнения в поддержке.")

        try:
            bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)
        except Exception:
            pass
