from telebot import TeleBot, custom_filters
from telebot.storage import StateMemoryStorage

from .config import load_config
from .storage import init_storage, ensure_bootstrap_admins
from .handlers import ban_guard, start, start_nav, profile, wallet, support, catalog, order, chat, seller, admin_panel


def main():
    cfg = load_config()

    init_storage()
    ensure_bootstrap_admins(cfg.super_admin_id, cfg.admin_ids)

    storage = StateMemoryStorage()
    bot = TeleBot(cfg.bot_token, state_storage=storage)

    bot.add_custom_filter(custom_filters.StateFilter(bot))

    ban_guard.register(bot)

    start.register(bot, cfg)
    start_nav.register(bot, cfg)
    admin_panel.register(bot, cfg)

    profile.register(bot)
    wallet.register(bot)
    support.register(bot)
    catalog.register(bot)
    order.register(bot)
    chat.register(bot)
    seller.register(bot, cfg)

    print("Bot is running...")
    bot.infinity_polling(skip_pending=True)


if __name__ == "__main__":
    main()
