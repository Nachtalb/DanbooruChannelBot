import logging
import os
import sys
from threading import Thread
import types
from typing import Callable, Type

from telegram import Bot, Update, User
from telegram.ext import (
    CallbackContext,
    CommandHandler,
    Filters,
    Handler,
    MessageHandler,
    Updater,
    messagequeue,
)
from telegram.utils.request import Request

from .settings import ADMINS, LOG_LEVEL, MODE, TELEGRAM_API_TOKEN

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=LOG_LEVEL)


def decorate_all_senders(cls):
    for attr in dir(cls):
        if attr.startswith("send_") and isinstance(method := getattr(cls, attr), types.FunctionType):
            setattr(cls, attr, messagequeue.queuedmessage(method))
    return cls


@decorate_all_senders
class MQBot(Bot):
    """subclass of Bot which delegates send method handling to MQ"""

    def __init__(self, *args, is_queued_def=False, mqueue=None, **kwargs):
        super(MQBot, self).__init__(*args, **kwargs)
        # below 2 attributes should be provided for decorator usage
        self._is_messages_queued_default = is_queued_def
        self._msg_queue = mqueue or messagequeue.MessageQueue()

    def __del__(self):
        try:
            self._msg_queue.stop()
        except:
            pass


class DanbooruBot:
    def __init__(self, token: str, mode: str, mode_config: dict[str, str | int] = None, admins: list[str] = None):
        self.token = token
        self.mode = mode
        self.mode_config = mode_config or {}
        self.admins = admins or []

        self.updater: Updater
        self.logger = logging.getLogger(self.__class__.__name__)

    def start(self):
        queue = messagequeue.MessageQueue(all_burst_limit=2, all_time_limit_ms=6000)
        request = Request(con_pool_size=8)
        bot = MQBot(self.token, request=request, mqueue=queue)

        self.updater = Updater(bot=bot)

        self.add_command(name="restart", func=self.restart)

        self.log_self()
        self.send_message_if_reboot()

        from . import command
        from . import utils

        if self.mode == "webhook":
            self.updater.start_webhook(**self.mode_config)
        else:
            self.updater.start_polling()
        self.updater.idle()

    def log_self(self):
        me = self.me()
        self.logger.info(f"Start {self.mode} as: @{me.username} [{me.link}]")

    def me(self) -> User:
        return self.updater.bot.get_me()

    def add_command(self, handler: Type[Handler] | Handler = None, name: str = None, func: Callable = None, **kwargs):
        handler = handler or CommandHandler
        admin_only = kwargs.pop("admin", True)
        if admin_only:
            kwargs.setdefault("filters", Filters.user(username=self.admins))

        if isinstance(handler, Handler):
            self.updater.dispatcher.add_handler(handler=handler)
        elif handler is MessageHandler:
            self.updater.dispatcher.add_handler(handler(callback=func, **kwargs))  # type: ignore
        else:
            self.updater.dispatcher.add_handler(handler=handler(name, func, **kwargs))  # type: ignore

    def stop_and_restart(self, chat_id):
        """Gracefully stop the Updater and replace the current process with a new one."""
        self.logger.info("Restarting: stopping")
        self.updater.stop()
        self.logger.info("Restarting: starting")
        os.execl(sys.executable, sys.executable, *sys.argv + [f"is_restart={chat_id}"])

    def restart(self, update: Update, context: CallbackContext):
        """Start the restarting process

        Args:
            bot (:obj:`telegram.bot.Bot`): Telegram Api Bot Object.
            update (:obj:`telegram.update.Update`): Telegram Api Update Object
        """
        update.message.reply_text("Bot is restarting...")
        Thread(target=lambda: self.stop_and_restart(update.message.chat_id)).start()

    def send_message_if_reboot(self):
        args = sys.argv
        is_restart_arg = [item for item in args if item.startswith("is_restart")]

        if any(is_restart_arg):
            chat_id = is_restart_arg[0].split("=")[1]
            self.updater.bot.send_message(chat_id, "Bot has successfully restarted.")


danbooru_bot: DanbooruBot


def main():
    global danbooru_bot
    danbooru_bot = DanbooruBot(
        TELEGRAM_API_TOKEN,
        mode=MODE["active"],  # type: ignore
        mode_config=MODE.get("configuration"),  # type: ignore
        admins=ADMINS,
    )
    danbooru_bot.start()


if __name__ == "__main__":
    main()
