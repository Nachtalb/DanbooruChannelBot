from telegram import ReplyKeyboardMarkup, Update

from danbooru import app
from danbooru.context import CustomContext
from danbooru.utils import bool_emoji


HOME_SUBSCRIPTION_GROUPS = 8
TEST_SUBSCRIPTION_GROUPS = 18


async def subscription_groups(update: Update, context: CustomContext) -> int:
    if not update.message:
        return HOME_SUBSCRIPTION_GROUPS

    markup = ReplyKeyboardMarkup(
        [
            [
                "Edit existing groups",
                "Create new group",
            ],
            ["Delete a group", "Test groups"],
            [f"Toggle group policy [{'OR' if context.chat_data.subscription_groups_or else 'AND'}]", "Back"],  # type: ignore
        ],
        one_time_keyboard=True,
        selective=True,
    )

    text = (
        "<b>FILTER GROUPS</b>\n\n"
        "With filter groups you can block or force certain tags to be present. As an example:\nSet <b>include</b> to"
        " <code>hololive</code>. Now only posts with the tag <code>hololive</code> will be posted.\nNo we add a the tag"
        " <code>yuri</code> to the same group. By default it now posts all posts that have either <code>hololive</code>"
        " or <code>yuri</code> tag. If you want that only posts appear that have both tags set,you have to enable"
        " <b>Include full match</b>.\n\nThe same applies to the exclude, just the other way around. If you set"
        " <code>hololive</code> as an excluded tag, no posts with said Tag will appear.\n\nYou can also create multiple"
        " groups. When you do this the group policy will take effect. It's either OR or AND, meaning the posts will"
        " appear <code>group 1 OR group 2</code> matches or <code>group 1 AND group 2</code> match respectively."
    )

    await update.message.reply_text(text, reply_markup=markup)
    return HOME_SUBSCRIPTION_GROUPS


async def group_policy(update: Update, context: CustomContext) -> int:
    context.chat_data.subscription_groups_or = not context.chat_data.subscription_groups_or  # type: ignore
    return await subscription_groups(update, context)


async def test_group(update: Update, context: CustomContext) -> int:
    if not update.message:
        return TEST_SUBSCRIPTION_GROUPS

    await update.message.reply_text("Send me the ID of a post to test the configuration on")
    return TEST_SUBSCRIPTION_GROUPS


async def run_test_group(update: Update, context: CustomContext) -> int:
    if not update.message:
        return TEST_SUBSCRIPTION_GROUPS

    try:
        post_id = int(update.message.text.split()[0])  # type: ignore
    except (IndexError, ValueError, TypeError):
        await update.message.reply_text("You have to send me the ID of a danbooru post.")
        return TEST_SUBSCRIPTION_GROUPS

    post = await app.api.post(post_id)
    if context.chat_data and context.chat_data.post_allowed(post):
        await update.message.reply_text(f"{bool_emoji(True)} The post is allowed with the current configuration")
    else:
        await update.message.reply_text(f"{bool_emoji(False)} The post is not allowed with the current configuration")

    return await subscription_groups(update, context)
