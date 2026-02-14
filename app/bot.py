from telebot import TeleBot
from telebot.storage import StateMemoryStorage

from .config import load_config
from .handlers import start, start_nav, profile, wallet, support, catalog, order, chat, seller

def main():
    cfg = load_config()

    storage = StateMemoryStorage()
    bot = TeleBot(cfg.bot_token, state_storage=storage)

    # register handlers
    start.register(bot, cfg)
    start_nav.register(bot)
    profile.register(bot)
    wallet.register(bot)
    support.register(bot)
    catalog.register(bot)
    order.register(bot)
    chat.register(bot)
    seller.register(bot)

    print("Bot is running...")
    bot.infinity_polling(skip_pending=True)

if __name__ == "__main__":
    main()
