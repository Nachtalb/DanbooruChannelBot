from collections import defaultdict
from typing import DefaultDict

from telegram.ext import Application, CallbackContext, ExtBot

from danbooru.context.bot_data import BotData
from danbooru.context.chat_data import ChatData
from danbooru.context.user_data import UserData


class CustomContext(CallbackContext[ExtBot, UserData, ChatData, BotData]):
    pass
