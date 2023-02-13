from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from . import app
from .api import Api
from .handlers import help, post, set_config, settings, start
from .models import Config

if __name__ == "__main__":
    app.config = Config()  # type: ignore
    app.application = ApplicationBuilder().post_init(app.post_init).token(app.config.BOT_TOKEN).build()
    app.api = Api(user=app.config.DANBOORU_USERNAME, key=app.config.DANBOORU_KEY)

    app.application.add_handler(MessageHandler(filters.ALL, set_config), group=-1)
    app.application.add_handler(CommandHandler("start", start))
    app.application.add_handler(CommandHandler("help", help))
    app.application.add_handler(CommandHandler("settings", settings))
    app.application.add_handler(CommandHandler("post", post))

    if not app.config.WEBHOOK:
        app.application.run_polling()
