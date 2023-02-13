from telegram.ext import Application

from .api import Api
from .models.config import Config


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
            ("post", "Send some posts"),
        ]
    )
