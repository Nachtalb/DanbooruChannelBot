from telegram import Update
from telegram.ext import ContextTypes

from danbooru.handlers.settings.subscription_groups.edit import (
    EDIT_1_SUBSCRIPTION_GROUPS,
)


async def new_subscription_groups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return EDIT_1_SUBSCRIPTION_GROUPS

    await update.message.reply_text("What do you want to call your group?")
    return EDIT_1_SUBSCRIPTION_GROUPS
