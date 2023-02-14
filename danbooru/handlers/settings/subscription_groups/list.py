from telegram import Update
from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.ext import ContextTypes

from danbooru.handlers.settings.subscription_groups.edit import (
    EDIT_1_SUBSCRIPTION_GROUPS,
)
from danbooru.models.chat_config import ChatConfig
from danbooru.utils import chunks

LIST_SUBSCRIPTION_GROUPS = 9


async def list_subscription_groups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return EDIT_1_SUBSCRIPTION_GROUPS

    config: ChatConfig = context.chat_data["config"]  # type: ignore
    markup = ReplyKeyboardMarkup(
        list(
            chunks(
                [group.name for group in config.subscription_groups] + ["Cancel"],
                2,
            )
        ),
        one_time_keyboard=True,
        selective=True,
    )

    if len(markup.keyboard[0]) == 1:
        await update.message.reply_text("<b>EDIT GROUPS</b>\n\nYou currently have no groups.", reply_markup=markup)
    else:
        await update.message.reply_text("<b>EDIT GROUPS</b>\n\nWhich group do you want to edit?", reply_markup=markup)
    return EDIT_1_SUBSCRIPTION_GROUPS
