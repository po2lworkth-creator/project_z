from telebot import types

from .callbacks import Cb, pack

CATEGORIES = [
    "AD", "AE", "AF", "AG", "AL",
    "AO", "AR", "AT", "AU", "AW",
    "BA", "BB", "BD", "BE", "BF",
    "BG", "BH", "BJ", "BN", "BO",
    "BR", "BS", "BT", "BW", "BZ",
]


def main_menu_kb(page: int = 1) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)

    kb.row(
        types.InlineKeyboardButton("🔥 КАТАЛОГ", callback_data=pack(Cb.NAV, "catalog")),
        types.InlineKeyboardButton("Поддержка", callback_data=pack(Cb.SUP, "open")),
    )
    kb.row(
        types.InlineKeyboardButton("Баланс", callback_data=pack(Cb.NAV, "wallet")),
    )
    kb.row(
        types.InlineKeyboardButton("Профиль пользователя", callback_data=pack(Cb.NAV, "profile")),
    )
    kb.row(
        types.InlineKeyboardButton("Получить возможности продавца", callback_data=pack(Cb.SELL, "verify_phone")),
    )

    return kb


def support_kb() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("Обратиться в поддержку", callback_data=pack(Cb.SUP, "contact")))
    kb.add(types.InlineKeyboardButton("Запрос на вывод", callback_data=pack(Cb.WAL, "withdraw")))
    kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=pack(Cb.NAV, "home")))
    return kb


def profile_kb() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(
        types.InlineKeyboardButton("💬 Чат с продавцом", callback_data=pack(Cb.CHAT, "start")),
        types.InlineKeyboardButton("🛟 Поддержка", callback_data=pack(Cb.SUP, "open")),
    )
    kb.row(
        types.InlineKeyboardButton("✅ Продавец: верификация", callback_data=pack(Cb.SELL, "verify_phone")),
        types.InlineKeyboardButton("⬅️ Назад", callback_data=pack(Cb.NAV, "home")),
    )
    return kb


def wallet_kb() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(
        types.InlineKeyboardButton("➕ Пополнить", callback_data=pack(Cb.WAL, "topup")),
        types.InlineKeyboardButton("➖ Вывод", callback_data=pack(Cb.WAL, "withdraw")),
    )
    kb.row(
        types.InlineKeyboardButton("📜 История (заглушка)", callback_data=pack(Cb.WAL, "history")),
        types.InlineKeyboardButton("⬅️ Назад", callback_data=pack(Cb.NAV, "home")),
    )
    return kb


def order_kb(order_id: int) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(
        types.InlineKeyboardButton("📦 Отметить доставку (заглушка)", callback_data=pack(Cb.ORD, "delivered", str(order_id))),
        types.InlineKeyboardButton("✅ Подтвердить выполнение", callback_data=pack(Cb.ORD, "confirm", str(order_id))),
    )
    kb.add(types.InlineKeyboardButton("⚠️ Открыть спор (заглушка)", callback_data=pack(Cb.ORD, "dispute", str(order_id))))
    return kb
