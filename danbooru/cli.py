from asyncio import run

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

from .api import Api
from .commands import help, settings, start
from .models import Config

api: Api


async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global api
    if not update.message:
        return
    post = (await api.posts(1))[0]
    await update.message.reply_photo(post.best_file_url, caption=f"by {post.tag_string_artist}")


async def post_init(application: Application):
    await application.bot.set_my_commands(
        [
            ("start", "Starts the bot"),
            ("help", "Show help message"),
            ("settings", "Configure the bot"),
            ("test_command", "Run test command"),
        ]
    )


def main():
    global api
    config = Config()  # type: ignore
    application = ApplicationBuilder().post_init(post_init).token(config.BOT_TOKEN).build()
    api = Api(user=config.DANBOORU_USERNAME, key=config.DANBOORU_KEY)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CommandHandler("settings", settings))
    application.add_handler(CommandHandler("test_command", test_command))

    if not config.WEBHOOK:
        application.run_polling()


if __name__ == "__main__":
    main()
