from danbooru.bot import bot
from danbooru.bot.settings import ADMINS, MODE, TELEGRAM_API_TOKEN


if __name__ == "__main__":
    bot.danbooru_bot = bot.DanbooruBot(
        TELEGRAM_API_TOKEN,
        mode=MODE["active"],  # type: ignore
        mode_config=MODE.get("configuration"),  # type: ignore
        admins=ADMINS,
    )
    bot.danbooru_bot.start()
