from telegram import Update
from telegram import Update
from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.ext import ContextTypes
from telegram.ext import ContextTypes

from danbooru.models.chat_config import ChatConfig, SubscriptionGroup
from danbooru.utils import chunks

DELETE_1_SUBSCRIPTION_GROUPS = 16
DELETE_2_SUBSCRIPTION_GROUPS = 17


async def delete_subscription_groups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return DELETE_1_SUBSCRIPTION_GROUPS

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
        await update.message.reply_text("<b>DELETE GROUP</b>\n\nYou currently have no groups.", reply_markup=markup)
    else:
        await update.message.reply_text(
            "<b>DELETE GROUP:</b>\n\nWhich group do you want to delete?", reply_markup=markup
        )
    return DELETE_1_SUBSCRIPTION_GROUPS


async def confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return DELETE_2_SUBSCRIPTION_GROUPS

    config: ChatConfig = context.chat_data["config"]  # type: ignore
    group = config.get_subscription_group(update.message.text)
    if not group:
        await update.message.reply_text(f"A group with the name <code>{update.message.text}</code> does not exist.")
        return await delete_subscription_groups(update, context)

    markup = ReplyKeyboardMarkup(
        [["Yes", "No"]],
        one_time_keyboard=True,
        selective=True,
    )

    await update.message.reply_text(
        "<b>DELETE GROUP</b>\n\nAre you sure you want to delete the group <code>{group.name}</code>?",
        reply_markup=markup,
    )
    context.chat_data["group"] = group  # type: ignore
    return DELETE_2_SUBSCRIPTION_GROUPS


async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return DELETE_2_SUBSCRIPTION_GROUPS

    config: ChatConfig = context.chat_data["config"]  # type: ignore
    group: SubscriptionGroup = context.chat_data["group"]  # type: ignore
    del context.chat_data["group"]  # type: ignore

    if context.match.group().lower() == "yes":  # type: ignore
        config.subscription_groups.pop(config.subscription_groups.index(group))
        await update.message.reply_text(f"The group <code>{group.name}</code> has been deleted.")

    return await delete_subscription_groups(update, context)
