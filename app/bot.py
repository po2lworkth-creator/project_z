from telebot import TeleBot
from telebot.storage import StateMemoryStorage
from telebot.custom_filters import StateFilter

from .config import load_config
from .storage import init_storage
from .handlers import start, start_nav, profile, wallet, support, catalog, order, chat, seller


def main():
    cfg = load_config()
    init_storage()

    storage = StateMemoryStorage()
    bot = TeleBot(cfg.bot_token, state_storage=storage)
    bot.add_custom_filter(StateFilter(bot))

    # register handlers
    start.register(bot, cfg)
    start_nav.register(bot)
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
