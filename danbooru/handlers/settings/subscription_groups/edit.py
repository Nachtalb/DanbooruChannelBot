from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from danbooru.models.chat_config import ChatConfig, SubscriptionGroup
from danbooru.utils import bool_emoji as be

from . import subscription_groups

EDIT_1_SUBSCRIPTION_GROUPS = 12
EDIT_2_SUBSCRIPTION_GROUPS = 15


async def edit_subscription_groups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return EDIT_1_SUBSCRIPTION_GROUPS

    if context.chat_data and "current_group" in context.chat_data:
        group = context.chat_data["current_group"]
    else:
        config: ChatConfig = context.chat_data["config"]  # type: ignore
        group_name = update.message.text
        group = config.get_subscription_group(group_name)
        if not group:
            group = SubscriptionGroup(name=group_name)
            config.subscription_groups.append(group)
        context.chat_data["current_group"] = group  # type: ignore

    markup = ReplyKeyboardMarkup(
        [
            ["Include", "Exclude"],
            [
                f"Toggle include full match {be(group.include_full_match)}",
                f"Toggle exclude full match {be(group.exclude_full_match)}",
            ],
            ["Save"],
        ],
        one_time_keyboard=True,
        selective=True,
    )

    await update.message.reply_text(f"<b>GROUP: {group.name}</b>\n\nWhat do you want to change?", reply_markup=markup)
    return EDIT_1_SUBSCRIPTION_GROUPS


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if "current_group" in context.chat_data:  # type: ignore
        del context.chat_data["current_group"]  # type: ignore
    return await subscription_groups(update, context)


async def toggle_full_match(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    group: SubscriptionGroup = context.chat_data["current_group"]  # type: ignore

    match context.match.groups()[0]:  # type: ignore
        case "include":
            group.include_full_match = not group.include_full_match
        case "exclude":
            group.exclude_full_match = not group.exclude_full_match
    return await edit_subscription_groups(update, context)


async def edit_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.chat_data and "current_tag_is_include" in context.chat_data:
        is_include = set(context.chat_data["current_tag_is_include"])
    else:
        is_include = set(context.match.groups()[0].lower() == "include")  # type: ignore
        context.chat_data["current_tag_is_include"] = is_include  # type: ignore

    group: SubscriptionGroup = context.chat_data["current_group"]  # type: ignore
    markup = ReplyKeyboardMarkup([["Cancel", "Save"]], one_time_keyboard=True, selective=True)

    tags = group.include if is_include else group.exclude
    tags = ", ".join([f"<code>{tag}</code>" for tag in tags])
    if context.chat_data and (new_tags := context.chat_data.get("new_tags")):
        new_tags = ", ".join([f"<code>{tag}</code>" for tag in new_tags])
        intro = f"Before: {tags}\n\nAfter: {new_tags}"
    else:
        intro = f"Theser are your current tags: {tags}"
        if not tags:
            intro = "Send me some tags (space separated)"

    await update.message.reply_text(  # type: ignore
        f"<b>GROUP {'INCLUDE' if is_include else 'EXCLUDE'} TAGS: {group.name}</b>\n\n{intro}", reply_markup=markup
    )
    return EDIT_2_SUBSCRIPTION_GROUPS


async def set_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return EDIT_2_SUBSCRIPTION_GROUPS
    context.chat_data["new_tags"] = update.message.text.split()  # type: ignore
    return await edit_tags(update, context)


async def save_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    is_include = context.chat_data["current_tag_is_include"]  # type: ignore
    group: SubscriptionGroup = context.chat_data["current_group"]  # type: ignore
    if "new_tags" in context.chat_data:  # type: ignore
        if is_include:
            group.include = context.chat_data["new_tags"]  # type: ignore
        else:
            group.exclude = context.chat_data["new_tags"]  # type: ignore
        del context.chat_data["new_tags"]  # type: ignore
    del context.chat_data["current_tag_is_include"]  # type: ignore
    return await edit_subscription_groups(update, context)


async def cancel_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if "new_tags" in context.chat_data:  # type: ignore
        del context.chat_data["new_tags"]  # type: ignore
    del context.chat_data["current_tag_is_include"]  # type: ignore
    return await edit_subscription_groups(update, context)
