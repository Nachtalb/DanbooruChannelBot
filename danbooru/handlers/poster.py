from telegram import Update
from telegram.ext import ContextTypes

from danbooru import app
from danbooru.utils import post_format


async def post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    posts = await app.api.posts(2)

    for post in posts:
        caption = post_format(context.chat_data["config"], post)  # type: ignore
        await update.message.reply_text(post.best_file_url)
        if post.is_image:
            await update.message.reply_photo(post.best_file_url, caption)
        elif post.is_video or post.is_gif:
            await update.message.reply_video(post.best_file_url, caption=caption)
