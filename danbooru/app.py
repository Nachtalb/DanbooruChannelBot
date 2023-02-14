from telegram.ext import Application

from danbooru.api import Api
from danbooru.models.config import Config


application: Application = None  # type: ignore
api: Api = None  # type: ignore
config: Config = None  # type: ignore


async def post_init(application: Application):
    # TODO: autogenerate
    await application.bot.set_my_commands(
        [
            ("start", "Starts the bot"),
            ("help", "Show help message"),
            ("settings", "Configure the bot"),
            ("cancel", "Cancel current action"),
            ("post", "Send some posts"),
        ]
    )


async def post_shutdown(application: Application):
    global api
    await api.close()
