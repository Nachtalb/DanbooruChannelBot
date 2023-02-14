from telegram import Update
from telegram.ext import ContextTypes

from ..models import ChatConfig


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("Hello")


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("Help")


async def set_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.chat_data.setdefault("config", ChatConfig())  # type: ignore
