from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from danbooru.models.chat_config import ChatConfig
from danbooru.models.post import Post

from .api import Api
from .commands import help, settings, start
from .models import Config

api: Api


async def post_init(application: Application):
    await application.bot.set_my_commands(
        [
            ("start", "Starts the bot"),
            ("help", "Show help message"),
            ("settings", "Configure the bot"),
        ]
    )


async def set_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.chat_data.setdefault("config", ChatConfig())  # type: ignore


def main():
    global api
    config = Config()  # type: ignore
    application = ApplicationBuilder().post_init(post_init).token(config.BOT_TOKEN).build()
    api = Api(user=config.DANBOORU_USERNAME, key=config.DANBOORU_KEY)

    application.add_handler(MessageHandler(filters.ALL, set_config), group=-1)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CommandHandler("settings", settings))

    if not config.WEBHOOK:
        application.run_polling()


if __name__ == "__main__":
    main()
