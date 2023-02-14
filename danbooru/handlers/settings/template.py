from telegram import ReplyKeyboardMarkup, Update

from danbooru.context import ChatData, CustomContext
from danbooru.handlers.poster import post
from danbooru.handlers.settings import home

TEMPLATE = 6


async def template(update: Update, context: CustomContext) -> int:
    if not update.message:
        return TEMPLATE

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

    template = context.chat_data.template  # type: ignore
    intro = "Your current template looks like this:"
    # TODO save on user data
    if context.chat_data and "temp_template" in context.chat_data.temporary_data:
        intro = "Your new template will look like this:"
        template = context.chat_data.temporary_data["temp_template"]

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
<pre>{template}</pre>"""

    await update.message.reply_text(text, reply_markup=markup)
    return TEMPLATE


async def send_example_post(update: Update, context: CustomContext) -> int:
    original_template = context.chat_data.template  # type: ignore
    try:
        context.chat_data.template = context.chat_data.temporary_data.get("temp_template", context.chat_data.template)  # type: ignore
        context.args = ["4950458"]
        await post(update, context)
    finally:
        context.chat_data.template = original_template  # type: ignore

    return await template(update, context)


async def change_template(update: Update, context: CustomContext) -> int:
    context.chat_data.temporary_data["temp_template"] = update.message.text  # type: ignore
    return await template(update, context)


async def save(update: Update, context: CustomContext) -> int:
    context.chat_data.template = context.chat_data.temporary_data["temp_template"]  # type: ignore
    del context.chat_data.temporary_data["temp_template"]  # type: ignore
    return await home(update, context)


async def reset(update: Update, context: CustomContext) -> int:
    context.chat_data.temporary_data["temp_template"] = ChatData.__fields__["template"].default  # type: ignore
    return await template(update, context)


async def cancel(update: Update, context: CustomContext) -> int:
    if context.chat_data and "temp_template" in context.chat_data.temporary_data:
        del context.chat_data.temporary_data["temp_template"]  # type: ignore
    return await home(update, context)
