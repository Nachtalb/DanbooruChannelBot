from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from danbooru.handlers.poster import post
from danbooru.models import ChatConfig

from . import home

TEMPLATE = 6


async def template(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return TEMPLATE

    config: ChatConfig = context.chat_data["config"]  # type: ignore

    markup = ReplyKeyboardMarkup(
        [
            [
                "Send example post",
                "Save",
            ],
            [
                "Reset",
                "Cancel",
            ],
        ],
        one_time_keyboard=True,
        selective=True,
    )

    template = config.template
    intro = "Your current template looks like this:"
    # TODO save on user data
    if context.chat_data and "temp_template" in context.chat_data:
        intro = "Your new template will look like this:"
        template = context.chat_data["temp_template"]

    text = f"""<b>TEMPLATE</b>\n\n<b>In the template you have multiple variables available:</b>
- <code>{{posted_at}}</code> - Date and time of the posts creation
- <code>{{id}}</code> - ID of the post
- <code>{{tags}}</code> - A sample of 15 tags from all tags available (excl. artists, copyright, characters and meta tags)
- <code>{{artists}}</code> - All artist tags
- <code>{{characters}}</code> - All character tags
- <code>{{copyright}}</code> - All copyright tags
- <code>{{meta}}</code> - All meta tags
- <code>{{rating}}</code> - Rating (general, sensitive, questionable, explicit or unset)

------------

<b>{intro}</b>
<pre>
{template}
</pre>"""

    await update.message.reply_text(text, reply_markup=markup)
    return TEMPLATE


async def send_example_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    config: ChatConfig = context.chat_data["config"]  # type: ignore
    original_template = config.template
    try:
        config.template = context.chat_data.get("temp_template", config.template)  # type: ignore
        context.args = ["4950458"]
        await post(update, context)
    finally:
        config.template = original_template

    return await template(update, context)


async def change_template(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.chat_data["temp_template"] = update.message.text  # type: ignore
    return await template(update, context)


async def save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    config: ChatConfig = context.chat_data["config"]  # type: ignore
    config.template = context.chat_data["temp_template"]  # type: ignore
    del context.chat_data["temp_template"]  # type: ignore
    return await home(update, context)


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.chat_data["temp_template"] = ChatConfig.__fields__["template"].default  # type: ignore
    return await template(update, context)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.chat_data and "temp_template" in context.chat_data:
        del context.chat_data["temp_template"]  # type: ignore
    return await home(update, context)
