from telegram import Update
from telegram import ReplyKeyboardMarkup, Update

from danbooru.context import CustomContext
from danbooru.handlers.settings.subscription_groups.edit import (
    EDIT_1_SUBSCRIPTION_GROUPS,
)
from danbooru.utils import chunks

LIST_SUBSCRIPTION_GROUPS = 9


async def list_subscription_groups(update: Update, context: CustomContext) -> int:
    if not update.message or not update.message.text:
        return EDIT_1_SUBSCRIPTION_GROUPS

    markup = ReplyKeyboardMarkup(
        list(
            chunks(
                [group.name for group in context.chat_data.subscription_groups] + ["Cancel"],  # type: ignore
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
