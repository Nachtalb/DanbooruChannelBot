from telegram import Update

from danbooru.context import CustomContext


async def start(update: Update, context: CustomContext) -> None:
    if update.message:
        await update.message.reply_text("Hello")


async def help(update: Update, context: CustomContext) -> None:
    if update.message:
        await update.message.reply_text("Help")
