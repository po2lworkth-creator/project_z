from telebot import types

from .callbacks import Cb, pack

# Used in catalog handler
CATEGORIES = [
    "AD", "AE", "AF", "AG", "AL",
    "AO", "AR", "AT", "AU", "AW",
    "BA", "BB", "BD", "BE", "BF",
    "BG", "BH", "BJ", "BN", "BO",
    "BR", "BS", "BT", "BW", "BZ",
]


def main_menu_kb(
    page: int = 1,
    is_seller: bool = False,
    show_admin_panel: bool = False,
    show_super_admin_panel: bool = False,
) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)

    kb.row(
        types.InlineKeyboardButton("🔥 КАТАЛОГ", callback_data=pack(Cb.NAV, "catalog")),
        types.InlineKeyboardButton("Поддержка", callback_data=pack(Cb.SUP, "open")),
    )

    if is_seller:
        kb.row(types.InlineKeyboardButton("💸 Продать", callback_data=pack(Cb.NAV, "sell")))

    kb.row(types.InlineKeyboardButton("Баланс", callback_data=pack(Cb.NAV, "wallet")))
    kb.row(types.InlineKeyboardButton("📦 Все заказы", callback_data=pack(Cb.NAV, "active")))
    kb.row(types.InlineKeyboardButton("Профиль пользователя", callback_data=pack(Cb.NAV, "profile")))

    if not is_seller:
        kb.row(
            types.InlineKeyboardButton(
                "Получить возможности продавца",
                callback_data=pack(Cb.SELL, "verify_phone"),
            )
        )

    if show_admin_panel:
        kb.row(types.InlineKeyboardButton("🛠 Админ-панель", callback_data=pack(Cb.ADM, "open")))

    if show_super_admin_panel:
        kb.row(types.InlineKeyboardButton("🗝 Панель суперадмина", callback_data=pack(Cb.SAD, "open")))

    return kb


def admin_panel_kb() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("🔎 Найти пользователя по TG ID", callback_data=pack(Cb.ADM, "profile")))
    kb.add(types.InlineKeyboardButton("💰 Изменить баланс по TG ID", callback_data=pack(Cb.ADM, "balance")))
    kb.add(types.InlineKeyboardButton("✉️ Написать пользователю", callback_data=pack(Cb.ADM, "message")))
    kb.add(types.InlineKeyboardButton("📣 Рассылка", callback_data=pack(Cb.ADM, "broadcast")))
    kb.add(types.InlineKeyboardButton("⛔ Бан/разбан по TG ID", callback_data=pack(Cb.ADM, "ban")))
    kb.add(types.InlineKeyboardButton("🧹 Снять роль продавца по TG ID", callback_data=pack(Cb.ADM, "seller_revoke")))
    kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=pack(Cb.NAV, "home")))
    return kb


def admin_ban_choice_kb() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(
        types.InlineKeyboardButton("⛔ Забанить", callback_data=pack(Cb.ADM, "ban_set")),
        types.InlineKeyboardButton("✅ Разбанить", callback_data=pack(Cb.ADM, "ban_unset")),
    )
    kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=pack(Cb.ADM, "open")))
    return kb


def super_admin_panel_kb() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("🔎 Найти пользователя по TG ID", callback_data=pack(Cb.SAD, "profile")))
    kb.add(types.InlineKeyboardButton("💰 Изменить баланс по TG ID", callback_data=pack(Cb.SAD, "balance")))
    kb.add(types.InlineKeyboardButton("✉️ Написать пользователю", callback_data=pack(Cb.SAD, "message")))
    kb.add(types.InlineKeyboardButton("📣 Рассылка", callback_data=pack(Cb.SAD, "broadcast")))
    kb.add(types.InlineKeyboardButton("⛔ Бан/разбан по TG ID", callback_data=pack(Cb.SAD, "ban")))
    kb.add(types.InlineKeyboardButton("🧹 Снять роль продавца по TG ID", callback_data=pack(Cb.SAD, "seller_revoke")))
    kb.add(types.InlineKeyboardButton("👮 Управление админами", callback_data=pack(Cb.SAD, "admins")))
    kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=pack(Cb.NAV, "home")))
    return kb


def super_admin_admins_kb() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("✅ Выдать админку по TG ID", callback_data=pack(Cb.SAD, "admin_grant")))
    kb.add(types.InlineKeyboardButton("❌ Снять админку по TG ID", callback_data=pack(Cb.SAD, "admin_revoke")))
    kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=pack(Cb.SAD, "open")))
    return kb


def super_admin_ban_choice_kb() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(
        types.InlineKeyboardButton("⛔ Забанить", callback_data=pack(Cb.SAD, "ban_set")),
        types.InlineKeyboardButton("✅ Разбанить", callback_data=pack(Cb.SAD, "ban_unset")),
    )
    kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=pack(Cb.SAD, "open")))
    return kb


def admin_broadcast_targets_kb() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("👥 Всем пользователям", callback_data=pack(Cb.ADM, "broadcast_scope", "all")))
    kb.add(types.InlineKeyboardButton("🛒 Только продавцам", callback_data=pack(Cb.ADM, "broadcast_scope", "sellers")))
    kb.add(types.InlineKeyboardButton("🛟 Только поддержке", callback_data=pack(Cb.ADM, "broadcast_scope", "support")))
    kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=pack(Cb.ADM, "open")))
    return kb


def super_admin_broadcast_targets_kb() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("👥 Всем пользователям", callback_data=pack(Cb.SAD, "broadcast_scope", "all")))
    kb.add(types.InlineKeyboardButton("🛒 Только продавцам", callback_data=pack(Cb.SAD, "broadcast_scope", "sellers")))
    kb.add(types.InlineKeyboardButton("👮 Только администраторам", callback_data=pack(Cb.SAD, "broadcast_scope", "admins")))
    kb.add(types.InlineKeyboardButton("🛟 Только поддержке", callback_data=pack(Cb.SAD, "broadcast_scope", "support")))
    kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=pack(Cb.SAD, "open")))
    return kb


def support_kb() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("Обратиться в поддержку", callback_data=pack(Cb.SUP, "contact")))
    kb.add(types.InlineKeyboardButton("💸 Запрос на вывод", callback_data=pack(Cb.SUP, "withdraw")))
    kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=pack(Cb.NAV, "home")))
    return kb


def profile_kb(phone_linked: bool) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)

    kb.row(
        types.InlineKeyboardButton("💬 Чат с пользователем", callback_data=pack(Cb.CHAT, "start")),
        types.InlineKeyboardButton("🛟 Поддержка", callback_data=pack(Cb.SUP, "open")),
    )
    kb.row(types.InlineKeyboardButton("📝 Мои отзывы", callback_data=pack(Cb.NAV, "profile_reviews")))

    if not phone_linked:
        kb.row(types.InlineKeyboardButton("📱 Привязать телефон", callback_data=pack(Cb.SELL, "verify_phone")))

    kb.row(types.InlineKeyboardButton("⬅️ Назад", callback_data=pack(Cb.NAV, "home")))
    return kb


def wallet_kb() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(types.InlineKeyboardButton("➕ Пополнить", callback_data=pack(Cb.WAL, "topup")))
    kb.row(
        types.InlineKeyboardButton("📜 История баланса", callback_data=pack(Cb.WAL, "history")),
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
